"""``notifications`` - one SMS attempt per donor/request, guarded by an idempotency key."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import NotificationChannel, NotificationStatus
from app.core.exceptions import Conflict
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.db.models.blood_request import BloodRequest
    from app.db.models.donor_profile import DonorProfile
    from app.db.models.donor_response import DonorResponse

CHANNEL_LENGTH = 10
STATUS_LENGTH = 20
IDEMPOTENCY_KEY_LENGTH = 100
PROVIDER_MESSAGE_ID_LENGTH = 120
RESPONSE_TOKEN_LENGTH = 64

TRANSITIONS: dict[NotificationStatus, frozenset[NotificationStatus]] = {
    NotificationStatus.QUEUED: frozenset(
        {NotificationStatus.SENT, NotificationStatus.FAILED, NotificationStatus.CANCELLED}
    ),
    NotificationStatus.SENT: frozenset({NotificationStatus.DELIVERED, NotificationStatus.FAILED}),
    NotificationStatus.DELIVERED: frozenset(),
    NotificationStatus.FAILED: frozenset(),
    NotificationStatus.CANCELLED: frozenset(),
}


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "notifications"
    __table_args__ = (CheckConstraint("batch_number >= 1", name="batch_number_positive"),)

    request_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("blood_requests.id", ondelete="CASCADE"), nullable=False, index=True
    )
    donor_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("donor_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    channel: Mapped[NotificationChannel] = enum_column(NotificationChannel, CHANNEL_LENGTH, nullable=False)
    status: Mapped[NotificationStatus] = enum_column(
        NotificationStatus, STATUS_LENGTH, nullable=False, default=NotificationStatus.QUEUED, index=True
    )
    # Section 17 DSP-03: prevents a second notification for the same donor/request/stage.
    idempotency_key: Mapped[str] = mapped_column(
        String(IDEMPOTENCY_KEY_LENGTH), nullable=False, unique=True
    )
    provider_message_id: Mapped[str | None] = mapped_column(
        String(PROVIDER_MESSAGE_ID_LENGTH), nullable=True
    )
    # Dispatch stage reported by GET /candidates (section 9.11).
    batch_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Opaque token behind the secure response link of section 12; grants no other access.
    response_token: Mapped[str | None] = mapped_column(
        String(RESPONSE_TOKEN_LENGTH), nullable=True, unique=True
    )

    request: Mapped["BloodRequest"] = relationship(back_populates="notifications")
    donor: Mapped["DonorProfile"] = relationship()
    response: Mapped["DonorResponse | None"] = relationship(
        back_populates="notification", uselist=False, cascade="all, delete-orphan"
    )

    def transition_to(self, target: NotificationStatus) -> None:
        if target not in TRANSITIONS[self.status]:
            raise Conflict(
                f"انتقال وضعیت اعلان از {self.status.value} به {target.value} مجاز نیست.",
                details=[{"field": "status", "message": f"{self.status.value} -> {target.value}"}],
            )
        self.status = target

    @staticmethod
    def build_idempotency_key(request_id: UUID, donor_id: UUID, batch_number: int) -> str:
        return f"sms:{request_id}:{donor_id}:b{batch_number}"
