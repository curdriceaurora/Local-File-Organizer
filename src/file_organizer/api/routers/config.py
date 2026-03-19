"""Configuration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings, require_admin_user

router = APIRouter(tags=["config"])


class AISettings(BaseModel):
    """AI model settings."""

    model: str = "qwen2.5:3b-instruct-q4_K_M"
    temperature: float = 0.5
    max_tokens: int = 3000


class StorageSettings(BaseModel):
    """Storage configuration."""

    base_path: str = "/default/path"
    auto_backup: bool = True


class OrganizationSettings(BaseModel):
    """Organization method settings."""

    method: str = "PARA"
    auto_organize: bool = False


class ConfigUpdateRequest(BaseModel):
    """Configuration update request."""

    ai: AISettings | None = None
    storage: StorageSettings | None = None
    organization: OrganizationSettings | None = None


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
    request: ConfigUpdateRequest,
    settings: ApiSettings = Depends(get_settings),
    _admin: object = Depends(require_admin_user),
) -> ConfigResponse:
    """Update configuration with provided values."""
    global _config

    # Update config with provided values
    if request.organization is not None:
        _config.organization = request.organization

    if request.ai is not None:
        _config.ai = request.ai

    if request.storage is not None:
        _config.storage = request.storage

    return _config


@router.post("/config/reset", response_model=ConfigResponse)
def reset_config(
    settings: ApiSettings = Depends(get_settings),
    _admin: object = Depends(require_admin_user),
) -> ConfigResponse:
    """Reset configuration to defaults."""
    global _config
    _config = ConfigResponse()
    return _config
