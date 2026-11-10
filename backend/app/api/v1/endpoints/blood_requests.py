"""Blood request lifecycle endpoints contributed by Asra.
Dispatch and candidate routes remain in the existing dispatch.py module owned by the team.
"""
from datetime import UTC, datetime
from uuid import UUID
from fastapi import APIRouter
from sqlalchemy import func, select
from app.core.dependencies import CurrentUser, DatabaseSession, PageParams, assert_center_access
from app.core.enums import BloodGroup, BloodRequestStatus, ComponentType, NotificationStatus, RequestUrgency, UserRole
from app.core.exceptions import BadRequest, Conflict, Forbidden, NotFound
from app.db.models.blood_center import BloodCenter
from app.db.models.blood_request import BloodRequest
from app.db.models.donor_response import DonorResponse
from app.db.models.notification import Notification
from app.db.models.user import User
from app.schemas.blood_request import BloodRequestCreate, BloodRequestUpdate
from app.schemas.common import envelope, paginated, to_iso_zulu
from app.services.audit_service import AuditService
from app.api.v1.endpoints.dispatch import donor_reference

router = APIRouter(prefix="/blood-requests", tags=["blood-requests"])

def _request_out(row: BloodRequest, include_notes: bool = False) -> dict:
    data = {"id":str(row.id), "center_id":str(row.center_id), "component_type":row.component_type.value,
            "blood_group":row.blood_group.value, "rh_factor":row.rh_factor.value,
            "units_needed":row.units_needed, "urgency":row.urgency.value, "status":row.status.value,
            "expires_at":to_iso_zulu(row.expires_at), "created_at":to_iso_zulu(row.created_at),
            "updated_at":to_iso_zulu(row.updated_at), "activated_at":to_iso_zulu(row.activated_at),
            "center":{"id":str(row.center.id),"name":row.center.name,"address":row.center.address}}
    if include_notes: data["notes"] = row.notes
    return data

def _owned_request(db: DatabaseSession, request_id: UUID, user: User) -> BloodRequest:
    row = db.get(BloodRequest, request_id)
    if row is None: raise NotFound("درخواست خون یافت نشد.")
    assert_center_access(db, user, row.center_id)
    return row

@router.post("", status_code=201, summary="ایجاد درخواست خون (پیش‌نویس)")
def create_blood_request(payload: BloodRequestCreate, user: CurrentUser, db: DatabaseSession) -> dict:
    if user.role != UserRole.CENTER_OPERATOR: raise Forbidden()
    center = assert_center_access(db, user, payload.center_id)
    if not center.is_active: raise Conflict("مرکز غیرفعال است.")
    if payload.expires_at <= datetime.now(UTC): raise BadRequest("زمان انقضا باید در آینده باشد.")
    row = BloodRequest(center_id=center.id, component_type=payload.component_type, blood_group=payload.blood_group,
        rh_factor=payload.rh_factor, units_needed=payload.units_needed, urgency=payload.urgency,
        status=BloodRequestStatus.DRAFT, expires_at=payload.expires_at, notes=payload.notes, created_by=user.id)
    db.add(row); db.flush()
    AuditService(db).record(action="blood_request_created", entity_type="blood_request", actor_id=user.id, entity_id=row.id)
    db.commit(); db.refresh(row)
    return envelope(_request_out(row, True))

@router.get("", summary="فهرست درخواست‌های خون")
def list_blood_requests(user: CurrentUser, db: DatabaseSession, page_params: PageParams,
                        status_filter: BloodRequestStatus | None = None, center_id: UUID | None = None,
                        component_type: ComponentType | None = None, blood_group: BloodGroup | None = None,
                        urgency: RequestUrgency | None = None) -> dict:
    page, page_size = page_params
    stmt = select(BloodRequest)
    include_notes = user.role != UserRole.DONOR
    if user.role == UserRole.DONOR: stmt = stmt.where(BloodRequest.status == BloodRequestStatus.ACTIVE)
    elif user.role == UserRole.CENTER_OPERATOR:
        owned_ids = select(BloodCenter.id).where(BloodCenter.owner_user_id == user.id)
        stmt = stmt.where(BloodRequest.center_id.in_(owned_ids))
    if center_id is not None and user.role != UserRole.CENTER_OPERATOR: stmt = stmt.where(BloodRequest.center_id == center_id)
    if status_filter is not None and user.role != UserRole.DONOR: stmt = stmt.where(BloodRequest.status == status_filter)
    if component_type: stmt = stmt.where(BloodRequest.component_type == component_type)
    if blood_group: stmt = stmt.where(BloodRequest.blood_group == blood_group)
    if urgency: stmt = stmt.where(BloodRequest.urgency == urgency)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(BloodRequest.created_at.desc()).offset((page-1)*page_size).limit(page_size)).all()
    return paginated([_request_out(r, include_notes) for r in rows], page=page, page_size=page_size, total=total)

