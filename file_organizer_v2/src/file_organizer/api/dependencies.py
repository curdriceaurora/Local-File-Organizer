"""Dependency providers for the API layer."""
from __future__ import annotations

import os
from functools import lru_cache

from file_organizer.api.config import ApiSettings, load_settings
from file_organizer.config.manager import ConfigManager


@lru_cache
def get_settings() -> ApiSettings:
    """Return API settings for request handlers."""
    return load_settings()


@lru_cache
def get_config_manager() -> ConfigManager:
    """Return a config manager, optionally overridden by FO_CONFIG_DIR."""
    config_dir = os.environ.get("FO_CONFIG_DIR")
    return ConfigManager(config_dir=config_dir)
