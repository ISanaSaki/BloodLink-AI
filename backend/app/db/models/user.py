"""``users`` - authentication identity and role (contract section 3 and 5)."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import UserRole
from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, enum_column

if TYPE_CHECKING:
    from app.db.models.blood_request import BloodRequest
    from app.db.models.donor_profile import DonorProfile

ROLE_LENGTH = 20


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    phone: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    role: Mapped[UserRole] = enum_column(UserRole, ROLE_LENGTH, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    donor_profile: Mapped["DonorProfile | None"] = relationship(
        back_populates="user", uselist=False, lazy="selectin", cascade="all, delete-orphan"
    )
    created_requests: Mapped[list["BloodRequest"]] = relationship(back_populates="created_by_user")

    @property
    def is_profile_complete(self) -> bool:
        """Section 9.2/9.3: profile is complete once blood data and consents exist."""
        profile = self.donor_profile
        if profile is None:
            return self.role != UserRole.DONOR
        return profile.blood_group is not None and profile.rh_factor is not None

    def __repr__(self) -> str:  # pragma: no cover - debugging helper, phone is masked
        return f"<User id={self.id} role={self.role}>"
