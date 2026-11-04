"""Schemas of ``GET /users/me`` and the user object embedded in the token response."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.core.enums import UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    phone: str
    role: UserRole
    is_active: bool
    is_profile_complete: bool
