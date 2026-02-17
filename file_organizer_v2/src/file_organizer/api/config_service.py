"""Configuration service with database persistence."""
from __future__ import annotations

import json
from typing import Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from file_organizer.api.db_models import SettingsStore


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


class ConfigService:
    """Thread-safe configuration service with database persistence.

    This service provides persistent storage for application configuration
    using the database instead of in-memory storage. Configuration is stored
    per-user or globally (when user_id is None).
    """

    CONFIG_KEY = "app_config"

    def __init__(self, db: Session, user_id: Optional[str] = None):
        """Initialize the configuration service.

        Args:
            db: Database session for persistence operations
            user_id: Optional user ID for user-specific config (None for global)
        """
        self.db = db
        self.user_id = user_id

    def get_config(self) -> ConfigResponse:
        """Get current configuration from database.

        Returns:
            ConfigResponse: Current configuration or defaults if not set
        """
        # Query without locking for read operations
        setting = (
            self.db.query(SettingsStore)
            .filter(
                SettingsStore.user_id == self.user_id,
                SettingsStore.key == self.CONFIG_KEY,
            )
            .first()
        )

        if setting and setting.value:
            try:
                data = json.loads(setting.value)
                return ConfigResponse(**data)
            except (json.JSONDecodeError, ValueError):
                # Return defaults if stored data is corrupted
                return ConfigResponse()

        return ConfigResponse()

    def update_config(self, config_update: dict) -> ConfigResponse:
        """Update configuration with provided values.

        Args:
            config_update: Dictionary with configuration updates

        Returns:
            ConfigResponse: Updated configuration
        """
        # Use row-level locking to ensure thread-safe updates
        setting = (
            self.db.query(SettingsStore)
            .filter(
                SettingsStore.user_id == self.user_id,
                SettingsStore.key == self.CONFIG_KEY,
            )
            .with_for_update()
            .first()
        )

        # Get current config or defaults
        if setting and setting.value:
            try:
                current_data = json.loads(setting.value)
                current_config = ConfigResponse(**current_data)
            except (json.JSONDecodeError, ValueError):
                current_config = ConfigResponse()
        else:
            current_config = ConfigResponse()

        # Apply updates to current config
        if "organization" in config_update:
            current_config.organization = OrganizationSettings(
                **{
                    **current_config.organization.model_dump(),
                    **config_update["organization"],
                }
            )
        if "ai" in config_update:
            current_config.ai = AISettings(
                **{
                    **current_config.ai.model_dump(),
                    **config_update["ai"],
                }
            )
        if "storage" in config_update:
            current_config.storage = StorageSettings(
                **{
                    **current_config.storage.model_dump(),
                    **config_update["storage"],
                }
            )

        # Serialize and save to database
        config_json = current_config.model_dump_json()

        if setting:
            setting.value = config_json
        else:
            setting = SettingsStore(
                user_id=self.user_id,
                key=self.CONFIG_KEY,
                value=config_json,
            )
            self.db.add(setting)

        self.db.commit()
        self.db.refresh(setting)

        return current_config

    def reset_config(self) -> ConfigResponse:
        """Reset configuration to defaults.

        Returns:
            ConfigResponse: Default configuration
        """
        # Use row-level locking for thread-safe deletion
        setting = (
            self.db.query(SettingsStore)
            .filter(
                SettingsStore.user_id == self.user_id,
                SettingsStore.key == self.CONFIG_KEY,
            )
            .with_for_update()
            .first()
        )

        if setting:
            self.db.delete(setting)
            self.db.commit()

        return ConfigResponse()
