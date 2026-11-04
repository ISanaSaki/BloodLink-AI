"""Response envelope of section 7.2 plus the shared UTC datetime type."""

from datetime import UTC, datetime
from typing import Annotated, Any

from pydantic import BeforeValidator, Field, PlainSerializer

from app.core.context import get_request_id


def to_utc(value: Any) -> Any:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return value


def to_iso_zulu(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return to_utc(value).astimezone(UTC).isoformat().replace("+00:00", "Z")


# API times are ISO-8601 UTC with a `Z` suffix (section 2.1).
UtcDatetime = Annotated[
    datetime,
    BeforeValidator(to_utc),
    PlainSerializer(to_iso_zulu, return_type=str, when_used="json"),
]

# E.164 is preferred by the contract (section 5, `users.phone`).
PHONE_PATTERN = r"^\+[1-9]\d{6,14}$"
PhoneNumber = Annotated[str, Field(pattern=PHONE_PATTERN, examples=["+989121234567"])]

def envelope(
    data: Any,
    *,
    page: int | None = None,
    page_size: int | None = None,
    total: int | None = None,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {"request_id": get_request_id()}
    if page is not None:
        meta["page"] = page
        meta["page_size"] = page_size
        meta["total"] = total
    if extra_meta:
        meta.update(extra_meta)
    return {"data": data, "meta": meta}


def paginated(items: list[Any], *, page: int, page_size: int, total: int) -> dict[str, Any]:
    return envelope(items, page=page, page_size=page_size, total=total)
