"""Configuration endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

router = APIRouter(tags=["config"])


class AISettings(BaseModel):
    """AI model settings."""

    model_config = ConfigDict(extra="forbid")

    model: str = "qwen2.5:3b-instruct-q4_K_M"
    temperature: float = 0.5
    max_tokens: int = 3000


class StorageSettings(BaseModel):
    """Storage configuration."""

    model_config = ConfigDict(extra="forbid")

    base_path: str = "/default/path"
    auto_backup: bool = True


class OrganizationSettings(BaseModel):
    """Organization method settings."""

    model_config = ConfigDict(extra="forbid")

    method: str = "PARA"
    auto_organize: bool = False


class ConfigResponse(BaseModel):
    """Complete configuration response."""

    version: str = "2.0.0"
    ai: AISettings = AISettings()
    storage: StorageSettings = StorageSettings()
    organization: OrganizationSettings = OrganizationSettings()
    app_version: str = "2.0.0"


class ConfigUpdateRequest(BaseModel):
    """Request model for updating configuration with validation."""

    model_config = ConfigDict(extra="forbid")

    ai: AISettings | None = None
    storage: StorageSettings | None = None
    organization: OrganizationSettings | None = None


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
    """Update configuration with provided values."""
    global _config

    # Update config with provided values
    if config_update.organization is not None:
        _config.organization = OrganizationSettings(**{
            **_config.organization.model_dump(),
            **config_update.organization.model_dump(exclude_unset=True),
        })
    if config_update.ai is not None:
        _config.ai = AISettings(**{
            **_config.ai.model_dump(),
            **config_update.ai.model_dump(exclude_unset=True),
        })
    if config_update.storage is not None:
        _config.storage = StorageSettings(**{
            **_config.storage.model_dump(),
            **config_update.storage.model_dump(exclude_unset=True),
        })

    return _config


@router.post("/config/reset", response_model=ConfigResponse)
def reset_config(settings: ApiSettings = Depends(get_settings)) -> ConfigResponse:
    """Reset configuration to defaults."""
    global _config
    _config = ConfigResponse()
    return _config
