"""Blood centre endpoints contributed by Asra."""
from math import asin, cos, radians, sin, sqrt
from uuid import UUID
from fastapi import APIRouter, Query
from sqlalchemy import func, select
from app.core.dependencies import CurrentUser, DatabaseSession, PageParams, assert_center_access
from app.core.enums import UserRole
from app.core.exceptions import BadRequest, Conflict, Forbidden, NotFound
from app.db.models.blood_center import BloodCenter
from app.db.models.user import User
from app.schemas.center import CenterCreate, CenterUpdate
from app.schemas.common import envelope, paginated
from app.services.audit_service import AuditService

router = APIRouter(prefix="/centers", tags=["centers"])

def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat, dlon = radians(lat2-lat1), radians(lon2-lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 6371.0 * 2 * asin(sqrt(a))

def _payload(center: BloodCenter, *, distance_km: float | None = None, can_manage: bool = False) -> dict:
    data = {"id": str(center.id), "name": center.name, "address": center.address,
            "latitude": float(center.latitude), "longitude": float(center.longitude),
            "phone": center.phone, "opening_hours": center.opening_hours, "is_active": center.is_active}
    if distance_km is not None: data["distance_km"] = round(distance_km, 2)
    if can_manage: data["is_verified"] = center.is_verified
    return data

@router.get("", summary="List active centres")
def list_centers(user: CurrentUser, db: DatabaseSession, page_params: PageParams,
                 latitude: float | None = Query(default=None, ge=-90, le=90),
                 longitude: float | None = Query(default=None, ge=-180, le=180),
                 radius_km: float | None = Query(default=None, ge=0, le=500)) -> dict:
    if (latitude is None) != (longitude is None):
        raise BadRequest("Latitude and longitude must be sent together.")
    page, page_size = page_params
    stmt = select(BloodCenter).where(BloodCenter.is_active.is_(True)).order_by(BloodCenter.name)
    centers = db.scalars(stmt).all()
    if latitude is None:
        total = len(centers)
        rows = centers[(page-1)*page_size:page*page_size]
        return paginated([_payload(c) for c in rows], page=page, page_size=page_size, total=total)
    scored = [(_distance_km(latitude, longitude, float(c.latitude), float(c.longitude)), c) for c in centers]
    if radius_km is not None: scored = [(d,c) for d,c in scored if d <= radius_km]
    scored.sort(key=lambda item: item[0])
    window = scored[(page-1)*page_size:page*page_size]
    return paginated([_payload(c, distance_km=d) for d,c in window], page=page, page_size=page_size, total=len(scored))

@router.get("/{center_id}", summary="Centre details")
def get_center(center_id: UUID, user: CurrentUser, db: DatabaseSession) -> dict:
    center = db.get(BloodCenter, center_id)
    if center is None: raise NotFound("Blood centre not found.")
    can_manage = user.role == UserRole.ADMIN or (user.role == UserRole.CENTER_OPERATOR and center.owner_user_id == user.id)
    if not center.is_active and not can_manage: raise NotFound("Blood centre not found.")
    return envelope(_payload(center, can_manage=can_manage))

@router.post("", status_code=201, summary="Create a centre (system admin)")
def create_center(payload: CenterCreate, user: CurrentUser, db: DatabaseSession) -> dict:
    if user.role != UserRole.ADMIN: raise Forbidden()
    data = payload.model_dump()
    owner_user_id = data.pop("owner_user_id", None)
    if owner_user_id is not None:
        owner = db.get(User, owner_user_id)
        if owner is None or owner.role != UserRole.CENTER_OPERATOR:
            raise BadRequest("The centre owner must be a valid center_operator account.")
    center = BloodCenter(**data, owner_user_id=owner_user_id)
    db.add(center); db.flush()
    AuditService(db).record(action="center_created", entity_type="blood_center", actor_id=user.id, entity_id=center.id, details={"name":center.name})
    db.commit(); db.refresh(center)
    return envelope(_payload(center, can_manage=True))

@router.patch("/{center_id}", summary="Edit a centre")
def update_center(center_id: UUID, payload: CenterUpdate, user: CurrentUser, db: DatabaseSession) -> dict:
    center = db.get(BloodCenter, center_id)
    if center is None: raise NotFound("Blood centre not found.")
    is_admin = user.role == UserRole.ADMIN
    if not is_admin and not (user.role == UserRole.CENTER_OPERATOR and center.owner_user_id == user.id): raise Forbidden()
    updates = payload.model_dump(exclude_unset=True)
    if not is_admin and ({"is_verified", "is_active"} & updates.keys()): raise Forbidden("Only an admin can change the verification or activation status.")
    for key, value in updates.items(): setattr(center, key, value)
    AuditService(db).record(action="center_updated", entity_type="blood_center", actor_id=user.id, entity_id=center.id, details={"fields":sorted(updates)})
    db.commit(); db.refresh(center)
    return envelope(_payload(center, can_manage=True))
