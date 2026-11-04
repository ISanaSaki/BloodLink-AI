"""``audit_logs`` - append-only trail for sensitive operations (section 3 and 14)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPrimaryKeyMixin, utcnow

ACTION_LENGTH = 60
ENTITY_TYPE_LENGTH = 40


class AuditLog(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    # Append-only: a trail without a time is not evidence, so only `created_at` exists.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )

    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(ACTION_LENGTH), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(ENTITY_TYPE_LENGTH), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Never store coordinates, OTP codes, tokens or full phone numbers here.
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
