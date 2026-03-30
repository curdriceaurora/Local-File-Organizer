"""Configuration manager for File Organizer.

Handles loading, saving, and profile management for the unified
application configuration.

.. deprecated:: 2.0
    Use PathManager for path resolution instead of hardcoded paths.
    For new code, pass config_dir from PathManager.config_dir:

        from file_organizer.config.path_manager import PathManager
        path_manager = PathManager()
        config_manager = ConfigManager(config_dir=path_manager.config_dir)

See: docs/config/path-standardization.md
"""

from __future__ import annotations

import logging
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from file_organizer.config.path_manager import get_config_dir
from file_organizer.config.schema import AppConfig, ModelPreset, UpdateSettings
from file_organizer.models.base import DeviceType, ModelConfig, ModelType

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = get_config_dir()
CONFIG_FILENAME = "config.yaml"


class ConfigManager:
    """Manages application configuration profiles.

    Reads and writes YAML config files, supports multiple profiles,
    and delegates to module-specific config constructors.

    Args:
        config_dir: Directory for configuration files.
            Defaults to the platform config dir via platformdirs (e.g. ``~/Library/Application Support/file-organizer`` on macOS).
    """

    def __init__(self, config_dir: str | Path | None = None) -> None:
        """Set up the config manager using the given directory."""
        self._config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR

    @property
    def config_dir(self) -> Path:
        """Return the configuration directory path."""
        return self._config_dir

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def load(self, profile: str = "default") -> AppConfig:
        """Load a configuration profile from disk.

        If the config file or profile section is missing, returns
        an ``AppConfig`` with all defaults.

        Args:
            profile: Profile name to load.

        Returns:
            Loaded AppConfig instance.
        """
        config_path = self._config_dir / CONFIG_FILENAME

        if not config_path.exists():
            logger.debug("Config file not found at %s, using defaults", config_path)
            return AppConfig(profile_name=profile)

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Failed to parse %s, using defaults", config_path, exc_info=True)
            return AppConfig(profile_name=profile)

        if not isinstance(raw, dict):
            return AppConfig(profile_name=profile)

        profiles = raw.get("profiles", {})
        data = profiles.get(profile)

        if not isinstance(data, dict):
            logger.debug("Profile '%s' not found, using defaults", profile)
            return AppConfig(profile_name=profile)

        return self._dict_to_config(data, profile)

    def save(self, config: AppConfig, profile: str | None = None) -> None:
        """Save a configuration profile to disk.

        Creates the config directory and file if they don't exist.

        Args:
            config: AppConfig instance to persist.
            profile: Profile name override.  Uses ``config.profile_name``
                when *None*.
        """
        profile = profile or config.profile_name
        config_path = self._config_dir / CONFIG_FILENAME

        self._config_dir.mkdir(parents=True, exist_ok=True)

        # Load existing data to preserve other profiles
        existing: dict[str, Any] = {}
        if config_path.exists():
            try:
                existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except Exception:
                existing = {}

        if not isinstance(existing, dict):
            existing = {}

        profiles = existing.setdefault("profiles", {})
        profiles[profile] = self.config_to_dict(config)

        config_path.write_text(
            yaml.dump(existing, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        logger.info("Saved profile '%s' to %s", profile, config_path)

    def list_profiles(self) -> list[str]:
        """List available configuration profile names.

        Returns:
            Sorted list of profile name strings.
        """
        config_path = self._config_dir / CONFIG_FILENAME
        if not config_path.exists():
            return []

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        except Exception:
            return []

        if not isinstance(raw, dict):
            return []

        profiles = raw.get("profiles", {})
        if not isinstance(profiles, dict):
            return []

        return sorted(profiles.keys())

    def delete_profile(self, profile: str) -> bool:
        """Delete a configuration profile.

        Args:
            profile: Name of the profile to delete.

        Returns:
            True if the profile was deleted, False if not found.
        """
        config_path = self._config_dir / CONFIG_FILENAME
        if not config_path.exists():
            return False

        try:
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        except Exception:
            return False

        profiles = raw.get("profiles", {})
        if profile not in profiles:
            return False

        del profiles[profile]
        config_path.write_text(
            yaml.dump(raw, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        return True

    # ------------------------------------------------------------------
    # Module config delegation
    # ------------------------------------------------------------------

    def to_text_model_config(self, config: AppConfig) -> ModelConfig:
        """Create a ModelConfig for the text model from AppConfig.

        Args:
            config: Application configuration.

        Returns:
            ModelConfig configured for text inference.
        """
        return ModelConfig(
            name=config.models.text_model,
            model_type=ModelType.TEXT,
            temperature=config.models.temperature,
            max_tokens=config.models.max_tokens,
            device=DeviceType(config.models.device),
            framework=config.models.framework,
        )

    def to_vision_model_config(self, config: AppConfig) -> ModelConfig:
        """Create a ModelConfig for the vision model from AppConfig.

        Args:
            config: Application configuration.

        Returns:
            ModelConfig configured for vision inference.
        """
        return ModelConfig(
            name=config.models.vision_model,
            model_type=ModelType.VISION,
            temperature=config.models.temperature,
            max_tokens=config.models.max_tokens,
            device=DeviceType(config.models.device),
            framework=config.models.framework,
        )

    def to_watcher_config(self, config: AppConfig) -> Any:
        """Create a WatcherConfig from AppConfig overrides.

        Returns the module-specific WatcherConfig dataclass.
        Falls back to WatcherConfig defaults when no overrides are set.

        Args:
            config: Application configuration.

        Returns:
            WatcherConfig instance.
        """
        from file_organizer.watcher.config import WatcherConfig

        overrides = config.watcher or {}
        # Convert directory strings to Paths
        if "watch_directories" in overrides:
            overrides["watch_directories"] = [Path(d) for d in overrides["watch_directories"]]
        return WatcherConfig(**overrides)

    def to_daemon_config(self, config: AppConfig) -> Any:
        """Create a DaemonConfig from AppConfig overrides.

        Args:
            config: Application configuration.

        Returns:
            DaemonConfig instance.
        """
        from file_organizer.daemon.config import DaemonConfig

        overrides = config.daemon or {}
        if "watch_directories" in overrides:
            overrides["watch_directories"] = [Path(d) for d in overrides["watch_directories"]]
        if "output_directory" in overrides:
            overrides["output_directory"] = Path(overrides["output_directory"])
        return DaemonConfig(**overrides)

    def to_parallel_config(self, config: AppConfig) -> Any:
        """Create a ParallelConfig from AppConfig overrides.

        Args:
            config: Application configuration.

        Returns:
            ParallelConfig instance.
        """
        from file_organizer.parallel.config import ParallelConfig

        overrides = config.parallel or {}
        return ParallelConfig(**overrides)

    def to_event_config(self, config: AppConfig) -> Any:
        """Create an EventConfig from AppConfig overrides.

        Args:
            config: Application configuration.

        Returns:
            EventConfig instance.
        """
        from file_organizer.events.config import EventConfig

        overrides = config.events or {}
        return EventConfig(**overrides)

    def to_deploy_config(self, config: AppConfig) -> Any:
        """Create a DeploymentConfig from AppConfig overrides.

        Args:
            config: Application configuration.

        Returns:
            DeploymentConfig instance.
        """
        from file_organizer.deploy.config import DeploymentConfig

        overrides = config.deploy or {}
        return DeploymentConfig(**overrides)

    def to_para_config(self, config: AppConfig) -> Any:
        """Create a PARAConfig from AppConfig overrides.

        Args:
            config: Application configuration.

        Returns:
            PARAConfig instance.
        """
        from file_organizer.methodologies.para.config import PARAConfig

        overrides = config.para or {}
        return PARAConfig(**overrides)

    def to_johnny_decimal_config(self, config: AppConfig) -> Any:
        """Create a JohnnyDecimalConfig from AppConfig overrides.

        JohnnyDecimalConfig requires a ``scheme`` parameter, so this
        delegates to the module's ``create_default_config()`` factory
        when no overrides are provided.

        Args:
            config: Application configuration.

        Returns:
            JohnnyDecimalConfig instance.
        """
        from file_organizer.methodologies.johnny_decimal.config import (
            create_default_config,
        )

        overrides = config.johnny_decimal
        if not overrides:
            return create_default_config()
        return create_default_config(**overrides)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def config_to_dict(self, config: AppConfig) -> dict[str, Any]:
        """Serialize an AppConfig to a plain dict for API and YAML output."""
        return self._config_to_dict(config)

    @staticmethod
    def _config_to_dict(config: AppConfig) -> dict[str, Any]:
        """Serialize an AppConfig to a plain dict for YAML output."""
        data: dict[str, Any] = {
            "version": config.version,
            "default_methodology": config.default_methodology,
            "setup_completed": config.setup_completed,
            "models": asdict(config.models),
            "updates": asdict(config.updates),
        }

        # Only include module overrides that are set
        for name in (
            "watcher",
            "daemon",
            "parallel",
            "pipeline",
            "events",
            "deploy",
            "para",
            "johnny_decimal",
        ):
            value = getattr(config, name)
            if value is not None:
                data[name] = value

        return data

    @staticmethod
    def _dict_to_config(data: dict[str, Any], profile: str) -> AppConfig:
        """Deserialize a dict (from YAML) into an AppConfig."""
        models_data = data.get("models", {})
        if isinstance(models_data, dict):
            # Only pass keys that ModelPreset accepts
            valid_keys = {f.name for f in fields(ModelPreset)}
            models_data = {k: v for k, v in models_data.items() if k in valid_keys}
            models = ModelPreset(**models_data)
        else:
            models = ModelPreset()

        updates_data = data.get("updates", {})
        if isinstance(updates_data, dict):
            valid_update_keys = {f.name for f in fields(UpdateSettings)}
            updates_data = {k: v for k, v in updates_data.items() if k in valid_update_keys}
            updates = UpdateSettings(**updates_data)
        else:
            updates = UpdateSettings()

        return AppConfig(
            profile_name=profile,
            version=data.get("version", "1.0"),
            default_methodology=data.get("default_methodology", "none"),
            setup_completed=data.get("setup_completed", False),
            models=models,
            updates=updates,
            watcher=data.get("watcher"),
            daemon=data.get("daemon"),
            parallel=data.get("parallel"),
            pipeline=data.get("pipeline"),
            events=data.get("events"),
            deploy=data.get("deploy"),
            para=data.get("para"),
            johnny_decimal=data.get("johnny_decimal"),
        )
