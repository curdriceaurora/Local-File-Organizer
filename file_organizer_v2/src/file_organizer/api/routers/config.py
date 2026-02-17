"""Configuration endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from file_organizer.api.config import ApiSettings
from file_organizer.api.config_service import ConfigResponse, ConfigService
from file_organizer.api.dependencies import UserLike, get_current_active_user, get_db, get_settings

router = APIRouter(tags=["config"])


@router.get("/config", response_model=ConfigResponse)
def get_config(
    settings: ApiSettings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: UserLike = Depends(get_current_active_user),
) -> ConfigResponse:
    """Get current configuration from database.

    Configuration is stored persistently in the database and is thread-safe.
    User-specific configuration is supported when auth is enabled.
    """
    # Use user-specific config when auth is enabled, global config otherwise
    user_id = user.id if settings.auth_enabled and hasattr(user, "id") else None
    service = ConfigService(db, user_id=user_id)
    return service.get_config()


@router.put("/config", response_model=ConfigResponse)
def update_config(
    config_update: dict,
    settings: ApiSettings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: UserLike = Depends(get_current_active_user),
) -> ConfigResponse:
    """Update configuration with provided values.

    Updates are persisted to the database and protected with row-level locking
    to ensure thread-safety across multiple workers or instances.
    """
    # Use user-specific config when auth is enabled, global config otherwise
    user_id = user.id if settings.auth_enabled and hasattr(user, "id") else None
    service = ConfigService(db, user_id=user_id)
    return service.update_config(config_update)


@router.post("/config/reset", response_model=ConfigResponse)
def reset_config(
    settings: ApiSettings = Depends(get_settings),
    db: Session = Depends(get_db),
    user: UserLike = Depends(get_current_active_user),
) -> ConfigResponse:
    """Reset configuration to defaults.

    Deletes stored configuration from the database and returns default values.
    """
    # Use user-specific config when auth is enabled, global config otherwise
    user_id = user.id if settings.auth_enabled and hasattr(user, "id") else None
    service = ConfigService(db, user_id=user_id)
    return service.reset_config()