@router.get("/{request_id}", summary="جزئیات درخواست خون")
def get_blood_request(request_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    row = db.get(BloodRequest, request_id)
    if row is None: raise NotFound("درخواست خون یافت نشد.")
    if user.role == UserRole.DONOR:
        if row.status != BloodRequestStatus.ACTIVE: raise NotFound("درخواست خون یافت نشد.")
    else: assert_center_access(db, user, row.center_id)
    return envelope(_request_out(row, user.role != UserRole.DONOR))

@router.patch("/{request_id}", summary="ویرایش پیش‌نویس درخواست")
def update_blood_request(request_id: UUID, payload: BloodRequestUpdate, user: CurrentUser, db: DatabaseSession) -> dict:
    if user.role != UserRole.CENTER_OPERATOR: raise Forbidden()
    row = _owned_request(db, request_id, user)
    if row.status != BloodRequestStatus.DRAFT: raise Conflict("فقط درخواست پیش‌نویس قابل ویرایش است.")
    updates = payload.model_dump(exclude_unset=True)
    if "expires_at" in updates and updates["expires_at"] <= datetime.now(UTC): raise BadRequest("زمان انقضا باید در آینده باشد.")
    for key, value in updates.items(): setattr(row, key, value)
    AuditService(db).record(action="blood_request_updated", entity_type="blood_request", actor_id=user.id, entity_id=row.id, details={"fields":sorted(updates)})
    db.commit(); db.refresh(row)
    return envelope(_request_out(row, True))

@router.post("/{request_id}/activate", summary="فعال‌سازی درخواست")
def activate_blood_request(request_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    if user.role != UserRole.CENTER_OPERATOR: raise Forbidden()
    row = _owned_request(db, request_id, user)
    if row.status != BloodRequestStatus.DRAFT: raise Conflict("فقط درخواست پیش‌نویس قابل فعال‌سازی است.")
    center = db.get(BloodCenter, row.center_id)
    if center is None or not center.is_verified or not center.is_active: raise Conflict("مرکز باید تأییدشده و فعال باشد.")
    if row.expires_at <= datetime.now(UTC): raise Conflict("زمان اعتبار درخواست به پایان رسیده است.")
    row.transition_to(BloodRequestStatus.ACTIVE)
    AuditService(db).record(action="blood_request_activated", entity_type="blood_request", actor_id=user.id, entity_id=row.id)
    db.commit(); db.refresh(row)
    return envelope(_request_out(row, True))

@router.post("/{request_id}/cancel", summary="لغو درخواست")
def cancel_blood_request(request_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    if user.role != UserRole.CENTER_OPERATOR: raise Forbidden()
    row = _owned_request(db, request_id, user)
    if row.status not in (BloodRequestStatus.DRAFT, BloodRequestStatus.ACTIVE): raise Conflict("این درخواست قابل لغو نیست.")
    row.transition_to(BloodRequestStatus.CANCELLED)
    queued = db.scalars(select(Notification).where(Notification.request_id == row.id, Notification.status == NotificationStatus.QUEUED)).all()
    for notification in queued: notification.transition_to(NotificationStatus.CANCELLED)
    AuditService(db).record(action="blood_request_cancelled", entity_type="blood_request", actor_id=user.id, entity_id=row.id)
    db.commit(); db.refresh(row)
    return envelope(_request_out(row, True))

@router.get("/{request_id}/responses", summary="پاسخ‌های داوطلبان به فراخوان")
def list_responses(request_id: UUID, user: CurrentUser, db: DatabaseSession, page_params: PageParams) -> dict:
    row = _owned_request(db, request_id, user)
    page, page_size = page_params
    stmt = select(DonorResponse).join(Notification, DonorResponse.notification_id == Notification.id).where(Notification.request_id == row.id)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    responses = db.scalars(stmt.order_by(DonorResponse.responded_at.desc()).offset((page-1)*page_size).limit(page_size)).all()
    data = [{"donor_reference":donor_reference(response.donor_id), "response":response.response.value,
             "responded_at":to_iso_zulu(response.responded_at), "eta_minutes":response.eta_minutes} for response in responses]
    return paginated(data, page=page, page_size=page_size, total=total)
