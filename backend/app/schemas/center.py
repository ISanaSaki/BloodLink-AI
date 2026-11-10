"""Centre request/response schemas (Asra contribution; contract section 9.7)."""
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, model_validator

class CenterCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    address: str = Field(min_length=1)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    phone: str | None = Field(default=None, max_length=20)
    opening_hours: str | None = None
    is_verified: bool = False
    is_active: bool = True
    owner_user_id: UUID | None = None

class CenterUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=160)
    address: str | None = Field(default=None, min_length=1)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    phone: str | None = Field(default=None, max_length=20)
    opening_hours: str | None = None
    is_verified: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def at_least_one(self):
        if not self.model_dump(exclude_unset=True):
            raise ValueError("حداقل یک فیلد برای ویرایش ارسال کنید.")
        return self
