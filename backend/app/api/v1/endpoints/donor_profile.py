"""``PATCH /donors/me/profile`` - donor self-service profile and consents (section 9.4)."""

from fastapi import APIRouter

from app.core.dependencies import DatabaseSession, DonorUser
from app.schemas.common import envelope
from app.schemas.donor import DonorProfileOut, DonorProfilePatch
from app.services.audit_service import AuditService
from app.services.donor_service import apply_profile_patch, ensure_donor_profile

router = APIRouter(prefix="/donors/me", tags=["donors"])


def to_profile_out(profile) -> DonorProfileOut:
    return DonorProfileOut(
        donor_id=profile.id,
        blood_group=profile.blood_group,
        rh_factor=profile.rh_factor,
        blood_type_verified=profile.blood_type_verified,
        last_donation_date=profile.last_donation_date,
        sms_consent=profile.sms_consent,
        location_consent=profile.location_consent,
    )


@router.patch("/profile", summary="Complete the donor profile")
def patch_donor_profile(
    payload: DonorProfilePatch,
    user: DonorUser,
    db: DatabaseSession,
) -> dict:
    profile = ensure_donor_profile(db, user)
    profile = apply_profile_patch(db, profile, payload)
    AuditService(db).record(
        action="donor_profile_updated",
        entity_type="donor_profile",
        actor_id=user.id,
        entity_id=profile.id,
        details={"fields": sorted(payload.model_dump(exclude_unset=True))},
    )
    db.commit()
    return envelope(to_profile_out(profile).model_dump(mode="json"))
