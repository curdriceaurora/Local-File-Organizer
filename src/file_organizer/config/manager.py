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

from file_organizer.config.methodology import normalize as normalize_methodology
from file_organizer.config.migrations import compare_versions, migrate_to_current
from file_organizer.config.path_manager import get_config_dir
from file_organizer.config.schema import (
    CURRENT_SCHEMA_VERSION,
    SUPPORTED_SCHEMA_VERSIONS,
    AppConfig,
    ModelPreset,
    UpdateSettings,
)
from file_organizer.models.base import DeviceType, ModelConfig, ModelType
from file_organizer.utils.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = get_config_dir()
CONFIG_FILENAME = "config.yaml"

# AppConfig fields with dedicated (de)serialization behavior. Every other
# field is copied straight through by name — adding a new plain field to
# AppConfig requires no changes here. See #1542.
_NESTED_DATACLASS_TYPES: dict[str, type] = {
    "models": ModelPreset,
    "updates": UpdateSettings,
}
_MODULE_OVERRIDE_FIELDS = frozenset(
    {
        "watcher",
        "daemon",
        "parallel",
        "pipeline",
        "events",
        "deploy",
        "para",
        "johnny_decimal",
    }
)
# profile_name is the dict key under "profiles" in the on-disk YAML, not a
# serialized field of the profile body itself.
_EXCLUDED_FIELDS = frozenset({"profile_name"})


