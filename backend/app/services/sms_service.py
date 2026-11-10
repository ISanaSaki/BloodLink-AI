"""Swappable SMS provider adapter (contract section 0 "Demo" and section 12).

`mock` records messages and sends nothing. A real gateway needs vendor-issued
credentials plus centre approval, and is intentionally not wired up here.
"""

import itertools
from dataclasses import dataclass, field
from typing import Protocol

from app.core.config import Settings, settings
from app.core.logging import get_logger

logger = get_logger(__name__)

MOCK_PROVIDER = "mock"


@dataclass(frozen=True, slots=True)
class SmsSendResult:
    provider_message_id: str
    accepted: bool
    failure_reason: str | None = None


class SmsProvider(Protocol):
    name: str

    def send(self, to: str, body: str) -> SmsSendResult: ...


@dataclass(slots=True)
class MockSmsProvider:
    """Records messages instead of sending them; safe for demos and tests."""

    name: str = MOCK_PROVIDER
    messages: list[dict[str, str]] = field(default_factory=list)
    _counter: "itertools.count[int]" = field(default_factory=itertools.count, repr=False)

    def send(self, to: str, body: str) -> SmsSendResult:
        reference = f"mock-{next(self._counter):06d}"
        self.messages.append({"to": mask_phone(to), "body": body, "reference": reference})
        _write_dev_outbox(to, body)
        logger.info(
            "sms_mock_send",
            extra={"provider": self.name, "message_id": reference, "length": len(body)},
        )
        return SmsSendResult(provider_message_id=reference, accepted=True)

    def clear(self) -> None:
        self.messages.clear()


def _write_dev_outbox(to: str, body: str) -> None:
    """Demo mailbox (a file, not a log line) so the team can read a code without breaching section 14."""
    path = settings.sms_dev_outbox_file
    if not path or settings.is_production:
        return
    try:
        with open(path, "a", encoding="utf-8") as outbox:
            outbox.write(f"{to}\t{body}\n")
    except OSError as exc:
        logger.warning("dev_outbox_write_failed", extra={"error_type": type(exc).__name__})


def mask_phone(phone: str) -> str:
    """Section 14: complete phone numbers must not reach the log."""
    if len(phone) <= 6:
        return "*" * len(phone)
    return f"{phone[:4]}***{phone[-3:]}"


_MOCK_PROVIDER = MockSmsProvider()


def build_sms_provider(config: Settings | None = None) -> SmsProvider:
    config = config or settings
    if config.sms_provider.lower() == MOCK_PROVIDER:
        return _MOCK_PROVIDER
    raise ValueError(
        f"Unsupported SMS_PROVIDER={config.sms_provider!r}. "
        "A real gateway requires vendor credentials and centre approval."
    )


def mock_provider() -> MockSmsProvider:
    """Access to the recorded demo messages (used by the test suite and the demo UI)."""
    return _MOCK_PROVIDER


def build_otp_message(code: str, ttl_seconds: int) -> str:
    return f"Your one-time code: {code}. It is valid for {ttl_seconds} seconds."


def build_dispatch_message(center_name: str, response_url: str) -> str:
    return (
        f"A blood donation call has been opened at {center_name}.\n"
        f"If you are able, view the details and respond through the secure link below:\n{response_url}\n"
        "This message does not confirm your medical eligibility."
    )


def build_cancellation_message(center_name: str) -> str:
    return f"The blood donation call at {center_name} has been stopped. Thank you for your attention."
