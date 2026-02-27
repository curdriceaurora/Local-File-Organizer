"""Unified configuration management for File Organizer."""

from __future__ import annotations

from file_organizer.config.manager import ConfigManager
from file_organizer.config.path_manager import PathManager
from file_organizer.config.path_migration import PathMigrator, detect_legacy_paths
from file_organizer.config.schema import AppConfig, ModelPreset, UpdateSettings

__all__ = [
    "AppConfig",
    "ConfigManager",
    "PathManager",
    "PathMigrator",
    "detect_legacy_paths",
    "ModelPreset",
    "UpdateSettings",
]
