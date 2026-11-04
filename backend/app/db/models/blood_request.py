"""``blood_requests`` plus the request state machine frozen in section 15."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import BloodGroup, BloodRequestStatus, ComponentType, RequestUrgency, RhFactor
from app.core.exceptions import Conflict
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.db.models.blood_center import BloodCenter
    from app.db.models.notification import Notification
    from app.db.models.user import User

COMPONENT_LENGTH = 30
URGENCY_LENGTH = 20
STATUS_LENGTH = 24
BLOOD_GROUP_LENGTH = 2
RH_FACTOR_LENGTH = 8

TRANSITIONS: dict[BloodRequestStatus, frozenset[BloodRequestStatus]] = {
    BloodRequestStatus.DRAFT: frozenset({BloodRequestStatus.ACTIVE, BloodRequestStatus.CANCELLED}),
    BloodRequestStatus.ACTIVE: frozenset(
        {
            BloodRequestStatus.FULFILLED,
            BloodRequestStatus.CANCELLED,
            BloodRequestStatus.EXPIRED,
        }
    ),
    BloodRequestStatus.FULFILLED: frozenset(),
    BloodRequestStatus.CANCELLED: frozenset(),
    BloodRequestStatus.EXPIRED: frozenset(),
}

TERMINAL_STATUSES = frozenset(
    {BloodRequestStatus.FULFILLED, BloodRequestStatus.CANCELLED, BloodRequestStatus.EXPIRED}
)


class BloodRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "blood_requests"
    __table_args__ = (CheckConstraint("units_needed > 0", name="units_needed_positive"),)

    center_id: Mapped[UUID] = mapped_column(
        Uuid(), ForeignKey("blood_centers.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    component_type: Mapped[ComponentType] = enum_column(ComponentType, COMPONENT_LENGTH, nullable=False)
    blood_group: Mapped[BloodGroup] = enum_column(BloodGroup, BLOOD_GROUP_LENGTH, nullable=False)
    rh_factor: Mapped[RhFactor] = enum_column(RhFactor, RH_FACTOR_LENGTH, nullable=False)
    units_needed: Mapped[int] = mapped_column(Integer, nullable=False)
    urgency: Mapped[RequestUrgency] = enum_column(
        RequestUrgency, URGENCY_LENGTH, nullable=False, default=RequestUrgency.ROUTINE
    )
    status: Mapped[BloodRequestStatus] = enum_column(
        BloodRequestStatus, STATUS_LENGTH, nullable=False, default=BloodRequestStatus.DRAFT, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[UUID] = mapped_column(Uuid(), ForeignKey("users.id"), nullable=False)
    # Internal centre note: never shown to donors and never printed in an SMS (section 9.8).
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    center: Mapped["BloodCenter"] = relationship(back_populates="requests")
    created_by_user: Mapped["User"] = relationship(back_populates="created_requests")
    notifications: Mapped[list["Notification"]] = relationship(back_populates="request")

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_STATUSES

    def transition_to(self, target: BloodRequestStatus, *, now: datetime | None = None) -> None:
        """Apply a state-machine transition or raise 409 CONFLICT (section 15)."""
        if target not in TRANSITIONS[self.status]:
            raise Conflict(
                f"انتقال وضعیت از {self.status.value} به {target.value} مجاز نیست.",
                details=[{"field": "status", "message": f"{self.status.value} -> {target.value}"}],
            )
        self.status = target
        if target is BloodRequestStatus.ACTIVE:
            self.activated_at = now or datetime.now(UTC)

    def is_expired(self, now: datetime) -> bool:
        reference = now if now.tzinfo else now.replace(tzinfo=UTC)
        return self.expires_at <= reference
