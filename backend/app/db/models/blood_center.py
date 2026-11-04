"""``blood_centers`` - a donation centre; only verified centres may request blood."""

from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.db.models.blood_request import BloodRequest
    from app.db.models.user import User

NAME_LENGTH = 160


class BloodCenter(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "blood_centers"
    __table_args__ = (
        CheckConstraint("latitude >= -90 AND latitude <= 90", name="latitude_range"),
        CheckConstraint("longitude >= -180 AND longitude <= 180", name="longitude_range"),
    )

    name: Mapped[str] = mapped_column(String(NAME_LENGTH), nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Public operational field surfaced by GET /centers (section 9.7).
    opening_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Operator binding required by section 8 ("center owner" may patch a centre).
    owner_user_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    owner: Mapped["User | None"] = relationship()
    requests: Mapped[list["BloodRequest"]] = relationship(back_populates="center")

    def accepts_new_requests(self) -> bool:
        return self.is_verified and self.is_active
