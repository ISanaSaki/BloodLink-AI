"""Donor availability update schema."""

from pydantic import BaseModel, ConfigDict, model_validator

from app.core.enums import AvailabilityStatus
from app.schemas.common import UtcDatetime


class AvailabilityUpdate(BaseModel):
    """Donor availability window."""

    model_config = ConfigDict(extra="forbid")

    status: AvailabilityStatus
    available_from: UtcDatetime | None = None
    available_until: UtcDatetime | None = None

    @model_validator(mode="after")
    def validate_window(self):
        if self.status.value == "available":
            if self.available_from is None or self.available_until is None:
                raise ValueError(
                    "Both start and end times are required when available."
                )

            if self.available_until <= self.available_from:
                raise ValueError(
                    "End time must be after start time."
                )

        elif self.available_from is not None or self.available_until is not None:
            raise ValueError(
                "Time values must not be provided when unavailable."
            )

        return self