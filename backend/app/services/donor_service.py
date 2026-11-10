"""Donor self-service rules shared by profile, location and availability endpoints."""

from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.exceptions import Forbidden
from app.db.models.donor_location import DonorLocation
from app.db.models.donor_profile import DonorProfile
from app.db.models.user import User
from app.schemas.donor import DonorProfilePatch

# Writable by the donor themselves; `blood_type_verified` is never here (section 9.4).
DONOR_EDITABLE_FIELDS = ("blood_group", "rh_factor", "last_donation_date", "sms_consent", "location_consent")


def ensure_donor_profile(db: Session, user: User) -> DonorProfile:
    profile = user.donor_profile
    if profile is not None:
        return profile
    profile = DonorProfile(user_id=user.id)
    db.add(profile)
    db.flush()
    db.refresh(user)
    return profile


def apply_profile_patch(db: Session, profile: DonorProfile, payload: DonorProfilePatch) -> DonorProfile:
    """Ignore unset fields; a consent withdrawal immediately clears stored coordinates (9.6)."""
    updates = payload.model_dump(exclude_unset=True)
    for field in DONOR_EDITABLE_FIELDS:
        if field in updates:
            setattr(profile, field, updates[field])
    if updates.get("location_consent") is False:
        clear_location(db, profile)
    db.flush()
    return profile


def set_location(db: Session, profile: DonorProfile, latitude: Decimal, longitude: Decimal) -> DonorLocation:
    if not profile.location_consent:
        raise Forbidden(
            "Location processing consent must be enabled to save a location.",
        )
    location = profile.location or DonorLocation(donor_id=profile.id)
    location.latitude = latitude
    location.longitude = longitude
    db.add(location)
    db.flush()
    return location


def clear_location(db: Session, profile: DonorProfile) -> None:
    db.execute(delete(DonorLocation).where(DonorLocation.donor_id == profile.id))
    db.expire(profile)
