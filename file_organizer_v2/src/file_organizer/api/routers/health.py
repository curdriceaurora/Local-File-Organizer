"""Health check endpoints."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: ApiSettings = Depends(get_settings)) -> dict[str, str]:
    """Return basic health status for the API."""
    return {
        "status": "healthy",
        "version": settings.version,
        "environment": settings.environment,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
