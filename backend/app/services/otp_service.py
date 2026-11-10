"""OTP lifecycle: challenge storage, rate limiting and verification (sections 9.1, 9.2, 12.1).

Only the HMAC digest of a code is persisted. Redis is the production store because the
workers and the API must share TTL state; an in-memory store keeps unit tests dependency-free.
"""

import hashlib
import hmac
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.core.enums import OtpPurpose, UserRole
from app.core.exceptions import NotFound, RateLimited, Unauthorized
from app.core.security import generate_otp_code, hash_otp, otp_matches
from app.db.models.donor_profile import DonorProfile
from app.db.models.user import User


def now_ts() -> float:
    return datetime.now(UTC).timestamp()


@dataclass(slots=True)
class OtpChallenge:
    challenge_id: UUID
    phone: str
    purpose: OtpPurpose
    code_hash: str
    expires_at: float
    attempts: int = 0

    @property
    def remaining_seconds(self) -> int:
        return max(1, math.ceil(self.expires_at - now_ts()))

    def to_json(self) -> str:
        payload = asdict(self)
        payload["challenge_id"] = str(self.challenge_id)
        payload["purpose"] = str(self.purpose)
        return json.dumps(payload)

    @classmethod
    def from_json(cls, raw: str) -> "OtpChallenge":
        payload = json.loads(raw)
        return cls(
            challenge_id=UUID(payload["challenge_id"]),
            phone=payload["phone"],
            purpose=OtpPurpose(payload["purpose"]),
            code_hash=payload["code_hash"],
            expires_at=float(payload["expires_at"]),
            attempts=int(payload.get("attempts", 0)),
        )


class ChallengeStore(Protocol):
    def save(self, challenge: OtpChallenge) -> None: ...
    def load(self, challenge_id: UUID) -> OtpChallenge | None: ...
    def delete(self, challenge_id: UUID) -> None: ...
    def lock(self, key: str, ttl_seconds: int) -> int:
        """Set the key if free; return 0, otherwise the seconds already locked."""

    def count(self, key: str, ttl_seconds: int) -> int:
        """Increment a rolling-window counter and return its value."""


class InMemoryChallengeStore:
    def __init__(self) -> None:
        self._challenges: dict[UUID, OtpChallenge] = {}
        self._locks: dict[str, float] = {}
        self._counters: dict[str, tuple[int, float]] = {}

    def save(self, challenge: OtpChallenge) -> None:
        self._challenges[challenge.challenge_id] = challenge

    def load(self, challenge_id: UUID) -> OtpChallenge | None:
        challenge = self._challenges.get(challenge_id)
        if challenge is None:
            return None
        if challenge.expires_at <= now_ts():
            self._challenges.pop(challenge_id, None)
            return None
        return challenge

    def delete(self, challenge_id: UUID) -> None:
        self._challenges.pop(challenge_id, None)

    def lock(self, key: str, ttl_seconds: int) -> int:
        expiry = self._locks.get(key, 0.0)
        if expiry > now_ts():
            return max(1, math.ceil(expiry - now_ts()))
        self._locks[key] = now_ts() + ttl_seconds
        return 0

    def count(self, key: str, ttl_seconds: int) -> int:
        current, expiry = self._counters.get(key, (0, 0.0))
        if expiry <= now_ts():
            self._counters[key] = (1, now_ts() + ttl_seconds)
            return 1
        self._counters[key] = (current + 1, expiry)
        return current + 1

    def clear(self) -> None:
        self._challenges.clear()
        self._locks.clear()
        self._counters.clear()


class RedisChallengeStore:
    def __init__(self, client) -> None:
        self._client = client

    def save(self, challenge: OtpChallenge) -> None:
        self._client.set(
            f"otp:challenge:{challenge.challenge_id}",
            challenge.to_json(),
            ex=challenge.remaining_seconds,
        )

    def load(self, challenge_id: UUID) -> OtpChallenge | None:
        raw = self._client.get(f"otp:challenge:{challenge_id}")
        return OtpChallenge.from_json(raw) if raw else None

    def delete(self, challenge_id: UUID) -> None:
        self._client.delete(f"otp:challenge:{challenge_id}")

    def lock(self, key: str, ttl_seconds: int) -> int:
        if self._client.set(key, "1", nx=True, ex=ttl_seconds):
            return 0
        return max(0, int(self._client.ttl(key) or 0))

    def count(self, key: str, ttl_seconds: int) -> int:
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        total, expiry = pipe.execute()
        if expiry is None or int(expiry) < 0:
            self._client.expire(key, ttl_seconds)
        return int(total)


