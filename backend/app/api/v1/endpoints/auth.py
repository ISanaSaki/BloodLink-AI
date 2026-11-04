"""Auth endpoints owned by the Backend Lead: OTP request and verify (sections 9.1, 9.2)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.dependencies import DatabaseSession
from app.core.enums import OtpPurpose
from app.core.security import create_access_token
from app.schemas.auth import OtpRequestIn, OtpRequestOut, OtpVerifyIn, TokenOut
from app.schemas.common import envelope
from app.schemas.user import UserOut
from app.services.audit_service import AuditService
from app.services.otp_service import (
    ChallengeStore,
    OtpService,
    get_challenge_store,
    get_or_create_user,
)
from app.services.sms_service import build_otp_message, build_sms_provider

router = APIRouter(prefix="/auth", tags=["auth"])


def get_otp_store() -> ChallengeStore:
    return get_challenge_store()


OtpStore = Annotated[ChallengeStore, Depends(get_otp_store)]


def _send_otp_sms(phone: str, code: str, ttl_seconds: int) -> None:
    """Send inline: a Celery task would put the OTP code and the phone number into the broker."""
    build_sms_provider().send(phone, build_otp_message(code, ttl_seconds))


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/otp/request", status_code=status.HTTP_202_ACCEPTED, summary="درخواست کد OTP")
def request_otp(
    payload: OtpRequestIn,
    request: Request,
    store: OtpStore,
    db: DatabaseSession,
) -> dict:
    issued = OtpService(store).issue(payload.phone, payload.purpose, _client_ip(request))
    _send_otp_sms(issued.phone, issued.code, issued.expires_in_seconds)
    AuditService(db).record(
        action="otp_requested",
        entity_type="otp_challenge",
        entity_id=issued.challenge_id,
        details={"purpose": str(issued.purpose)},
    )
    db.commit()
    return envelope(
        OtpRequestOut(
            challenge_id=issued.challenge_id,
            expires_in_seconds=issued.expires_in_seconds,
            resend_after_seconds=issued.resend_after_seconds,
        ).model_dump(mode="json")
    )


@router.post("/otp/verify", summary="تأیید کد OTP و دریافت توکن")
def verify_otp(payload: OtpVerifyIn, store: OtpStore, db: DatabaseSession) -> dict:
    OtpService(store).verify(payload.challenge_id, payload.phone, payload.code, payload.purpose)
    user, created = get_or_create_user(db, payload.phone, payload.purpose)
    if created:
        AuditService(db).record(
            action="donor_registered",
            entity_type="user",
            actor_id=user.id,
            entity_id=user.id,
            details={"role": str(user.role)},
        )
    db.commit()

    token, expires_in = create_access_token(user.id, user.role)
    return envelope(
        TokenOut(
            access_token=token,
            expires_in=expires_in,
            user=UserOut.model_validate(user),
        ).model_dump(mode="json")
    )
