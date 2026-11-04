"""Token issuing/validation and OTP hashing (section 0: Bearer access token + OTP)."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from app.core.config import settings
from app.core.enums import OtpPurpose, UserRole

JWT_ALGORITHM = "HS256"
OTP_CODE_LENGTH = 6


@dataclass(frozen=True, slots=True)
class TokenPayload:
    user_id: UUID
    role: UserRole
    expires_at: datetime


def create_access_token(user_id: UUID | str, role: UserRole | str) -> tuple[str, int]:
    """Return ``(token, expires_in_seconds)`` for the authenticated user."""
    now = datetime.now(UTC)
    expires_in = settings.access_token_expire_minutes * 60
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "role": str(role),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(claims, settings.secret_key, algorithm=JWT_ALGORITHM)
    return token, expires_in


def decode_access_token(token: str) -> TokenPayload:
    claims = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    return TokenPayload(
        user_id=UUID(str(claims["sub"])),
        role=UserRole(str(claims["role"])),
        expires_at=datetime.fromtimestamp(int(claims["exp"]), tz=UTC),
    )


def generate_otp_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(OTP_CODE_LENGTH))


def hash_otp(code: str, phone: str, purpose: OtpPurpose | str) -> str:
    """Only the digest is ever stored (section 9.1)."""
    message = f"{phone}:{purpose}:{code}".encode()
    return hmac.new(settings.secret_key.encode(), message, hashlib.sha256).hexdigest()


def otp_matches(code: str, phone: str, purpose: OtpPurpose | str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_otp(code, phone, purpose), stored_hash)


def generate_response_token() -> str:
    """Opaque token used for the secure donor response link (section 12)."""
    return secrets.token_urlsafe(32)
