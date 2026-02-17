"""Configuration endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

router = APIRouter(tags=["config"])


class AISettings(BaseModel):
    """AI model settings."""

    model: str = "qwen2.5:3b-instruct-q4_K_M"
    temperature: float = Field(default=0.5, ge=0.0, le=2.0)
    max_tokens: int = Field(default=3000, gt=0, le=100000)


class StorageSettings(BaseModel):
    """Storage configuration."""

    base_path: str = "/default/path"
    auto_backup: bool = True


class OrganizationSettings(BaseModel):
    """Organization method settings."""

    method: str = "PARA"
    auto_organize: bool = False


class AISettingsUpdate(BaseModel):
    """Partial AI model settings for updates."""

    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0, le=100000)


class StorageSettingsUpdate(BaseModel):
    """Partial storage configuration for updates."""

    base_path: Optional[str] = None
    auto_backup: Optional[bool] = None


class OrganizationSettingsUpdate(BaseModel):
    """Partial organization method settings for updates."""

    method: Optional[str] = None
    auto_organize: Optional[bool] = None


class ConfigUpdateRequest(BaseModel):
    """Configuration update request with validated fields."""

    ai: Optional[AISettingsUpdate] = None
    storage: Optional[StorageSettingsUpdate] = None
    organization: Optional[OrganizationSettingsUpdate] = None


class ConfigResponse(BaseModel):
    """Complete configuration response."""

    version: str = "2.0.0"
    ai: AISettings = AISettings()
    storage: StorageSettings = StorageSettings()
    organization: OrganizationSettings = OrganizationSettings()
    app_version: str = "2.0.0"


# Global config store (in-memory for testing)
_config = ConfigResponse()


@router.get("/config", response_model=ConfigResponse)
def get_config(settings: ApiSettings = Depends(get_settings)) -> ConfigResponse:
    """Get current configuration."""
    global _config
    return _config


@router.put("/config", response_model=ConfigResponse)
def update_config(
    config_update: ConfigUpdateRequest,
    settings: ApiSettings = Depends(get_settings),
) -> ConfigResponse:
    """Update configuration with provided values.
    
    Uses Pydantic models for input validation to prevent injection
    of malicious configuration values or unauthorized overwrites.
    """
    global _config

    # Update config with validated values
    if config_update.organization is not None:
        update_data = config_update.organization.model_dump(exclude_none=True)
        _config.organization = OrganizationSettings(**{
            **_config.organization.model_dump(),
            **update_data,
        })
    if config_update.ai is not None:
        update_data = config_update.ai.model_dump(exclude_none=True)
        _config.ai = AISettings(**{
            **_config.ai.model_dump(),
            **update_data,
        })
    if config_update.storage is not None:
        update_data = config_update.storage.model_dump(exclude_none=True)
        _config.storage = StorageSettings(**{
            **_config.storage.model_dump(),
            **update_data,
        })

    return _config


@router.post("/config/reset", response_model=ConfigResponse)
def reset_config(settings: ApiSettings = Depends(get_settings)) -> ConfigResponse:
    """Reset configuration to defaults."""
    global _config
    _config = ConfigResponse()
    return _config
