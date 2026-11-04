"""Pytest wiring: a dedicated PostgreSQL schema, eager Celery and in-memory OTP storage.

Everything here runs before `app` is imported so the global engine binds to the test
database instead of the development one.
"""

import os
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://postgres:postgres@127.0.0.1:5433/blood_donation_test",
)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ["APP_ENV"] = "test"
os.environ["COMPATIBILITY_POLICY"] = "demo"
os.environ["SMS_DEV_OUTBOX_FILE"] = ""

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.db.base import Base  # noqa: E402
import app.db.models  # noqa: E402,F401 - registers every mapper before create_all
from app.db.session import SessionLocal, engine  # noqa: E402


def _ensure_database() -> None:
    """Create blood_donation_test when it does not exist yet."""
    admin_url = TEST_DATABASE_URL.rsplit("/", 1)[0] + "/postgres"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    with admin.connect() as connection:
        name = TEST_DATABASE_URL.rsplit("/", 1)[1].split("?")[0]
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()


_ensure_database()

# The test schema is built by the real migration chain, so every test run also proves
# `alembic upgrade head` matches the models (decision 0005, DoD section 20).
def _migrate_test_schema() -> None:
    from alembic import command
    from alembic.config import Config

    ini = Path(__file__).resolve().parents[2] / "alembic.ini"
    Base.metadata.drop_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS alembic_version"))
    command.upgrade(Config(str(ini)), "head")


_migrate_test_schema()


@pytest.fixture(autouse=True)
def _reset_data() -> None:
    tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _offline_services() -> None:
    """OTP challenges stay in memory and Celery runs inline - no Redis needed for tests."""
    from app.services.otp_service import InMemoryChallengeStore, set_challenge_store
    from app.services.sms_service import mock_provider
    from app.tasks.celery_app import celery_app

    store = InMemoryChallengeStore()
    store.clear()
    mock_provider().clear()
    set_challenge_store(store)
    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield store
    set_challenge_store(None)


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> "TestClient":
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------- data factories

OTP_BODY_PATTERN = r"کد تأیید یکبار مصرف شما: (\d{6})"


def sent_messages() -> list[dict[str, str]]:
    from app.services.sms_service import mock_provider

    return mock_provider().messages


def _last_otp_code() -> str:
    import re

    body = sent_messages()[-1]["body"]
    match = re.search(OTP_BODY_PATTERN, body)
    assert match, f"no OTP code found in mock message body: {body!r}"
    return match.group(1)


def make_phone() -> str:
    return f"+9891{uuid4().int % 10**8:08d}"


@pytest.fixture
def donor_factory(db):
    from app.core.enums import UserRole
    from app.db.models.donor_availability import DonorAvailability
    from app.db.models.donor_location import DonorLocation
    from app.db.models.donor_profile import DonorProfile
    from app.db.models.user import User

    def _make(
        *,
        phone: str | None = None,
        blood_group="O",
        rh_factor="positive",
        verified: bool = True,
        sms_consent: bool = True,
        location_consent: bool = True,
        latitude: Decimal | None = Decimal("35.700000"),
        longitude: Decimal | None = Decimal("51.400000"),
        available: bool = True,
    ) -> DonorProfile:
        user = User(phone=phone or make_phone(), role=UserRole.DONOR, is_active=True)
        db.add(user)
        db.flush()
        profile = DonorProfile(
            user_id=user.id,
            blood_group=blood_group,
            rh_factor=rh_factor,
            blood_type_verified=verified,
            sms_consent=sms_consent,
            location_consent=location_consent,
        )
        db.add(profile)
        db.flush()
        if latitude is not None and location_consent:
            db.add(DonorLocation(donor_id=profile.id, latitude=latitude, longitude=longitude))
        db.add(
            DonorAvailability(
                donor_id=profile.id,
                status="available" if available else "unavailable",
            )
        )
        db.commit()
        db.refresh(profile)
        return profile

    return _make


@pytest.fixture
def center_factory(db):
    from app.core.enums import UserRole
    from app.db.models.blood_center import BloodCenter
    from app.db.models.user import User

    def _make(*, operator: bool = True, verified: bool = True, is_active: bool = True):
        owner = None
        if operator:
            owner = User(phone=make_phone(), role=UserRole.CENTER_OPERATOR, is_active=True)
            db.add(owner)
            db.flush()
        center = BloodCenter(
            name=f"مرکز آزمایشی {uuid4().hex[:6]}",
            address="تهران، خیابان نمونه",
            latitude=Decimal("35.700000"),
            longitude=Decimal("51.400000"),
            phone="+982122222222",
            is_verified=verified,
            is_active=is_active,
            opening_hours="۲۴ ساعته",
            owner_user_id=owner.id if owner else None,
        )
        db.add(center)
        db.commit()
        return center, owner

    return _make


@pytest.fixture
def request_factory(db):
    from app.db.models.blood_request import BloodRequest

    def _make(center, owner, *, status="draft", units_needed=2, minutes=120, **kwargs):
        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        request = BloodRequest(
            center_id=center.id,
            component_type=kwargs.pop("component_type", "red_cells"),
            blood_group=kwargs.pop("blood_group", "O"),
            rh_factor=kwargs.pop("rh_factor", "positive"),
            units_needed=units_needed,
            urgency=kwargs.pop("urgency", "urgent"),
            status=status,
            expires_at=now + timedelta(minutes=minutes),
            created_by=owner.id,
            notes="یادداشت داخلی مرکز",
            activated_at=now if status != "draft" else None,
            **kwargs,
        )
        db.add(request)
        db.commit()
        db.refresh(request)
        return request

    return _make


@pytest.fixture
def auth_headers(client):
    """Issue a real JWT through the public OTP endpoints (no manual token crafting)."""

    def _headers(user_id, role) -> dict[str, str]:
        from app.core.security import create_access_token

        token, _ = create_access_token(user_id, role)
        return {"Authorization": f"Bearer {token}"}

    return _headers


@pytest.fixture
def registered_donor(client):
    """End-to-end registration through the API, returning headers and the donor row."""
    from app.core.enums import OtpPurpose

    phone = make_phone()
    issued = client.post("/api/v1/auth/otp/request", json={"phone": phone, "purpose": "register"})
    assert issued.status_code == 202, issued.text
    challenge_id = issued.json()["data"]["challenge_id"]
    code = _last_otp_code()
    verified = client.post(
        "/api/v1/auth/otp/verify",
        json={
            "challenge_id": challenge_id,
            "phone": phone,
            "code": code,
            "purpose": OtpPurpose.REGISTER.value,
        },
    )
    assert verified.status_code == 200, verified.text
    body = verified.json()["data"]
    return {
        "phone": phone,
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
        "user": body["user"],
    }
