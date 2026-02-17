"""Configuration endpoints."""
from __future__ import annotations

import threading
from functools import lru_cache
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_settings

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


class ConfigResponse(BaseModel):
    """Complete configuration response."""

    version: str = "2.0.0"
    ai: AISettings = AISettings()
    storage: StorageSettings = StorageSettings()
    organization: OrganizationSettings = OrganizationSettings()
    app_version: str = "2.0.0"


class ConfigStore:
    """Thread-safe configuration storage using a lock for concurrent access."""

    def __init__(self) -> None:
        self._config = ConfigResponse()
        self._lock = threading.Lock()

    def get(self) -> ConfigResponse:
        """Get a copy of the current configuration."""
        with self._lock:
            return self._config.model_copy(deep=True)

    def update(self, config_update: dict[str, Any]) -> ConfigResponse:
        """Update configuration with provided values."""
        with self._lock:
            if "organization" in config_update:
                self._config.organization = OrganizationSettings(**{
                    **self._config.organization.model_dump(),
                    **config_update["organization"],
                })
            if "ai" in config_update:
                self._config.ai = AISettings(**{
                    **self._config.ai.model_dump(),
                    **config_update["ai"],
                })
            if "storage" in config_update:
                self._config.storage = StorageSettings(**{
                    **self._config.storage.model_dump(),
                    **config_update["storage"],
                })
            return self._config.model_copy(deep=True)

    def reset(self) -> ConfigResponse:
        """Reset configuration to defaults."""
        with self._lock:
            self._config = ConfigResponse()
            return self._config.model_copy(deep=True)


@lru_cache
def _get_config_store() -> ConfigStore:
    """Return a singleton ConfigStore instance."""
    return ConfigStore()


def get_config_store(request: Optional[Request] = None) -> ConfigStore:
    """Dependency to get the config store.

    If a request is provided and has app.state.config_store, use that.
    Otherwise, fall back to the singleton instance.
    """
    if request is not None and hasattr(request.app, "state"):
        store = getattr(request.app.state, "config_store", None)
        if store is not None:
            return store
    return _get_config_store()


@router.get("/config", response_model=ConfigResponse)
def get_config(
    settings: ApiSettings = Depends(get_settings),
    store: ConfigStore = Depends(get_config_store),
) -> ConfigResponse:
    """Get current configuration."""
    return store.get()


@router.put("/config", response_model=ConfigResponse)
def update_config(
    config_update: dict[str, Any],
    settings: ApiSettings = Depends(get_settings),
    store: ConfigStore = Depends(get_config_store),
) -> ConfigResponse:
    """Update configuration with provided values."""
    return store.update(config_update)


@router.post("/config/reset", response_model=ConfigResponse)
def reset_config(
    settings: ApiSettings = Depends(get_settings),
    store: ConfigStore = Depends(get_config_store),
) -> ConfigResponse:
    """Reset configuration to defaults."""
    return store.reset()
