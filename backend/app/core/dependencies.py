"""FastAPI dependencies: DB session, authentication, role guards, pagination, client IP."""

from typing import Annotated, TYPE_CHECKING
from uuid import UUID

from fastapi import Depends, Query, Request
from jwt import PyJWTError
from sqlalchemy.orm import Session

from app.core.enums import UserRole
from app.core.exceptions import Forbidden, NotFound, Unauthorized
from app.core.security import decode_access_token
from app.db.models.user import User
from app.db.session import get_db

if TYPE_CHECKING:
    from app.db.models.blood_center import BloodCenter

DatabaseSession = Annotated[Session, Depends(get_db)]


def _bearer_token(request: Request) -> str:
    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized()
    return token.strip()


def get_current_user(request: Request, db: DatabaseSession) -> User:
    token = _bearer_token(request)
    try:
        claims = decode_access_token(token)
    except PyJWTError as exc:
        raise Unauthorized("The token is invalid or has expired.") from exc

    user = db.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise Unauthorized()
    request.state.user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole):
    allowed = frozenset(roles)

    def dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise Forbidden()
        return user

    return dependency


DonorUser = Annotated[User, Depends(require_roles(UserRole.DONOR))]
CenterOrAdminUser = Annotated[User, Depends(require_roles(UserRole.CENTER_OPERATOR, UserRole.ADMIN))]


def assert_center_access(db: Session, user: User, center_id: UUID) -> "BloodCenter":
    """A centre's data is reachable by its own operator or an admin (sections 8, 9.11)."""
    from app.db.models.blood_center import BloodCenter

    center = db.get(BloodCenter, center_id)
    if center is None:
        raise NotFound("Centre not found.")
    if user.role is UserRole.ADMIN:
        return center
    if user.role is not UserRole.CENTER_OPERATOR or center.owner_user_id != user.id:
        raise Forbidden("This centre is not linked to your account.")
    return center


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_page_params(
    page: Annotated[int, Query(ge=1, description="Page number, starting at 1")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page, at most 100")] = 20,
) -> tuple[int, int]:
    return page, page_size


PageParams = Annotated[tuple[int, int], Depends(get_page_params)]

__all__ = [
    "CurrentUser",
    "DatabaseSession",
    "DonorUser",
    "PageParams",
    "get_client_ip",
    "get_current_user",
    "get_page_params",
    "require_roles",
]
