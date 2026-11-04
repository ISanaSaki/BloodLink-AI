"""Structured logging that never prints secrets (contract section 14)."""

import logging
import sys
from typing import Any

from app.core.config import settings
from app.core.context import get_request_id

_CONFIGURED = False
_REDADED_KEYS = {"otp", "code", "token", "access_token", "authorization", "password", "phone", "secret"}


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s"
        )
    )
    handler.addFilter(_RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if settings.app_debug else logging.INFO)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)


def redact(extra: dict[str, Any]) -> dict[str, Any]:
    """Drop keys that may carry OTPs, tokens or full phone numbers before logging."""
    return {key: value for key, value in extra.items() if key.lower() not in _REDADED_KEYS}