class UnsupportedConfigVersionError(RuntimeError):
    """Raised when a save would overwrite an unsupported-version profile.

    ``load()`` degrades an unsupported-version profile to defaults (read-side
    migration safety), so a load-mutate-save would otherwise clobber the
    incompatible file. Pass ``force=True`` to :meth:`ConfigManager.save` to
    overwrite/migrate intentionally.
    """

    def __init__(self, profile: str, version: object) -> None:
        """Record the offending *profile* and on-disk *version*."""
        self.profile = profile
        self.version = version
        super().__init__(
            f"Refusing to overwrite profile {profile!r}: on-disk schema version "
            f"{version!r} is unsupported (supported: "
            f"{sorted(SUPPORTED_SCHEMA_VERSIONS)}). Pass force=True to overwrite."
        )


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
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            logger.warning("Failed to parse %s, using defaults", config_path, exc_info=True)
            return AppConfig(profile_name=profile)

        if not isinstance(raw, dict):
            return AppConfig(profile_name=profile)

        profiles = raw.get("profiles", {})
        data = profiles.get(profile)

        if not isinstance(data, dict):
            logger.debug("Profile '%s' not found, using defaults", profile)
            return AppConfig(profile_name=profile)

        disk_version = str(data.get("version", CURRENT_SCHEMA_VERSION))
        if disk_version != CURRENT_SCHEMA_VERSION:
            if compare_versions(disk_version, CURRENT_SCHEMA_VERSION) > 0:
                logger.warning(
                    "Profile '%s' in %s has a newer unsupported "
                    "schema version %s (current is %s). Loading best-effort; fields "
                    "introduced in the newer schema may be dropped. "
                    "Consider upgrading fo to keep settings lossless.",
                    profile,
                    config_path,
                    disk_version,
                    CURRENT_SCHEMA_VERSION,
                )
            else:
                logger.info(
                    "Migrating config from version %s to %s",
                    disk_version,
                    CURRENT_SCHEMA_VERSION,
                )
                try:
                    data = migrate_to_current(
                        data,
                        from_version=disk_version,
                        to_version=CURRENT_SCHEMA_VERSION,
                    )
                except Exception:
                    logger.error(
                        "Config migration from %s to %s failed; "
                        "falling back to defaults. The on-disk file is "
                        "left untouched — your previous config is safe.",
                        disk_version,
                        CURRENT_SCHEMA_VERSION,
                        exc_info=True,
                    )
                    return AppConfig(profile_name=profile)

        return self._dict_to_config(data, profile)

    def save(self, config: AppConfig, profile: str | None = None, *, force: bool = False) -> None:
        """Save a configuration profile to disk.

        Creates the config directory and file if they don't exist.

        Args:
            config: AppConfig instance to persist.
            profile: Profile name override.  Uses ``config.profile_name``
                when *None*.
            force: Overwrite even when the existing on-disk profile was written
                under an unsupported schema version. Defaults to ``False``, which
                refuses such an overwrite (migration-safe — ``load()`` returns
                defaults for an unsupported version, so a load-mutate-save would
                otherwise clobber the incompatible file).

        Raises:
            UnsupportedConfigVersionError: The on-disk profile has an unsupported
                schema version and ``force`` is ``False``.
        """
        profile = profile or config.profile_name
        config_path = self._config_dir / CONFIG_FILENAME

        self._config_dir.mkdir(parents=True, exist_ok=True)

        # Load existing data to preserve other profiles
        existing: dict[str, Any] = {}
        if config_path.exists():
            try:
                existing = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError, UnicodeDecodeError):
                logger.warning(
                    "Failed to load existing config from %s, starting fresh",
                    config_path,
                    exc_info=True,
                )
                existing = {}

        if not isinstance(existing, dict):
            existing = {}

        # Migration-safe write guard (F6): refuse to clobber a profile whose
        # on-disk schema version is unsupported. load() degrades such a profile
        # to defaults, so a load-mutate-save would otherwise overwrite the
        # incompatible file with default/current-schema data (see #1276).
        if not force:
            existing_profiles = existing.get("profiles")
            existing_profile = (
                existing_profiles.get(profile) if isinstance(existing_profiles, dict) else None
            )
            if isinstance(existing_profile, dict):
                on_disk_version = existing_profile.get("version")
                if (
                    on_disk_version is not None
                    and str(on_disk_version) not in SUPPORTED_SCHEMA_VERSIONS
                ):
                    raise UnsupportedConfigVersionError(profile, on_disk_version)

        profiles = existing.setdefault("profiles", {})
        profiles[profile] = self.config_to_dict(config)

        # Atomic write: a mid-write crash leaves the prior config intact rather
        # than a truncated/corrupt file.
        atomic_write_text(
            config_path,
            yaml.dump(existing, default_flow_style=False, sort_keys=False),
        )
        logger.info("Saved profile '%s' to %s", profile, config_path)

    @staticmethod
    def mark_setup_completed(config: AppConfig) -> None:
        """Flag *config* as having completed guided setup, in place.

        Sets ``setup_completed=True`` and clears ``setup_deferred``. Does not
        persist — callers save afterward, typically with ``force=True`` since
        setup completion is a deliberate (re)configuration that should
        migrate/overwrite an unsupported-version profile rather than fail the
        save guard (#1276).
        """
        config.setup_completed = True
        config.setup_deferred = False

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
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
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
        except (OSError, yaml.YAMLError, UnicodeDecodeError):
            logger.warning(
                "Failed to load config while deleting profile %s", profile, exc_info=True
            )
            return False

        if not isinstance(raw, dict):
            return False

        profiles = raw.get("profiles", {})
        if not isinstance(profiles, dict):
            return False
        if profile not in profiles:
            return False

        del profiles[profile]
        atomic_write_text(
            config_path,
            yaml.dump(raw, default_flow_style=False, sort_keys=False),
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
        """Serialize an AppConfig to a plain dict for YAML output.

        Iterates ``dataclasses.fields(AppConfig)`` so a new plain field needs
        no changes here; only nested dataclasses, module-override dicts, and
        the version stamp have dedicated handling (see the module-level
        field registries near the top of this file).

        F6: always stamps CURRENT_SCHEMA_VERSION into the serialized record
        rather than the in-memory config.version field. After a successful
        migration, the migrated data needs to be written back with the new
        version stamp so the next load doesn't re-trigger migration.
        """
        data: dict[str, Any] = {}
        for f in fields(config):
            name = f.name
            if name in _EXCLUDED_FIELDS:
                continue
            if name == "version":
                data[name] = CURRENT_SCHEMA_VERSION
            elif name in _NESTED_DATACLASS_TYPES:
                data[name] = asdict(getattr(config, name))
            elif name in _MODULE_OVERRIDE_FIELDS:
                # Only include module overrides that are set.
                value = getattr(config, name)
                if value is not None:
                    data[name] = value
            else:
                data[name] = getattr(config, name)

        return data

    @staticmethod
    def _dict_to_config(data: dict[str, Any], profile: str) -> AppConfig:
        """Deserialize a dict (from YAML) into an AppConfig.

        Mirrors :meth:`_config_to_dict`: plain fields absent from *data* fall
        through to the ``AppConfig`` dataclass's own default rather than
        repeating it here.
        """
        kwargs: dict[str, Any] = {"profile_name": profile}
        for f in fields(AppConfig):
            name = f.name
            if name == "profile_name":
                continue
            if name == "version":
                # Normalize to str so a YAML-parsed float (``version: 1.0``)
                # does not leak through as a float despite the ``str``
                # annotation.
                kwargs[name] = str(data.get("version", CURRENT_SCHEMA_VERSION))
            elif name == "default_methodology":
                kwargs[name] = normalize_methodology(data.get("default_methodology"))
            elif name in _NESTED_DATACLASS_TYPES:
                dataclass_type = _NESTED_DATACLASS_TYPES[name]
                raw = data.get(name, {})
                if isinstance(raw, dict):
                    # Only pass keys the nested dataclass accepts.
                    valid_keys = {nf.name for nf in fields(dataclass_type)}
                    raw = {k: v for k, v in raw.items() if k in valid_keys}
                    kwargs[name] = dataclass_type(**raw)
                else:
                    kwargs[name] = dataclass_type()
            elif name in _MODULE_OVERRIDE_FIELDS:
                kwargs[name] = data.get(name)
            elif name in data:
                kwargs[name] = data[name]

        return AppConfig(**kwargs)
