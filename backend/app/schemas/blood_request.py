"""Blood request schemas (Asra contribution; contract section 9.8)."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.core.enums import BloodGroup, ComponentType, RequestUrgency, RhFactor
from app.schemas.common import UtcDatetime

class BloodRequestCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    center_id: UUID
    component_type: ComponentType
    blood_group: BloodGroup
    rh_factor: RhFactor
    units_needed: int = Field(gt=0)
    urgency: RequestUrgency
    expires_at: UtcDatetime
    notes: str | None = None

class BloodRequestUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component_type: ComponentType | None = None
    blood_group: BloodGroup | None = None
    rh_factor: RhFactor | None = None
    units_needed: int | None = Field(default=None, gt=0)
    urgency: RequestUrgency | None = None
    expires_at: UtcDatetime | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not self.model_dump(exclude_unset=True):
            raise ValueError("Send at least one field to edit.")
        return self
