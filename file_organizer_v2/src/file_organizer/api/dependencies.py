"""Dependency providers for the API layer."""
from __future__ import annotations

from functools import lru_cache

from file_organizer.api.config import ApiSettings, load_settings


@lru_cache(maxsize=1)
def get_settings() -> ApiSettings:
    """Return cached API settings."""
    return load_settings()
