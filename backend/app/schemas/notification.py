"""Notification list and donor response shapes (sections 9.12 and the donor panel)."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import (
    BloodGroup,
    ComponentType,
    DonorResponseType,
    NotificationChannel,
    NotificationStatus,
    RequestUrgency,
    RhFactor,
)
from app.schemas.common import UtcDatetime


class DonorResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    response: DonorResponseType
    responded_at: UtcDatetime


class NotificationOut(BaseModel):
    id: UUID
    request_id: UUID
    channel: NotificationChannel
    status: NotificationStatus
    created_at: UtcDatetime
    center_id: UUID
    center_name: str
    component_type: ComponentType
    blood_group: BloodGroup
    rh_factor: RhFactor
    urgency: RequestUrgency
    expires_at: UtcDatetime
    response: DonorResponseOut | None = None


class NotificationResponseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: DonorResponseType
    eta_minutes: int | None = Field(default=None, ge=0, le=24 * 60)


class NotificationResponseOut(BaseModel):
    notification_id: UUID
    response: DonorResponseType
    responded_at: UtcDatetime
