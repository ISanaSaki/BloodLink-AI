"""Donor self-service shapes (sections 9.4 and 9.6)."""

from datetime import date
from decimal import Decimal
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.enums import BloodGroup, RhFactor
from app.schemas.common import UtcDatetime


class DonorProfilePatch(BaseModel):
    """``blood_type_verified`` is deliberately absent: the donor cannot set it (9.4)."""

    model_config = ConfigDict(extra="forbid")

    blood_group: BloodGroup | None = None
    rh_factor: RhFactor | None = None
    last_donation_date: date | None = None
    sms_consent: bool | None = None
    location_consent: bool | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> Self:
        if not self.model_dump(exclude_unset=True):
            raise ValueError("حداقل یک فیلد برای ویرایش ارسال کنید.")
        return self


class DonorProfileOut(BaseModel):
    donor_id: UUID
    blood_group: BloodGroup | None
    rh_factor: RhFactor | None
    blood_type_verified: bool
    last_donation_date: date | None
    sms_consent: bool
    location_consent: bool


class DonorLocationPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    latitude: Decimal = Field(ge=Decimal("-90"), le=Decimal("90"), examples=[33.4878])
    longitude: Decimal = Field(ge=Decimal("-180"), le=Decimal("180"), examples=[48.3558])


class DonorLocationOut(BaseModel):
    donor_id: UUID
    latitude: Decimal | None
    longitude: Decimal | None
    updated_at: UtcDatetime
    location_consent: bool
