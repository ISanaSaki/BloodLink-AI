"""``GET /users/me`` (section 9.3)."""

from fastapi import APIRouter

from app.core.dependencies import CurrentUser
from app.schemas.common import envelope
from app.schemas.user import UserOut

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", summary="اطلاعات کاربر جاری")
def read_current_user(user: CurrentUser) -> dict:
    return envelope(UserOut.model_validate(user).model_dump(mode="json"))
