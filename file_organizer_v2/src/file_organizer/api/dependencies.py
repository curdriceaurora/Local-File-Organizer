"""Dependency providers for the API layer."""
from __future__ import annotations

from file_organizer.api.config import ApiSettings, load_settings


def get_settings() -> ApiSettings:
    """Return API settings for request handlers."""
    return load_settings()
