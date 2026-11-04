"""Project-wide enums frozen by section 6 of the development contract."""

from enum import StrEnum


class UserRole(StrEnum):
    DONOR = "donor"
    CENTER_OPERATOR = "center_operator"
    ADMIN = "admin"


class RhFactor(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"


class BloodGroup(StrEnum):
    A = "A"
    B = "B"
    AB = "AB"
    O = "O"


class AvailabilityStatus(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class ComponentType(StrEnum):
    RED_CELLS = "red_cells"
    PLATELETS = "platelets"
    PLASMA = "plasma"
    WHOLE_BLOOD = "whole_blood"


class RequestUrgency(StrEnum):
    ROUTINE = "routine"
    URGENT = "urgent"
    CRITICAL = "critical"


class BloodRequestStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class NotificationChannel(StrEnum):
    SMS = "sms"


class NotificationStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class DonorResponseType(StrEnum):
    INTERESTED = "interested"
    UNAVAILABLE = "unavailable"


class OtpPurpose(StrEnum):
    LOGIN = "login"
    REGISTER = "register"


class EligibilityCheckStatus(StrEnum):
    """Values fixed by the Matching contract in section 11.2."""

    VERIFIED_DATA = "verified_data"
    NEEDS_REVIEW = "needs_review"
