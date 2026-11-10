"""v1 router assembly. Paths and tags are frozen by the contract (section 8)."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    auth,
    dispatch,
    donor_location,
    donor_profile,
    health,
    notifications,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(donor_profile.router)
api_router.include_router(donor_location.router)
api_router.include_router(dispatch.router)
api_router.include_router(notifications.router)

# Registered here by their owners, keeping this file conflict-free (section 16.2):
#   from app.api.v1.endpoints import blood_requests, centers, donor_availability  # Asra
#   api_router.include_router(centers.router)
#   api_router.include_router(blood_requests.router)
#   api_router.include_router(donor_availability.router)
