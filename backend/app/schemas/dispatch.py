"""Dispatch and candidate shapes (sections 9.10 and 9.11)."""

from uuid import UUID

from pydantic import BaseModel

from app.core.enums import EligibilityCheckStatus, NotificationStatus


class DispatchAcceptedOut(BaseModel):
    dispatch_id: UUID
    request_id: UUID
    status: NotificationStatus
    candidate_count: int
    first_batch_size: int


class CandidateOut(BaseModel):
    """Section 9.11 - never exposes donor name, phone number or raw coordinates."""

    donor_reference: str
    eta_minutes: int | None
    distance_km: float | None
    eligibility_check_status: EligibilityCheckStatus
    dispatch_stage: int | None = None
