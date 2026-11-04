"""Pydantic schemas. Every JSON key stays snake_case (contract section 2.1)."""

from app.schemas.auth import OtpRequestIn, OtpRequestOut, OtpVerifyIn, TokenOut
from app.schemas.common import envelope, paginated
from app.schemas.donor import (
    DonorLocationOut,
    DonorLocationPatch,
    DonorProfileOut,
    DonorProfilePatch,
)
from app.schemas.notification import (
    DonorResponseOut,
    NotificationOut,
    NotificationResponseIn,
    NotificationResponseOut,
)
from app.schemas.user import UserOut

__all__ = [
    "DonorLocationOut",
    "DonorLocationPatch",
    "DonorProfileOut",
    "DonorProfilePatch",
    "DonorResponseOut",
    "NotificationOut",
    "NotificationResponseIn",
    "NotificationResponseOut",
    "OtpRequestIn",
    "OtpRequestOut",
    "OtpVerifyIn",
    "TokenOut",
    "UserOut",
    "envelope",
    "paginated",
]
