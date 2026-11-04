"""``donor_responses`` - exactly one final answer per notification."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Integer, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DonorResponseType
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column, utcnow

if TYPE_CHECKING:
    from app.db.models.notification import Notification

RESPONSE_LENGTH = 20


class DonorResponse(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "donor_responses"

    notification_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("notifications.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    response: Mapped[DonorResponseType] = enum_column(DonorResponseType, RESPONSE_LENGTH, nullable=False)
    responded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    # Optional self-reported travel time, shown to the centre by section 9.13.
    eta_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    notification: Mapped["Notification"] = relationship(back_populates="response")

    @property
    def donor_id(self) -> UUID:
        """Donor is derived through the notification, keeping one source of truth."""
        return self.notification.donor_id
