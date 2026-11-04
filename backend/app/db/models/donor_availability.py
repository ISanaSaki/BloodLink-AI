"""``donor_availability`` - the donor's own statement about reachability, not medical fitness."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import AvailabilityStatus
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.db.models.donor_profile import DonorProfile

STATUS_LENGTH = 20


class DonorAvailability(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "donor_availability"
    __table_args__ = (
        CheckConstraint(
            "available_from IS NULL OR available_until IS NULL OR available_from <= available_until",
            name="window_is_ordered",
        ),
    )

    donor_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("donor_profiles.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    status: Mapped[AvailabilityStatus] = enum_column(
        AvailabilityStatus, STATUS_LENGTH, nullable=False, default=AvailabilityStatus.UNAVAILABLE
    )
    available_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    donor: Mapped["DonorProfile"] = relationship(back_populates="availability")

    def is_available_at(self, moment: datetime) -> bool:
        if self.status != AvailabilityStatus.AVAILABLE:
            return False
        if self.available_from is not None and moment < self.available_from:
            return False
        return not (self.available_until is not None and moment > self.available_until)
