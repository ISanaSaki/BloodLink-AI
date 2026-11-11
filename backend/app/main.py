"""FastAPI application entrypoint: ``uvicorn app.main:app``."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.context import new_request_id, reset_request_id, set_request_id
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger(__name__)

DESCRIPTION = """
Smart blood-donation call-out and donor routing system — competition MVP on synthetic data.

Every response uses the `{ data, meta }` envelope and every error uses `{ error }`;
field names are exactly snake_case. Full rules live in `docs/API_CONTRACT.md`.
"""

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=DESCRIPTION,
    # Traceback pages are never enabled: section 7 requires every error body to be
    # `{ "error": ... }`. `APP_DEBUG` only raises the log level.
    debug=False,
    openapi_tags=[
        {"name": "auth", "description": "OTP request/verify and access token."},
        {"name": "users", "description": "Current user."},
        {"name": "donors", "description": "Donor self-service profile, consents, location."},
        {"name": "dispatch", "description": "Matching-driven staged dispatch and candidates."},
        {"name": "notifications", "description": "Donor notifications and responses."},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-Id") or new_request_id()
    token = set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_request_id(token)
    response.headers["X-Request-Id"] = request_id
    return response


register_exception_handlers(app)
app.include_router(api_router, prefix=settings.api_v1_prefix)
