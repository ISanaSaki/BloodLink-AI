"""Matching service unit scenarios (contract section 11.3)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.core.config import settings
from app.core.exceptions import Conflict, Forbidden
from app.core.enums import BloodGroup, ComponentType, EligibilityCheckStatus, RhFactor
from app.services.matching_service import (
    DemoDeclaredTypePolicy,
    MatchingInput,
    MatchingService,
)
from app.services.maps_service import MockMapsProvider

CENTER_LAT = Decimal("35.700000")
CENTER_LON = Decimal("51.400000")


@pytest.fixture
def matching(db):
    return MatchingService(db, MockMapsProvider(), DemoDeclaredTypePolicy(), settings)


def make_input(db, center, request, **overrides) -> MatchingInput:
    base = {
        "request_id": request.id,
        "center_id": center.id,
        "component_type": request.component_type,
        "blood_group": request.blood_group,
        "rh_factor": request.rh_factor,
        "max_candidates": settings.dispatch_max_candidates,
        "batch_size": settings.dispatch_batch_size,
    }
    base.update(overrides)
    return MatchingInput(**base)


def test_closer_donor_ranks_first(db, matching, center_factory, request_factory, donor_factory):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    near = donor_factory(latitude=Decimal("35.705000"), longitude=Decimal("51.405000"))
    far = donor_factory(latitude=Decimal("35.850000"), longitude=Decimal("51.550000"))

    result = matching.run(make_input(db, center, request))

    assert [c.donor_id for c in result.candidates] == [near.id, far.id]
    assert [c.rank for c in result.candidates] == [1, 2]
    assert result.candidates[0].eta_minutes < result.candidates[1].eta_minutes
    assert result.candidates[0].distance_km < result.candidates[1].distance_km


def test_donors_without_consent_are_excluded(db, matching, center_factory, request_factory, donor_factory):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_factory(sms_consent=False)
    donor_factory(location_consent=False)

    assert matching.run(make_input(db, center, request)).candidates == ()


def test_unverified_blood_type_goes_to_needs_review_bucket(
    db, matching, center_factory, request_factory, donor_factory
):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    verified = donor_factory()
    unverified = donor_factory(verified=False)

    result = matching.run(make_input(db, center, request))

    assert [c.donor_id for c in result.dispatchable] == [verified.id]
    assert [c.donor_id for c in result.needs_review] == [unverified.id]
    assert all(
        c.eligibility_check_status is EligibilityCheckStatus.NEEDS_REVIEW for c in result.needs_review
    )
    assert all(
        c.eligibility_check_status is EligibilityCheckStatus.VERIFIED_DATA for c in result.dispatchable
    )


def test_unavailable_donor_is_excluded(db, matching, center_factory, request_factory, donor_factory):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_factory(available=False)

    assert matching.run(make_input(db, center, request)).candidates == ()


def test_closed_availability_window_is_excluded(db, matching, center_factory, request_factory, donor_factory):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    profile = donor_factory()

    from app.db.models.donor_availability import DonorAvailability

    availability = db.query(DonorAvailability).filter_by(donor_id=profile.id).one()
    availability.available_until = datetime.now(UTC) - timedelta(minutes=5)
    db.commit()

    assert matching.run(make_input(db, center, request)).candidates == ()


def test_different_blood_group_is_excluded(db, matching, center_factory, request_factory, donor_factory):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active", blood_group="AB")
    donor_factory(blood_group="O")

    assert matching.run(make_input(db, center, request)).candidates == ()


def test_max_candidates_caps_the_result(db, matching, center_factory, request_factory, donor_factory):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    for _ in range(5):
        donor_factory()

    result = matching.run(make_input(db, center, request, max_candidates=2))

    assert len(result.candidates) == 2
    assert [c.rank for c in result.candidates] == [1, 2]


def test_donor_without_coordinates_is_not_ranked(db, matching, center_factory, request_factory, donor_factory):
    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_factory(latitude=None, longitude=None)

    assert matching.run(make_input(db, center, request)).candidates == ()


def test_draft_request_cannot_be_dispatched(db, center_factory, request_factory, matching):
    """DSP-01 at the service layer."""
    center, owner = center_factory()
    request = request_factory(center, owner, status="draft")

    with pytest.raises(Conflict):
        matching.candidates_for_request(request.id)


def test_unverified_center_is_refused(db, center_factory, request_factory, matching):
    center, owner = center_factory(verified=False)
    request = request_factory(center, owner, status="active")

    with pytest.raises(Forbidden):
        matching.candidates_for_request(request.id)


def test_unknown_request_raises_not_found(db, matching):
    import uuid

    from app.core.exceptions import NotFound

    with pytest.raises(NotFound):
        matching.candidates_for_request(uuid.uuid4())


def test_provider_failure_falls_back_to_distance(db, center_factory, request_factory, donor_factory):
    """Section 11.3 step 6: ETA loss must degrade to distance, not crash Matching."""
    from app.services.maps_service import MapsUnavailableError

    class BrokenMaps:
        name = "broken"

        def route(self, origin, destination):
            raise MapsUnavailableError("provider down")

    center, owner = center_factory()
    request = request_factory(center, owner, status="active")
    donor_factory()

    service = MatchingService(db, BrokenMaps(), DemoDeclaredTypePolicy(), settings)
    candidate = service.run(make_input(db, center, request)).candidates[0]

    assert candidate.eta_minutes is None
    assert candidate.distance_km is not None


def test_candidate_datatypes_match_the_contract():
    """Section 11.1/11.2 field names stay exactly as agreed with the Frontend."""
    from app.services.matching_service import MatchingCandidate

    assert set(MatchingInput.__dataclass_fields__) == {
        "request_id",
        "center_id",
        "component_type",
        "blood_group",
        "rh_factor",
        "max_candidates",
        "batch_size",
    }
    assert set(MatchingCandidate.__dataclass_fields__) == {
        "donor_id",
        "eta_minutes",
        "distance_km",
        "eligibility_check_status",
        "rank",
        "location_updated_at",
    }


def test_component_type_is_carried_into_matching(
    db, center_factory, request_factory, donor_factory, matching
):
    center, owner = center_factory()
    request = request_factory(
        center,
        owner,
        status="active",
        component_type=ComponentType.PLATELETS,
        blood_group=BloodGroup.B,
        rh_factor=RhFactor.NEGATIVE,
    )
    donor_factory(blood_group="B", rh_factor="negative")

    result = matching.run(make_input(db, center, request))
    assert len(result.candidates) == 1
