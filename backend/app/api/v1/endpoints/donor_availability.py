"""Donor availability endpoint contributed by Asra."""
from fastapi import APIRouter
from app.core.dependencies import DatabaseSession, DonorUser
from app.core.enums import AvailabilityStatus
from app.schemas.donor_availability import AvailabilityUpdate
from app.db.models.donor_availability import DonorAvailability
from app.schemas.common import envelope, to_iso_zulu
from app.services.audit_service import AuditService
from app.services.donor_service import ensure_donor_profile

router = APIRouter(prefix="/donors", tags=["donors"])

@router.patch("/me/availability", summary="Set the donor's availability status")
def update_availability(payload: AvailabilityUpdate, user: DonorUser, db: DatabaseSession) -> dict:
    donor = ensure_donor_profile(db, user)
    availability = donor.availability
    if availability is None:
        availability = DonorAvailability(donor_id=donor.id)
        db.add(availability)
    availability.status = payload.status
    availability.available_from = payload.available_from if payload.status == AvailabilityStatus.AVAILABLE else None
    availability.available_until = payload.available_until if payload.status == AvailabilityStatus.AVAILABLE else None
    db.flush()
    AuditService(db).record(action="donor_availability_updated", entity_type="donor_availability", actor_id=user.id, entity_id=availability.id, details={"status":payload.status.value})
    db.commit(); db.refresh(availability)
    return envelope({"donor_id":str(donor.id), "status":availability.status.value,
                     "available_from":to_iso_zulu(availability.available_from),
                     "available_until":to_iso_zulu(availability.available_until),
                     "updated_at":to_iso_zulu(availability.updated_at)})