def _rate_key(secret: str, scope: str, value: str) -> str:
    """Rate-limit keys never contain a raw phone number or client IP."""
    digest = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:32]
    return f"otp:rate:{scope}:{digest}"


@dataclass(frozen=True, slots=True)
class OtpIssued:
    challenge_id: UUID
    code: str
    phone: str
    purpose: OtpPurpose
    expires_in_seconds: int
    resend_after_seconds: int


class OtpService:
    def __init__(self, store: ChallengeStore, config: Settings | None = None) -> None:
        self._store = store
        self._config = config or settings

    def issue(self, phone: str, purpose: OtpPurpose, client_ip: str) -> OtpIssued:
        config = self._config
        locked = self._store.lock(
            _rate_key(config.secret_key, "resend", phone), config.otp_resend_seconds
        )
        if locked:
            raise RateLimited("Please wait before requesting another code.", retry_after_seconds=locked)

        self._enforce_window(_rate_key(config.secret_key, "phone", phone), config.otp_max_requests_per_phone)
        self._enforce_window(
            _rate_key(config.secret_key, "ip", client_ip), config.otp_max_requests_per_ip
        )

        code = generate_otp_code()
        challenge = OtpChallenge(
            challenge_id=uuid4(),
            phone=phone,
            purpose=purpose,
            code_hash=hash_otp(code, phone, purpose),
            expires_at=now_ts() + config.otp_ttl_seconds,
        )
        self._store.save(challenge)
        return OtpIssued(
            challenge_id=challenge.challenge_id,
            code=code,
            phone=phone,
            purpose=purpose,
            expires_in_seconds=config.otp_ttl_seconds,
            resend_after_seconds=config.otp_resend_seconds,
        )

    def verify(self, challenge_id: UUID, phone: str, code: str, purpose: OtpPurpose) -> None:
        """Raise on any mismatch; a successful verify consumes the challenge once."""
        challenge = self._store.load(challenge_id)
        if challenge is None:
            raise Unauthorized("The verification code is invalid or has expired.")
        if challenge.phone != phone or challenge.purpose != purpose:
            self._store.delete(challenge_id)
            raise Unauthorized("The verification code does not match this phone or purpose.")

        if not otp_matches(code, phone, purpose, challenge.code_hash):
            self._register_failure(challenge)
            raise Unauthorized("The code you entered is incorrect.")

        self._store.delete(challenge_id)

    def _register_failure(self, challenge: OtpChallenge) -> None:
        attempts = challenge.attempts + 1
        if attempts >= self._config.otp_max_attempts:
            self._store.delete(challenge.challenge_id)
            raise RateLimited("Too many attempts. Request a new code.")
        self._store.save(replace(challenge, attempts=attempts))

    def _enforce_window(self, key: str, limit: int) -> None:
        used = self._store.count(key, self._config.otp_rate_limit_window_seconds)
        if used > limit:
            raise RateLimited(
                "The maximum number of code requests for this period has been used.",
                retry_after_seconds=self._config.otp_rate_limit_window_seconds,
            )


def get_or_create_user(db: Session, phone: str, purpose: OtpPurpose) -> tuple[User, bool]:
    """Section 9.2: a new phone registers as `donor`; `login` never provisions silently."""
    user = db.scalar(select(User).where(User.phone == phone))
    if user is not None:
        if not user.is_active:
            raise Unauthorized("Your account has been disabled.")
        return user, False
    if purpose is not OtpPurpose.REGISTER:
        raise NotFound("No account found for this phone; register first.")

    user = User(phone=phone, role=UserRole.DONOR, is_active=True)
    db.add(user)
    db.flush()
    db.add(DonorProfile(user_id=user.id))
    return user, True


_store_singleton: ChallengeStore | None = None


def get_challenge_store() -> ChallengeStore:
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = build_challenge_store()
    return _store_singleton


def set_challenge_store(store: ChallengeStore | None) -> None:
    global _store_singleton
    _store_singleton = store


def build_challenge_store() -> ChallengeStore:
    try:
        import redis

        client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return RedisChallengeStore(client)
    except Exception:  # offline development / unit tests
        return InMemoryChallengeStore()
