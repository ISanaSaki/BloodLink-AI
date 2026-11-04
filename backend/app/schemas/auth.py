"""Request/response shapes for the public OTP endpoints (sections 9.1 and 9.2)."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import OtpPurpose
from app.schemas.common import PhoneNumber
from app.schemas.user import UserOut


class OtpRequestIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phone: PhoneNumber
    purpose: OtpPurpose


class OtpRequestOut(BaseModel):
    challenge_id: UUID
    expires_in_seconds: int
    resend_after_seconds: int


class OtpVerifyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challenge_id: UUID
    phone: PhoneNumber
    code: str = Field(pattern=r"^\d{6}$", examples=["123456"])
    purpose: OtpPurpose


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user: UserOut
