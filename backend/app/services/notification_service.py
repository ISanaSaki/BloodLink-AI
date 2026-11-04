"""Dispatch orchestration: staged notification batches, responses and stop conditions.

Responsibilities frozen by the contract:
* create one notification per donor/request stage, guarded by ``idempotency_key`` (DSP-03);
* send a batch through the SMS adapter and persist provider status (section 12);
* stop automatically on fulfilment, cancellation or expiry (section 15).
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.enums import (
    BloodRequestStatus,
    DonorResponseType,
    NotificationChannel,
    NotificationStatus,
)
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.core.logging import get_logger
from app.core.security import generate_response_token
from app.db.models.blood_center import BloodCenter
from app.db.models.blood_request import BloodRequest
from app.db.models.donor_profile import DonorProfile
from app.db.models.donor_response import DonorResponse
from app.db.models.notification import Notification
from app.services.matching_service import (
    CompatibilityPolicy,
    MatchingResult,
    MatchingService,
    build_compatibility_policy,
)
from app.services.maps_service import MapsProvider, build_maps_provider
from app.services.sms_service import SmsProvider, build_dispatch_message, build_sms_provider

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DispatchPlan:
    dispatch_id: UUID
    request_id: UUID
    candidate_count: int
    first_batch_size: int
    batch_count: int
    notification_ids: list[UUID]


@dataclass(slots=True)
class NotificationService:
    db: Session
    sms: SmsProvider
    maps: MapsProvider
    policy: CompatibilityPolicy
    config: Settings
    response_url_builder: Any = None

    @classmethod
    def build(cls, db: Session, config: Settings | None = None) -> "NotificationService":
        config = config or settings
        return cls(
            db=db,
            sms=build_sms_provider(config),
            maps=build_maps_provider(config),
            policy=build_compatibility_policy(config),
            config=config,
        )

    # ------------------------------------------------------------------ dispatch

    def plan_dispatch(self, request_id: UUID) -> DispatchPlan:
        matching = MatchingService(self.db, self.maps, self.policy, self.config)
        request, inp = matching.candidates_for_request(request_id)
        result: MatchingResult = matching.run(inp)
        dispatchable = result.dispatchable
        if not dispatchable:
            raise Conflict(
                "کاندیدای قابل فراخوان با داده تأییدشده یافت نشد.",
                details=[{"field": "candidates", "message": "empty"}],
            )

        batch_size = max(1, self.config.dispatch_batch_size)
        notifications: list[Notification] = []
        for position, candidate in enumerate(dispatchable):
            batch_number = position // batch_size + 1
            notification = self._create_notification(request, candidate.donor_id, batch_number)
            if notification is not None:
                notifications.append(notification)

        if notifications:
            self.db.flush()

        first_batch = [n for n in notifications if n.batch_number == 1]
        dispatch_id = uuid4()
        logger.info(
            "dispatch_planned",
            extra={
                "request_id": str(request.id),
                "dispatch_id": str(dispatch_id),
                "candidate_count": len(dispatchable),
                "batch_count": math.ceil(len(dispatchable) / batch_size),
            },
        )
        return DispatchPlan(
            dispatch_id=dispatch_id,
            request_id=request.id,
            candidate_count=len(dispatchable),
            first_batch_size=len(first_batch),
            batch_count=math.ceil(len(dispatchable) / batch_size),
            notification_ids=[n.id for n in notifications],
        )

    def _create_notification(
        self, request: BloodRequest, donor_id: UUID, batch_number: int
    ) -> Notification | None:
        """Idempotent per (request, donor, stage) - existing rows are reused (DSP-03)."""
        key = Notification.build_idempotency_key(request.id, donor_id, batch_number)
        existing = self.db.scalar(select(Notification).where(Notification.idempotency_key == key))
        if existing is not None:
            return None
        donor = self.db.get(DonorProfile, donor_id)
        if donor is None:
            return None
        notification = Notification(
            request_id=request.id,
            donor_id=donor.id,
            channel=NotificationChannel.SMS,
            status=NotificationStatus.QUEUED,
            idempotency_key=key,
            batch_number=batch_number,
            response_token=generate_response_token(),
        )
        try:
            with self.db.begin_nested():
                self.db.add(notification)
                self.db.flush()
        except IntegrityError:
            # A concurrent planner won the race for this key; keep its row, lose none.
            return None
        return notification

    def send_batch(self, request_id: UUID, batch_number: int, *, now: datetime | None = None) -> int:
        """Send one staged batch; returns how many messages left the queue."""
        moment = now or datetime.now(UTC)
        request = self.get_request(request_id)
        if request.is_terminal:
            logger.info("dispatch_batch_skipped", extra={"request_id": str(request_id)})
            return 0
        if request.status is not BloodRequestStatus.ACTIVE:
            logger.info(
                "dispatch_batch_not_active",
                extra={"request_id": str(request_id), "status": request.status.value},
            )
            return 0
        if request.is_expired(moment):
            self.expire_request(request)
            return 0
        if self.is_fulfilled(request_id, request):
            return 0

        center = self.db.get(BloodCenter, request.center_id)
        if center is None:
            raise NotFound("مرکز این درخواست یافت نشد.")

        rows = self.db.scalars(
            select(Notification)
            .where(
                Notification.request_id == request_id,
                Notification.batch_number == batch_number,
                Notification.status == NotificationStatus.QUEUED,
            )
            .order_by(Notification.created_at)
        ).all()

        sent = 0
        for notification in rows:
            if self._send_one(notification, center):
                sent += 1
        self.db.commit()
        return sent

    def _send_one(self, notification: Notification, center: BloodCenter) -> bool:
        donor = self.db.get(DonorProfile, notification.donor_id)
        if donor is None:
            notification.transition_to(NotificationStatus.FAILED)
            notification.failure_reason = "donor_missing"
            return False
        user_phone = donor.user.phone
        body = build_dispatch_message(center.name, self.response_url(notification))
        result = self.sms.send(user_phone, body)
        if result.accepted:
            notification.provider_message_id = result.provider_message_id
            notification.transition_to(NotificationStatus.SENT)
            return True
        notification.transition_to(NotificationStatus.FAILED)
        notification.failure_reason = result.failure_reason or "provider_rejected"
        notification.retry_count += 1
        return False

    def response_url(self, notification: Notification) -> str:
        if self.response_url_builder is not None:
            return self.response_url_builder(notification)
        token = notification.response_token or ""
        return f"{self.config.public_app_base_url}/pages/respond.html?token={token}"

    # ------------------------------------------------------------------ stop conditions

    def cancel_pending(self, request_id: UUID, reason: str) -> int:
        """Cancel every not-yet-sent notification of a request (DSP-04)."""
        rows = self.db.scalars(
            select(Notification).where(
                Notification.request_id == request_id,
                Notification.status == NotificationStatus.QUEUED,
            )
        ).all()
        for notification in rows:
            notification.transition_to(NotificationStatus.CANCELLED)
            notification.failure_reason = reason
        self.db.commit()
        return len(rows)

    def expire_request(self, request: BloodRequest) -> BloodRequest:
        if request.status is BloodRequestStatus.EXPIRED:
            return request
        request.transition_to(BloodRequestStatus.EXPIRED)
        self.cancel_pending(request.id, "request_expired")
        self.db.commit()
        return request

    def mark_fulfilled(self, request: BloodRequest) -> BloodRequest:
        if request.status is BloodRequestStatus.FULFILLED:
            return request
        request.transition_to(BloodRequestStatus.FULFILLED)
        self.cancel_pending(request.id, "request_fulfilled")
        self.db.commit()
        return request

    def is_fulfilled(self, request_id: UUID, request: BloodRequest | None = None) -> bool:
        """Enough `interested` answers stops the call (section 1.1 step 9)."""
        target = request or self.get_request(request_id)
        if target.status in (BloodRequestStatus.FULFILLED,):
            return True
        interested = self.db.scalar(
            select(func.count(DonorResponse.id))
            .join(Notification, Notification.id == DonorResponse.notification_id)
            .where(
                Notification.request_id == request_id,
                DonorResponse.response == DonorResponseType.INTERESTED,
            )
        )
        if (interested or 0) >= target.units_needed and target.status is BloodRequestStatus.ACTIVE:
            self.mark_fulfilled(target)
            return True
        return False

    def pending_batch_numbers(self, request_id: UUID) -> list[int]:
        """Batch numbers still holding queued notifications, ascending."""
        rows = self.db.scalars(
            select(Notification.batch_number)
            .where(
                Notification.request_id == request_id,
                Notification.status == NotificationStatus.QUEUED,
            )
            .distinct()
            .order_by(Notification.batch_number)
        ).all()
        return list(rows)

    def expire_overdue(self, *, now: datetime | None = None) -> int:
        """Beat task work: close requests past `expires_at` and stop their queues."""
        moment = now or datetime.now(UTC)
        overdue = self.db.scalars(
            select(BloodRequest).where(
                BloodRequest.status == BloodRequestStatus.ACTIVE,
                BloodRequest.expires_at <= moment,
            )
        ).all()
        for request in overdue:
            self.expire_request(request)
        return len(overdue)

    def advance_due_batches(self, *, now: datetime | None = None) -> list[tuple[UUID, int]]:
        """Sections 11.3 step 8 and 12.1: release stage N+1 once the response window passed.

        The decision is derived from stored notification state, so a worker restart
        cannot lose the schedule or skip a stage.
        """
        moment = now or datetime.now(UTC)
        window = timedelta(minutes=self.config.dispatch_response_window_minutes)
        active = self.db.scalars(
            select(BloodRequest).where(BloodRequest.status == BloodRequestStatus.ACTIVE)
        ).all()

        due: list[tuple[UUID, int]] = []
        for request in active:
            if request.is_expired(moment):
                continue
            pending = self.pending_batch_numbers(request.id)
            if not pending:
                continue
            last_send_at = self.db.scalar(
                select(func.max(Notification.updated_at)).where(
                    Notification.request_id == request.id,
                    Notification.status.in_(
                        (NotificationStatus.SENT, NotificationStatus.DELIVERED)
                    ),
                )
            )
            if last_send_at is not None and moment - last_send_at >= window:
                due.append((request.id, min(pending)))
        return due

    # ------------------------------------------------------------------ responses

    def get_request(self, request_id: UUID) -> BloodRequest:
        request = self.db.get(BloodRequest, request_id)
        if request is None:
            raise NotFound("درخواست خون یافت نشد.")
        return request

    def record_response(
        self,
        *,
        notification_id: UUID,
        donor_id: UUID,
        response: DonorResponseType,
        eta_minutes: int | None = None,
        now: datetime | None = None,
    ) -> DonorResponse:
        """Section 9.12: one final answer per notification, only by its own donor."""
        notification = self.db.get(Notification, notification_id)
        if notification is None:
            raise NotFound("اعلان یافت نشد.")
        if notification.donor_id != donor_id:
            raise Forbidden("این اعلان برای داوطلب دیگری ارسال شده است.")
        if notification.response is not None:
            raise Conflict(
                "برای این اعلان پاسخ نهایی ثبت شده است.",
                details=[{"field": "response", "message": "already_answered"}],
            )

        donor_response = DonorResponse(
            notification_id=notification.id,
            response=response,
            eta_minutes=eta_minutes,
            responded_at=now or datetime.now(UTC),
        )
        self.db.add(donor_response)
        self.db.flush()
        fulfilled = self.is_fulfilled(notification.request_id)
        self.db.commit()
        logger.info(
            "donor_response_recorded",
            extra={
                "notification_id": str(notification.id),
                "response": str(response),
                "request_fulfilled": bool(fulfilled),
            },
        )
        return donor_response
