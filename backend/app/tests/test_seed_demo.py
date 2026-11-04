"""INT-01 readiness: the demo dataset seeds, re-seeds and produces real candidates."""

from sqlalchemy import func, select

from app.db.models.blood_center import BloodCenter
from app.db.models.blood_request import BloodRequest
from app.db.models.donor_profile import DonorProfile
from app.db.models.user import User
from scripts.seed_demo import DONORS, CENTERS, seed


def test_seed_creates_the_demo_dataset(db):
    seed()

    assert db.scalar(select(func.count(User.id))) == 1 + len(CENTERS) + len(DONORS)
    assert db.scalar(select(func.count(BloodCenter.id))) == len(CENTERS)
    assert db.scalar(select(func.count(DonorProfile.id))) == len(DONORS)
    assert db.scalar(select(func.count(BloodRequest.id))) == len(CENTERS)

    tehran = db.scalar(select(BloodCenter).where(BloodCenter.name == CENTERS[0]["name"]))
    assert tehran.is_verified and tehran.owner_user_id is not None


def test_seed_is_idempotent(db):
    seed()
    seed()

    assert db.scalar(select(func.count(User.id))) == 1 + len(CENTERS) + len(DONORS)
    assert db.scalar(select(func.count(BloodRequest.id))) == len(CENTERS)
    assert db.scalar(select(func.count(BloodRequest.id)).where(BloodRequest.status == "draft")) == len(CENTERS)


def test_demo_dataset_yields_ranked_candidates(db):
    """A seeded draft request, once active, matches verified O+ donors near Tehran."""
    from app.core.enums import BloodRequestStatus
    from app.services.matching_service import MatchingService
    from app.services.notification_service import NotificationService

    seed()
    request = db.scalar(
        select(BloodRequest).where(
            BloodRequest.blood_group == "O", BloodRequest.rh_factor == "positive"
        )
    )
    request.status = BloodRequestStatus.ACTIVE
    request.activated_at = request.created_at
    db.commit()

    service = NotificationService.build(db)
    matching = MatchingService(db, service.maps, service.policy, service.config)
    _, inputs = matching.candidates_for_request(request.id)
    result = matching.run(inputs)

    assert len(result.dispatchable) == 3
    etas = [candidate.eta_minutes for candidate in result.dispatchable]
    assert etas == sorted(etas)
    assert all(candidate.distance_km is not None for candidate in result.dispatchable)
