"""``donor_profiles`` - declared donor data; never a medical eligibility verdict."""

from datetime import date
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BloodGroup, RhFactor
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.db.models.donor_availability import DonorAvailability
    from app.db.models.donor_location import DonorLocation
    from app.db.models.user import User

BLOOD_GROUP_LENGTH = 2
RH_FACTOR_LENGTH = 8


class DonorProfile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "donor_profiles"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    blood_group: Mapped[BloodGroup | None] = enum_column(BloodGroup, BLOOD_GROUP_LENGTH, nullable=True)
    rh_factor: Mapped[RhFactor | None] = enum_column(RhFactor, RH_FACTOR_LENGTH, nullable=True)
    # Only an authorised reference may flip this flag; the donor input is ignored (section 9.4).
    blood_type_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_donation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    sms_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    location_consent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    user: Mapped["User"] = relationship(back_populates="donor_profile")
    location: Mapped["DonorLocation | None"] = relationship(
        back_populates="donor", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    availability: Mapped["DonorAvailability | None"] = relationship(
        back_populates="donor", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
