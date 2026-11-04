"""Append-only audit trail for sensitive operations (sections 3 and 14)."""

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.context import get_request_id
from app.core.logging import redact
from app.db.models.audit_log import AuditLog


@dataclass(slots=True)
class AuditService:
    db: Session

    def record(
        self,
        *,
        action: str,
        entity_type: str,
        actor_id: UUID | None = None,
        entity_id: UUID | str | None = None,
        details: dict[str, Any] | None = None,
        comment: str | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            actor_id=actor_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=redact(details) if details else None,
            request_id=get_request_id(),
            comment=comment,
        )
        self.db.add(entry)
        return entry
