"""``PATCH /donors/me/location`` - consent-gated coordinate storage (section 9.6)."""

from fastapi import APIRouter

from app.core.dependencies import DatabaseSession, DonorUser
from app.schemas.common import envelope
from app.schemas.donor import DonorLocationOut, DonorLocationPatch
from app.services.audit_service import AuditService
from app.services.donor_service import ensure_donor_profile, set_location

router = APIRouter(prefix="/donors/me", tags=["donors"])


@router.patch("/location", summary="ثبت موقعیت فعلی داوطلب")
def patch_donor_location(
    payload: DonorLocationPatch,
    user: DonorUser,
    db: DatabaseSession,
) -> dict:
    profile = ensure_donor_profile(db, user)
    location = set_location(db, profile, payload.latitude, payload.longitude)
    # Coordinates are never logged or echoed to other users (sections 9.6 and 14).
    AuditService(db).record(
        action="donor_location_updated",
        entity_type="donor_location",
        actor_id=user.id,
        entity_id=location.id,
    )
    db.commit()
    return envelope(
        DonorLocationOut(
            donor_id=profile.id,
            latitude=location.latitude,
            longitude=location.longitude,
            updated_at=location.updated_at,
            location_consent=profile.location_consent,
        ).model_dump(mode="json")
    )
