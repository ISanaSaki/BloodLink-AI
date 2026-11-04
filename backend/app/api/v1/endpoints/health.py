"""Health probe for containers and the demo dashboard."""

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.common import envelope

router = APIRouter(tags=["system"])


@router.get("/health", summary="سلامت سرویس")
def health() -> dict:
    return envelope(
        {
            "status": "ok",
            "environment": settings.app_env,
            "api_version": "v1",
            "sms_provider": settings.sms_provider,
            "maps_provider": settings.maps_provider,
            "compatibility_policy": settings.compatibility_policy,
        }
    )
