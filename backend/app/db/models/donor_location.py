"""``donor_locations`` - coordinates kept only while ``location_consent`` is granted."""

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Numeric, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow

if TYPE_CHECKING:
    from app.db.models.donor_profile import DonorProfile


class DonorLocation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "donor_locations"
    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="latitude_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="longitude_range"),
    )

    donor_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("donor_profiles.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow, server_default=func.now()
    )

    donor: Mapped["DonorProfile"] = relationship(back_populates="location")
