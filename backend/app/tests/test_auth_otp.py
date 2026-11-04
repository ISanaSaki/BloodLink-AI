"""AUTH-01..03 acceptance scenarios (contract section 17) for the OTP endpoints."""

import logging
from uuid import UUID

import pytest

from conftest import _last_otp_code, make_phone, sent_messages

PREFIX = "/api/v1"


def request_otp(client, phone: str, purpose: str = "register"):
    return client.post(f"{PREFIX}/auth/otp/request", json={"phone": phone, "purpose": purpose})


def verify(client, challenge_id: str, phone: str, code: str, purpose: str = "register"):
    return client.post(
        f"{PREFIX}/auth/otp/verify",
        json={"challenge_id": challenge_id, "phone": phone, "code": code, "purpose": purpose},
    )


def test_otp_request_returns_challenge_and_sends_code(client):
    phone = make_phone()
    response = request_otp(client, phone)

    assert response.status_code == 202, response.text
    data = response.json()["data"]
    UUID(data["challenge_id"])
    assert data["expires_in_seconds"] == 120
    assert data["resend_after_seconds"] == 60
    assert "code" not in data  # the code only travels over the SMS channel

    assert len(_last_otp_code()) == 6
    assert phone not in sent_messages()[-1]["body"]
    assert sent_messages()[-1]["to"] != phone  # the recorded number stays masked


def test_otp_verify_creates_donor_and_consumes_challenge(client):
    """AUTH-01"""
    phone = make_phone()
    challenge_id = request_otp(client, phone).json()["data"]["challenge_id"]

    response = verify(client, challenge_id, phone, _last_otp_code())

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["token_type"] == "bearer"
    assert data["expires_in"] == 3600
    assert data["user"]["phone"] == phone
    assert data["user"]["role"] == "donor"
    assert data["user"]["is_profile_complete"] is False
    assert UUID(data["user"]["id"])

    replay = verify(client, challenge_id, phone, _last_otp_code())
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "UNAUTHENTICATED"


def test_verify_returns_working_token(client):
    phone = make_phone()
    challenge_id = request_otp(client, phone).json()["data"]["challenge_id"]
    token = verify(client, challenge_id, phone, _last_otp_code()).json()["data"]["access_token"]

    me = client.get(f"{PREFIX}/users/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["phone"] == phone


def test_wrong_otp_code_is_rejected(client):
    """AUTH-02"""
    phone = make_phone()
    challenge_id = request_otp(client, phone).json()["data"]["challenge_id"]

    response = verify(client, challenge_id, phone, "000000")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHENTICATED"


def test_expired_challenge_is_rejected(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "otp_ttl_seconds", -1)
    phone = make_phone()
    challenge_id = request_otp(client, phone).json()["data"]["challenge_id"]

    response = verify(client, challenge_id, phone, "123456")
    assert response.status_code == 401


def test_exhausting_attempts_returns_429(client):
    """AUTH-03: the challenge is destroyed once OTP_MAX_ATTEMPTS is reached."""
    phone = make_phone()
    challenge_id = request_otp(client, phone).json()["data"]["challenge_id"]

    for _ in range(4):
        assert verify(client, challenge_id, phone, "000000").status_code == 401

    blocked = verify(client, challenge_id, phone, "000000")
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "RATE_LIMITED"


def test_resend_before_window_is_rate_limited(client):
    phone = make_phone()
    assert request_otp(client, phone).status_code == 202

    second = request_otp(client, phone)
    assert second.status_code == 429
    assert int(second.headers["Retry-After"]) > 0


def test_per_phone_issue_limit_within_window(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "otp_resend_seconds", 0)
    phone = make_phone()
    statuses = [request_otp(client, phone).status_code for _ in range(settings.otp_max_requests_per_phone)]
    assert statuses == [202] * settings.otp_max_requests_per_phone

    overflow = request_otp(client, phone)
    assert overflow.status_code == 429
    assert overflow.json()["error"]["code"] == "RATE_LIMITED"


def test_login_for_unknown_phone_returns_not_found(client):
    phone = make_phone()
    challenge_id = request_otp(client, phone, "login").json()["data"]["challenge_id"]

    response = verify(client, challenge_id, phone, _last_otp_code(), purpose="login")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_register_twice_same_phone_reuses_account(client):
    from sqlalchemy import func, select

    from app.db.models.user import User
    from app.db.session import SessionLocal

    phone = make_phone()
    first = verify(client, request_otp(client, phone).json()["data"]["challenge_id"], phone, _last_otp_code())
    assert first.status_code == 200
    second_phone = make_phone()
    assert request_otp(client, second_phone).status_code == 202

    with SessionLocal() as session:
        accounts = session.scalar(select(func.count(User.id)).where(User.phone == phone))
    assert accounts == 1


def test_invalid_phone_shape_returns_standard_validation_error(client):
    response = request_otp(client, "09121234567")
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"][0]["field"] == "phone"
    assert UUID(error["request_id"])


def test_unknown_input_field_is_rejected(client):
    response = client.post(
        f"{PREFIX}/auth/otp/request",
        json={"phone": make_phone(), "purpose": "register", "role": "admin"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_challenge_phone_mismatch_is_rejected(client):
    first, second = make_phone(), make_phone()
    challenge_id = request_otp(client, first).json()["data"]["challenge_id"]

    response = verify(client, challenge_id, second, _last_otp_code())
    assert response.status_code == 401


def test_users_me_rejects_missing_or_broken_token(client):
    missing = client.get(f"{PREFIX}/users/me")
    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "UNAUTHENTICATED"

    broken = client.get(f"{PREFIX}/users/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert broken.status_code == 401


def test_inactive_user_cannot_authenticate(client, db):
    from app.core.enums import UserRole
    from app.db.models.user import User

    phone = make_phone()
    db.add(User(phone=phone, role=UserRole.DONOR, is_active=False))
    db.commit()

    challenge_id = request_otp(client, phone, "login").json()["data"]["challenge_id"]
    response = verify(client, challenge_id, phone, _last_otp_code(), purpose="login")
    assert response.status_code == 401


def test_otp_code_never_reaches_the_application_log(client, caplog):
    """Section 14: the code travels over the SMS channel only, never to a logger."""
    phone = make_phone()
    with caplog.at_level(logging.DEBUG):
        request_otp(client, phone)
    code = _last_otp_code()

    rendered = "\n".join(f"{record.getMessage()} {record.__dict__}" for record in caplog.records)
    assert code not in rendered
    assert phone not in rendered


def test_dev_outbox_catches_demo_codes(tmp_path, client, monkeypatch):
    outbox = tmp_path / "dev-outbox.log"
    monkeypatch.setattr("app.services.sms_service.settings.sms_dev_outbox_file", str(outbox))

    phone = make_phone()
    request_otp(client, phone)

    content = outbox.read_text(encoding="utf-8")
    assert phone in content
    assert _last_otp_code() in content


def test_dev_outbox_is_refused_in_production(tmp_path):
    from app.core.config import Settings

    with pytest.raises(ValueError, match="SMS_DEV_OUTBOX_FILE"):
        Settings(app_env="production", secret_key="a-real-secret", sms_dev_outbox_file=str(tmp_path / "x.log"))
