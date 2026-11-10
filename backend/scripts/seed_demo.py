"""Demo data for the contest MVP - synthetic records only.

Run with `python -m scripts.seed_demo` from `backend/`. The script is idempotent:
existing demo rows are reused, so it is safe to run after every `alembic upgrade head`.

All phones, names and coordinates here are invented for the demo. Never put real donor
or patient data into this file or into the database it writes (contract section 1.2).
"""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.enums import UserRole
from app.db.models.blood_center import BloodCenter
from app.db.models.blood_request import BloodRequest
from app.db.models.donor_availability import DonorAvailability
from app.db.models.donor_location import DonorLocation
from app.db.models.donor_profile import DonorProfile
from app.db.models.user import User
from app.db.session import session_scope

ADMIN_PHONE = "+989120000001"
CENTERS = (
    {
        "name": "Tehran Central Blood Center",
        "address": "No. 1, Demo Avenue, Tehran",
        "latitude": Decimal("35.699700"),
        "longitude": Decimal("51.398300"),
        "phone": "+982122220001",
        "operator_phone": "+989120000002",
    },
    {
        "name": "Karaj Central Blood Center",
        "address": "No. 2, Demo Boulevard, Karaj",
        "latitude": Decimal("35.832000"),
        "longitude": Decimal("50.991000"),
        "phone": "+982122220002",
        "operator_phone": "+989120000003",
    },
)

# (phone, blood_group, rh, verified, sms_consent, location_consent, lat, lng, available, last_donation)
DONORS: tuple[tuple, ...] = (
    ("+989121110001", "O", "positive", True, True, True, "35.705000", "51.405000", True, date(2026, 5, 10)),
    ("+989121110002", "O", "positive", True, True, True, "35.720000", "51.380000", True, date(2026, 4, 2)),
    ("+989121110003", "A", "positive", True, True, True, "35.680000", "51.420000", True, date(2026, 6, 20)),
    ("+989121110004", "B", "positive", True, True, True, "35.750000", "51.350000", True, date(2026, 3, 15)),
    ("+989121110005", "AB", "negative", True, True, True, "35.660000", "51.440000", True, date(2026, 7, 1)),
    ("+989121110006", "O", "negative", True, True, True, "35.820000", "51.300000", True, date(2026, 2, 8)),
    ("+989121110007", "O", "positive", True, True, True, "35.610000", "51.500000", True, date(2026, 8, 12)),
    ("+989121110008", "A", "negative", True, True, True, "35.830000", "50.990000", True, date(2026, 6, 30)),
    ("+989121110009", "O", "positive", False, True, True, "35.700000", "51.400000", True, None),
    ("+989121110010", "O", "positive", True, False, True, "35.710000", "51.410000", True, date(2026, 5, 5)),
    ("+989121110011", "O", "positive", True, True, False, "35.715000", "51.415000", True, date(2026, 4, 18)),
    ("+989121110012", "B", "negative", True, True, True, "35.690000", "51.390000", False, date(2026, 9, 9)),
)

DEMO_REQUESTS = (
    {"center_index": 0, "component_type": "red_cells", "blood_group": "O", "rh_factor": "positive",
     "units_needed": 3, "urgency": "urgent", "notes": "Demo request - synthetic data"},
    {"center_index": 1, "component_type": "platelets", "blood_group": "A", "rh_factor": "positive",
     "units_needed": 1, "urgency": "routine", "notes": "Demo request - synthetic data"},
)


def _get_or_create_user(session, phone: str, role: UserRole) -> User:
    user = session.scalar(select(User).where(User.phone == phone))
    if user is None:
        user = User(phone=phone, role=role, is_active=True)
        session.add(user)
        session.flush()
    return user


def seed() -> dict[str, int]:
    counts = {"users": 0, "centers": 0, "donors": 0, "requests": 0}
    now = datetime.now(UTC)
    counts["users"] = 1 + len(CENTERS) + len(DONORS)

    with session_scope() as session:
        _get_or_create_user(session, ADMIN_PHONE, UserRole.ADMIN)

        centers: list[BloodCenter] = []
        for spec in CENTERS:
            operator = _get_or_create_user(session, spec["operator_phone"], UserRole.CENTER_OPERATOR)
            center = session.scalar(select(BloodCenter).where(BloodCenter.name == spec["name"]))
            if center is None:
                center = BloodCenter(
                    name=spec["name"],
                    address=spec["address"],
                    latitude=spec["latitude"],
                    longitude=spec["longitude"],
                    phone=spec["phone"],
                    is_verified=True,
                    is_active=True,
                    opening_hours="24 hours",
                    owner_user_id=operator.id,
                )
                session.add(center)
                session.flush()
            centers.append(center)
            counts["centers"] += 1

        for (
            phone, blood_group, rh, verified, sms_consent, location_consent,
            latitude, longitude, available, last_donation,
        ) in DONORS:
            user = _get_or_create_user(session, phone, UserRole.DONOR)
            profile = session.scalar(select(DonorProfile).where(DonorProfile.user_id == user.id))
            if profile is None:
                profile = DonorProfile(user_id=user.id)
                session.add(profile)
            profile.blood_group = blood_group
            profile.rh_factor = rh
            profile.blood_type_verified = verified
            profile.last_donation_date = last_donation
            profile.sms_consent = sms_consent
            profile.location_consent = location_consent
            session.flush()

            if location_consent:
                location = profile.location or session.scalar(
                    select(DonorLocation).where(DonorLocation.donor_id == profile.id)
                )
                if location is None:
                    location = DonorLocation(donor_id=profile.id)
                    session.add(location)
                location.latitude = Decimal(latitude)
                location.longitude = Decimal(longitude)
            elif profile.location is not None:
                session.delete(profile.location)

            availability = profile.availability or session.scalar(
                select(DonorAvailability).where(DonorAvailability.donor_id == profile.id)
            )
            if availability is None:
                availability = DonorAvailability(donor_id=profile.id)
                session.add(availability)
            availability.status = "available" if available else "unavailable"
            availability.available_from = now if available else None
            availability.available_until = now + timedelta(days=7) if available else None
            counts["donors"] += 1

        for spec in DEMO_REQUESTS:
            center = centers[spec["center_index"]]
            existing = session.scalar(
                select(BloodRequest).where(
                    BloodRequest.center_id == center.id,
                    BloodRequest.status.in_(("draft", "active")),
                )
            )
            if existing is None:
                session.add(
                    BloodRequest(
                        center_id=center.id,
                        component_type=spec["component_type"],
                        blood_group=spec["blood_group"],
                        rh_factor=spec["rh_factor"],
                        units_needed=spec["units_needed"],
                        urgency=spec["urgency"],
                        status="draft",
                        expires_at=now + timedelta(hours=6),
                        created_by=center.owner_user_id,
                        notes=spec["notes"],
                    )
                )
            counts["requests"] += 1

    return counts


def main() -> None:
    counts = seed()
    print("demo data ready:")
    for key, value in counts.items():
        print(f"  {key}: {value}")
    print(f"  admin login (OTP): {ADMIN_PHONE}")
    for spec in CENTERS:
        print(f"  center operator (OTP): {spec['operator_phone']}")


if __name__ == "__main__":
    main()
