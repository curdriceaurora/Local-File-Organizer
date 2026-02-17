"""Configuration endpoints."""
from __future__ import annotations

from enum import Enum
from typing import Optional, TypeVar

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

router = APIRouter(tags=["config"])

# TypeVar for generic merge function - represents a BaseModel subclass
T = TypeVar("T", bound=BaseModel)


class OrganizationMethod(str, Enum):
    """Valid organization methods."""

    PARA = "PARA"
    DATE = "DATE"
    CONTENT = "content_based"
    NONE = "none"


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

    method: OrganizationMethod = OrganizationMethod.PARA
    auto_organize: bool = False


class AISettingsUpdate(BaseModel):
    """Partial update model for AI model settings (model name, temperature, max_tokens).
    
    All fields are optional. When provided, they must pass validation.
    """

    model_config = ConfigDict(validate_assignment=True)

    model: Optional[str] = None
    temperature: Optional[float] = Field(default=None, ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(default=None, gt=0, le=100000)


class StorageSettingsUpdate(BaseModel):
    """Partial update model for storage configuration (base path, auto backup).
    
    All fields are optional. When provided, they must pass validation.
    """

    model_config = ConfigDict(validate_assignment=True)

    base_path: Optional[str] = None
    auto_backup: Optional[bool] = None


class OrganizationSettingsUpdate(BaseModel):
    """Partial update model for organization settings (method, auto-organize flag).
    
    All fields are optional. When provided, they must pass validation.
    """

    model_config = ConfigDict(validate_assignment=True)

    method: Optional[OrganizationMethod] = None
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


def _merge_update(current: T, update: BaseModel) -> T:
    """Merge update data into current configuration.
    
    Args:
        current: Current configuration object
        update: Update object with optional fields
        
    Returns:
        New configuration object with merged data
    """
    update_data = update.model_dump(exclude_none=True)
    merged_data = {**current.model_dump(), **update_data}
    return type(current)(**merged_data)


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
        _config.organization = _merge_update(_config.organization, config_update.organization)
    if config_update.ai is not None:
        _config.ai = _merge_update(_config.ai, config_update.ai)
    if config_update.storage is not None:
        _config.storage = _merge_update(_config.storage, config_update.storage)

    return _config


@router.post("/config/reset", response_model=ConfigResponse)
def reset_config(settings: ApiSettings = Depends(get_settings)) -> ConfigResponse:
    """Reset configuration to defaults."""
    global _config
    _config = ConfigResponse()
    return _config
