"""Rule-based, explainable Matching service (contract section 11).

The service never decides medical eligibility: it filters on consented, verifiable
account data, estimates travel time through the maps adapter, and ranks candidates.
Compatibility rules come from a policy object that is label-only until an authorised
source exists (section 11.3 step 5).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.enums import (
    AvailabilityStatus,
    BloodGroup,
    BloodRequestStatus,
    ComponentType,
    EligibilityCheckStatus,
    RhFactor,
)
from app.core.exceptions import Conflict, Forbidden, NotFound
from app.core.logging import get_logger
from app.db.models.blood_center import BloodCenter
from app.db.models.blood_request import BloodRequest
from app.db.models.donor_availability import DonorAvailability
from app.db.models.donor_location import DonorLocation
from app.db.models.donor_profile import DonorProfile
from app.db.models.user import User
from app.services.maps_service import (
    Coordinate,
    MapsProvider,
    RouteEstimate,
    estimate_route,
)

logger = get_logger(__name__)

DEMO_POLICY = "demo"


@dataclass(frozen=True, slots=True)
class MatchingInput:
    request_id: UUID
    center_id: UUID
    component_type: ComponentType
    blood_group: BloodGroup
    rh_factor: RhFactor
    max_candidates: int
    batch_size: int


@dataclass(frozen=True, slots=True)
class MatchingCandidate:
    donor_id: UUID
    eta_minutes: int | None
    distance_km: float | None
    eligibility_check_status: EligibilityCheckStatus
    rank: int
    location_updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class MatchingResult:
    candidates: tuple[MatchingCandidate, ...]

    @property
    def dispatchable(self) -> list[MatchingCandidate]:
        """Only fully verified data may be auto-called (section 11.3 step 3)."""
        return [
            candidate
            for candidate in self.candidates
            if candidate.eligibility_check_status is EligibilityCheckStatus.VERIFIED_DATA
        ]

    @property
    def needs_review(self) -> list[MatchingCandidate]:
        return [
            candidate
            for candidate in self.candidates
            if candidate.eligibility_check_status is EligibilityCheckStatus.NEEDS_REVIEW
        ]


class CompatibilityPolicy(Protocol):
    name: str

    def matches(self, request: BloodRequest, profile: DonorProfile) -> bool: ...


@dataclass(frozen=True, slots=True)
class DemoDeclaredTypePolicy:
    """Label-only demo rule on synthetic contest data: the request declares one type.

    NOT a medical compatibility rule. Real routing must come from the centre or an
    authorised reference before dispatch is enabled for production.
    """

    name: str = DEMO_POLICY

    def matches(self, request: BloodRequest, profile: DonorProfile) -> bool:
        if profile.blood_group is None or profile.rh_factor is None:
            return False
        return profile.blood_group == request.blood_group and profile.rh_factor == request.rh_factor


class DispatchNotConfigured(Conflict):
    def __init__(self) -> None:
        super().__init__(
            "قواعد رسمی سازگاری فرآورده/گروه پیکربندی نشده است؛ فقط حالت demo فعال است.",
            details=[{"field": "compatibility_policy", "message": "official source required"}],
        )


def build_compatibility_policy(config: Settings | None = None) -> CompatibilityPolicy:
    config = config or settings
    if config.compatibility_policy.lower() == DEMO_POLICY:
        return DemoDeclaredTypePolicy()
    # Section 11.3 step 5: no official rules source configured -> real dispatch stays off.
    raise DispatchNotConfigured()


@dataclass(slots=True)
class MatchingService:
    db: Session
    maps: MapsProvider
    policy: CompatibilityPolicy
    config: Settings | None = None

    def candidates_for_request(self, request_id: UUID) -> tuple[BloodRequest, MatchingInput]:
        config = self.config or settings
        request = self.db.get(BloodRequest, request_id)
        if request is None:
            raise NotFound("درخواست خون یافت نشد.")
        if request.status is not BloodRequestStatus.ACTIVE:
            raise Conflict(
                "فقط درخواست در وضعیت active قابل فراخوان است.",
                details=[{"field": "status", "message": request.status.value}],
            )
        center = self.db.get(BloodCenter, request.center_id)
        if center is None:
            raise NotFound("مرکز این درخواست یافت نشد.")
        if not center.accepts_new_requests():
            raise Forbidden("مرکز هنوز تأیید نشده یا غیرفعال است.")

        inp = MatchingInput(
            request_id=request.id,
            center_id=center.id,
            component_type=request.component_type,
            blood_group=request.blood_group,
            rh_factor=request.rh_factor,
            max_candidates=config.dispatch_max_candidates,
            batch_size=config.dispatch_batch_size,
        )
        return request, inp

    def run(self, inp: MatchingInput, *, now: datetime | None = None) -> MatchingResult:
        moment = now or datetime.now(UTC)
        center = self.db.get(BloodCenter, inp.center_id)
        if center is None:
            raise NotFound("مرکز این درخواست یافت نشد.")
        request = self.db.get(BloodRequest, inp.request_id)
        if request is None:
            raise NotFound("درخواست خون یافت نشد.")

        rows = self.db.scalars(self._candidate_query(inp, moment)).all()
        destination = Coordinate.from_decimals(center.latitude, center.longitude)

        scored: list[tuple[EligibilityCheckStatus, RouteEstimate, DonorProfile]] = []
        for profile in rows:
            if not self.policy.matches(request, profile):
                continue
            location = profile.location
            if location is None or location.latitude is None or location.longitude is None:
                continue
            estimate = estimate_route(
                self.maps,
                Coordinate.from_decimals(location.latitude, location.longitude),
                destination,
            )
            status = (
                EligibilityCheckStatus.VERIFIED_DATA
                if profile.blood_type_verified
                else EligibilityCheckStatus.NEEDS_REVIEW
            )
            scored.append((status, estimate, profile))

        verified = self._rank(scored, EligibilityCheckStatus.VERIFIED_DATA, inp.max_candidates, 0)
        remaining = inp.max_candidates - len(verified)
        review = (
            self._rank(scored, EligibilityCheckStatus.NEEDS_REVIEW, remaining, len(verified))
            if remaining > 0
            else []
        )
        candidates = tuple(verified + review)
        logger.info(
            "matching_completed",
            extra={
                "request_id": str(inp.request_id),
                "candidate_count": len(candidates),
                "dispatchable_count": len([c for c in candidates if c.eligibility_check_status is EligibilityCheckStatus.VERIFIED_DATA]),
                "policy": self.policy.name,
            },
        )
        return MatchingResult(candidates=candidates)

    def _candidate_query(self, inp: MatchingInput, moment: datetime):
        return (
            select(DonorProfile)
            .join(User, User.id == DonorProfile.user_id)
            .join(DonorAvailability, DonorAvailability.donor_id == DonorProfile.id)
            .join(DonorLocation, DonorLocation.donor_id == DonorProfile.id)
            .where(
                User.is_active.is_(True),
                DonorProfile.sms_consent.is_(True),
                DonorProfile.location_consent.is_(True),
                DonorProfile.blood_group == inp.blood_group,
                DonorProfile.rh_factor == inp.rh_factor,
                DonorAvailability.status == AvailabilityStatus.AVAILABLE,
                (DonorAvailability.available_from.is_(None))
                | (DonorAvailability.available_from <= moment),
                (DonorAvailability.available_until.is_(None))
                | (DonorAvailability.available_until >= moment),
            )
        )

    @staticmethod
    def _rank(
        scored: list[tuple[EligibilityCheckStatus, RouteEstimate, DonorProfile]],
        bucket: EligibilityCheckStatus,
        limit: int,
        rank_offset: int,
    ) -> list[MatchingCandidate]:
        members = [entry for entry in scored if entry[0] is bucket]
        # Section 11.3 step 7: ETA first, then distance, then location freshness for a stable rank.
        members.sort(key=lambda entry: _sort_key(entry[1], entry[2]))
        return [
            MatchingCandidate(
                donor_id=profile.id,
                eta_minutes=estimate.eta_minutes,
                distance_km=estimate.distance_km,
                eligibility_check_status=bucket,
                rank=rank_offset + position,
                location_updated_at=profile.location.updated_at if profile.location else None,
            )
            for position, (_, estimate, profile) in enumerate(members[: max(0, limit)], start=1)
        ]


def _sort_key(estimate: RouteEstimate, profile: DonorProfile) -> tuple[float, float, float]:
    location = profile.location
    updated = location.updated_at.timestamp() if location and location.updated_at else 0.0
    eta = estimate.eta_minutes if estimate.eta_minutes is not None else float("inf")
    distance = estimate.distance_km if estimate.distance_km is not None else float("inf")
    return (eta, distance, -updated)
