"""Donor notification list and response submission (sections 9.12, 8 and 15)."""

from uuid import UUID

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.core.dependencies import DatabaseSession, DonorUser, PageParams
from app.db.models.donor_profile import DonorProfile
from app.db.models.notification import Notification
from app.schemas.common import envelope, paginated
from app.schemas.notification import (
    DonorResponseOut,
    NotificationOut,
    NotificationResponseIn,
    NotificationResponseOut,
)
from app.services.donor_service import ensure_donor_profile
from app.services.notification_service import NotificationService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _to_out(notification: Notification) -> NotificationOut:
    request = notification.request
    center = request.center
    return NotificationOut(
        id=notification.id,
        request_id=request.id,
        channel=notification.channel,
        status=notification.status,
        created_at=notification.created_at,
        center_id=center.id,
        center_name=center.name,
        component_type=request.component_type,
        blood_group=request.blood_group,
        rh_factor=request.rh_factor,
        urgency=request.urgency,
        expires_at=request.expires_at,
        response=DonorResponseOut.model_validate(notification.response)
        if notification.response
        else None,
    )


@router.get("", summary="اعلان‌های داوطلب جاری")
def list_donor_notifications(
    user: DonorUser,
    db: DatabaseSession,
    page_params: PageParams,
) -> dict:
    page, page_size = page_params
    base = select(Notification).join(DonorProfile, DonorProfile.id == Notification.donor_id).where(
        DonorProfile.user_id == user.id
    )
    total = db.scalar(
        select(func.count(Notification.id))
        .join(DonorProfile, DonorProfile.id == Notification.donor_id)
        .where(DonorProfile.user_id == user.id)
    )
    rows = db.scalars(
        base.order_by(Notification.created_at.desc(), Notification.id).offset(
            (page - 1) * page_size
        ).limit(page_size)
    ).all()
    return paginated(
        [_to_out(row).model_dump(mode="json") for row in rows],
        page=page,
        page_size=page_size,
        total=int(total or 0),
    )


@router.post(
    "/{notification_id}/response",
    status_code=status.HTTP_201_CREATED,
    summary="ثبت پاسخ داوطلب به فراخوان",
)
def respond_to_notification(
    notification_id: UUID,
    payload: NotificationResponseIn,
    user: DonorUser,
    db: DatabaseSession,
) -> dict:
    profile = ensure_donor_profile(db, user)
    donor_response = NotificationService.build(db).record_response(
        notification_id=notification_id,
        donor_id=profile.id,
        response=payload.response,
        eta_minutes=payload.eta_minutes,
    )
    return envelope(
        NotificationResponseOut(
            notification_id=donor_response.notification_id,
            response=donor_response.response,
            responded_at=donor_response.responded_at,
        ).model_dump(mode="json")
    )
