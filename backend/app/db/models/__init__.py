"""Importing this package registers every mapper for Alembic and the ORM."""

from app.db.models.audit_log import AuditLog
from app.db.models.blood_center import BloodCenter
from app.db.models.blood_request import BloodRequest
from app.db.models.donor_availability import DonorAvailability
from app.db.models.donor_location import DonorLocation
from app.db.models.donor_profile import DonorProfile
from app.db.models.donor_response import DonorResponse
from app.db.models.notification import Notification
from app.db.models.user import User

__all__ = [
    "AuditLog",
    "BloodCenter",
    "BloodRequest",
    "DonorAvailability",
    "DonorLocation",
    "DonorProfile",
    "DonorResponse",
    "Notification",
    "User",
]
