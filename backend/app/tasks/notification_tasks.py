"""Celery tasks for staged dispatch (contract section 12).

Every task is idempotent: re-running it after a worker restart must not send a second
message or double-apply a state transition. Task arguments carry only ids - never a
phone number, OTP code or coordinate - so nothing sensitive lands in the broker.
"""

from datetime import UTC, datetime
from uuid import UUID

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import session_scope
from app.services.notification_service import NotificationService
from app.tasks.celery_app import celery_app

logger = get_logger(__name__)

DISPATCH_BATCH = "app.tasks.notification_tasks.dispatch_notification_batch"
CHECK_TIMEOUT = "app.tasks.notification_tasks.check_dispatch_timeout"
CANCEL_PENDING = "app.tasks.notification_tasks.cancel_pending_notifications"


@celery_app.task(bind=True, name=DISPATCH_BATCH, max_retries=settings.sms_max_retries)
def dispatch_notification_batch(self, request_id: str, batch_number: int) -> dict[str, object]:
    """Send exactly one stage; `check_dispatch_timeout` decides when the next stage is due."""
    with session_scope() as session:
        service = NotificationService.build(session)
        sent = service.send_batch(UUID(request_id), batch_number)
    logger.info(
        "dispatch_batch_completed",
        extra={"request_id": request_id, "batch_number": batch_number, "sent": sent},
    )
    return {"request_id": request_id, "batch_number": batch_number, "sent": sent}


@celery_app.task(name=CHECK_TIMEOUT)
def check_dispatch_timeout() -> dict[str, int]:
    """Beat task: expire overdue requests and release the next stage of each live call."""
    moment = datetime.now(UTC)
    with session_scope() as session:
        service = NotificationService.build(session)
        expired = service.expire_overdue(now=moment)
        due = service.advance_due_batches(now=moment)

    for request_id, batch_number in due:
        dispatch_notification_batch.delay(str(request_id), batch_number)

    logger.info(
        "dispatch_timeout_checked",
        extra={"expired_requests": expired, "advanced_batches": len(due)},
    )
    return {"expired_requests": expired, "advanced_batches": len(due)}


@celery_app.task(name=CANCEL_PENDING)
def cancel_pending_notifications(request_id: str, reason: str = "cancelled_by_center") -> dict[str, int]:
    with session_scope() as session:
        cancelled = NotificationService.build(session).cancel_pending(UUID(request_id), reason)
    logger.info(
        "pending_notifications_cancelled",
        extra={"request_id": request_id, "cancelled": cancelled, "reason": reason},
    )
    return {"cancelled": cancelled}
