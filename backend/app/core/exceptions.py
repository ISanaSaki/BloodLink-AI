"""Standard error shape of section 7.2 and section 14 of the contract."""

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.context import get_request_id


class ErrorCode:
    """Stable, machine-readable codes the Frontend switches on (section 7.2)."""

    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


DEFAULT_MESSAGES: dict[str, str] = {
    ErrorCode.INVALID_REQUEST: "The request is invalid.",
    ErrorCode.UNAUTHENTICATED: "You must sign in to perform this operation.",
    ErrorCode.FORBIDDEN: "You do not have permission for this operation.",
    ErrorCode.RESOURCE_NOT_FOUND: "The requested resource was not found.",
    ErrorCode.CONFLICT: "The current state of the resource does not allow this operation.",
    ErrorCode.VALIDATION_ERROR: "The input is not valid.",
    ErrorCode.RATE_LIMITED: "Too many requests. Please try again later.",
    ErrorCode.INTERNAL_ERROR: "An internal error occurred. Reference the request ID when reporting it.",
}


class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str | None = None,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, "Unknown error.")
        self.details = details
        self.headers = headers or {}
        super().__init__(f"{code}: {self.message}")


class Unauthorized(AppError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            status.HTTP_401_UNAUTHORIZED,
            ErrorCode.UNAUTHENTICATED,
            message,
            headers={"WWW-Authenticate": "Bearer"},
        )


class Forbidden(AppError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(status.HTTP_403_FORBIDDEN, ErrorCode.FORBIDDEN, message)


class NotFound(AppError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(status.HTTP_404_NOT_FOUND, ErrorCode.RESOURCE_NOT_FOUND, message)


class Conflict(AppError):
    def __init__(self, message: str | None = None, details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(status.HTTP_409_CONFLICT, ErrorCode.CONFLICT, message, details)


class BadRequest(AppError):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(status.HTTP_400_BAD_REQUEST, ErrorCode.INVALID_REQUEST, message)


class RateLimited(AppError):
    def __init__(self, message: str | None = None, retry_after_seconds: int | None = None) -> None:
        headers = {"Retry-After": str(retry_after_seconds)} if retry_after_seconds else {}
        super().__init__(
            status.HTTP_429_TOO_MANY_REQUESTS, ErrorCode.RATE_LIMITED, message, headers=headers
        )


class ValidationFailed(AppError):
    def __init__(self, details: list[dict[str, Any]], message: str | None = None) -> None:
        super().__init__(
            status.HTTP_422_UNPROCESSABLE_ENTITY, ErrorCode.VALIDATION_ERROR, message, details=details
        )


def error_payload(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message, "request_id": get_request_id()}
    if details:
        error["details"] = details
    return {"error": error}


def _validation_details(exc: RequestValidationError | ValidationError) -> list[dict[str, Any]]:
    details = []
    for err in exc.errors():
        location = [str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path")]
        details.append({"field": ".".join(location) or "request", "message": err.get("msg", "invalid")})
    return details


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=error_payload(
                ErrorCode.VALIDATION_ERROR,
                DEFAULT_MESSAGES[ErrorCode.VALIDATION_ERROR],
                _validation_details(exc),
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            status.HTTP_401_UNAUTHORIZED: ErrorCode.UNAUTHENTICATED,
            status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
            status.HTTP_404_NOT_FOUND: ErrorCode.RESOURCE_NOT_FOUND,
            status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
            status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
        }.get(exc.status_code, ErrorCode.INVALID_REQUEST)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Section 14: never leak provider/internal detail to the client.
        from app.core.logging import get_logger

        get_logger(__name__).exception("unhandled_exception", extra={"error_type": type(exc).__name__})
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=error_payload(ErrorCode.INTERNAL_ERROR, DEFAULT_MESSAGES[ErrorCode.INTERNAL_ERROR]),
        )
