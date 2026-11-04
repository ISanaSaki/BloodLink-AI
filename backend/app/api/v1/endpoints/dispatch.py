"""Dispatch and candidate endpoints owned by the Backend Lead (sections 9.10, 9.11).

Matching itself lives in ``app.services.matching_service``; these endpoints only authorise
the caller, run the service and shape the response so no donor PII leaves the backend.
"""

import hashlib
import hmac
from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import (
    CenterOrAdminUser,
    DatabaseSession,
    PageParams,
    assert_center_access,
)
from app.core.enums import NotificationStatus
from app.core.exceptions import NotFound
from app.core.logging import get_logger
from app.schemas.common import envelope, paginated
from app.schemas.dispatch import CandidateOut, DispatchAcceptedOut
from app.db.models.blood_request import BloodRequest
from app.db.models.notification import Notification
from app.services.audit_service import AuditService
from app.services.matching_service import MatchingService
from app.services.notification_service import NotificationService
from app.tasks.notification_tasks import dispatch_notification_batch

router = APIRouter(prefix="/blood-requests", tags=["dispatch"])
logger = get_logger(__name__)


def donor_reference(donor_id: UUID) -> str:
    """Opaque, non-guessable reference: the panel never sees names, phones or coordinates."""
    digest = hmac.new(settings.secret_key.encode(), str(donor_id).encode(), hashlib.sha256)
    return f"donor-{digest.hexdigest()[:12]}"


def _enqueue_batch(request_id: UUID, batch_number: int) -> None:
    try:
        dispatch_notification_batch.delay(str(request_id), batch_number)
    except Exception as exc:  # no broker in a demo run: execute the batch inline
        logger.warning("dispatch_enqueue_failed_running_inline", extra={"error_type": type(exc).__name__})
        dispatch_notification_batch.apply(args=(str(request_id), batch_number))


@router.post(
    "/{request_id}/dispatch",
    status_code=status.HTTP_202_ACCEPTED,
    summary="شروع Matching و فراخوان مرحله‌ای",
)
def start_dispatch(request_id: UUID, user: CenterOrAdminUser, db: DatabaseSession) -> dict:
    request = _load_request(db, request_id)
    assert_center_access(db, user, request.center_id)

    service = NotificationService.build(db)
    plan = service.plan_dispatch(request_id)
    AuditService(db).record(
        action="dispatch_started",
        entity_type="blood_request",
        actor_id=user.id,
        entity_id=request.id,
        details={
            "candidate_count": plan.candidate_count,
            "first_batch_size": plan.first_batch_size,
            "batch_count": plan.batch_count,
        },
    )
    db.commit()
    _enqueue_batch(request_id, 1)

    return envelope(
        DispatchAcceptedOut(
            dispatch_id=plan.dispatch_id,
            request_id=plan.request_id,
            status=NotificationStatus.QUEUED,
            candidate_count=plan.candidate_count,
            first_batch_size=plan.first_batch_size,
        ).model_dump(mode="json")
    )


@router.get("/{request_id}/candidates", summary="مشاهده کاندیداهای رتبه‌بندی‌شده")
def list_candidates(
    request_id: UUID,
    user: CenterOrAdminUser,
    db: DatabaseSession,
    page_params: PageParams,
) -> dict:
    request = _load_request(db, request_id)
    assert_center_access(db, user, request.center_id)

    service = NotificationService.build(db)
    matching = MatchingService(db, service.maps, service.policy, service.config)
    _, inp = matching.candidates_for_request(request_id)
    result = matching.run(inp)

    dispatchable = result.dispatchable
    stages = {
        notification.donor_id: notification.batch_number
        for notification in db.scalars(
            select(Notification).where(Notification.request_id == request_id)
        ).all()
    }
    # Before a call is sent the panel still needs a stage: it is the position in the
    # same deterministic ordering ``plan_dispatch`` uses, so it never drifts from the record.
    batch_size = max(1, service.config.dispatch_batch_size)
    planned = {
        candidate.donor_id: position // batch_size + 1
        for position, candidate in enumerate(dispatchable)
    }

    page, page_size = page_params
    ordered = result.candidates
    window = ordered[(page - 1) * page_size : page * page_size]

    return paginated(
        [
            CandidateOut(
                donor_reference=donor_reference(candidate.donor_id),
                eta_minutes=candidate.eta_minutes,
                distance_km=candidate.distance_km,
                eligibility_check_status=candidate.eligibility_check_status,
                dispatch_stage=stages.get(candidate.donor_id) or planned.get(candidate.donor_id),
            ).model_dump(mode="json")
            for candidate in window
        ],
        page=page,
        page_size=page_size,
        total=len(ordered),
    )


def _load_request(db: Session, request_id: UUID) -> BloodRequest:
    request = db.get(BloodRequest, request_id)
    if request is None:
        raise NotFound("درخواست خون یافت نشد.")
    return request
