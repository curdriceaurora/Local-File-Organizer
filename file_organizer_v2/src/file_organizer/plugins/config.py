"""Plugin configuration persistence."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from file_organizer.plugins.errors import PluginConfigError

_PLUGIN_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _validate_plugin_name(name: str) -> str:
    candidate = name.strip()
    if not _PLUGIN_NAME_PATTERN.match(candidate):
        raise PluginConfigError(f"Invalid plugin name: {name!r}")
    return candidate


@dataclass
class PluginConfig:
    """Configuration payload stored per plugin."""

    name: str
    enabled: bool = False
    settings: dict[str, Any] = field(default_factory=dict)
    permissions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "settings": self.settings,
            "permissions": self.permissions,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PluginConfig:
        if not isinstance(payload, dict):
            raise PluginConfigError("Plugin config payload must be a mapping.")
        raw_name = payload.get("name")
        if not isinstance(raw_name, str):
            raise PluginConfigError("Plugin config is missing a valid 'name'.")
        name = _validate_plugin_name(raw_name)
        enabled = bool(payload.get("enabled", False))
        raw_settings = payload.get("settings", {})
        settings = raw_settings if isinstance(raw_settings, dict) else {}
        raw_permissions = payload.get("permissions", [])
        permissions = (
            [str(permission) for permission in raw_permissions]
            if isinstance(raw_permissions, list)
            else []
        )
        return cls(name=name, enabled=enabled, settings=settings, permissions=permissions)


class PluginConfigManager:
    """Read/write plugin configuration files."""

    def __init__(self, config_dir: str | Path) -> None:
        self._config_dir = Path(config_dir)

    @property
    def config_dir(self) -> Path:
        return self._config_dir

    def config_path(self, name: str) -> Path:
        validated_name = _validate_plugin_name(name)
        return self._config_dir / f"{validated_name}.json"

    def load_config(self, name: str) -> PluginConfig:
        """Load config from disk; return defaults when no config exists."""
        validated_name = _validate_plugin_name(name)
        path = self.config_path(validated_name)
        if not path.exists():
            return PluginConfig(name=validated_name)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise PluginConfigError(
                f"Failed to read config for plugin '{validated_name}'."
            ) from exc
        except json.JSONDecodeError as exc:
            raise PluginConfigError(
                f"Config for plugin '{validated_name}' is not valid JSON."
            ) from exc
        if not isinstance(payload, dict):
            raise PluginConfigError(f"Config for plugin '{validated_name}' must be a JSON object.")
        payload.setdefault("name", validated_name)
        config = PluginConfig.from_dict(payload)
        if config.name != validated_name:
            raise PluginConfigError(
                f"Config name mismatch: expected '{validated_name}', got '{config.name}'."
            )
        return config

    def save_config(self, config: PluginConfig) -> None:
        """Persist config atomically to avoid partial writes."""
        validated_name = _validate_plugin_name(config.name)
        payload = dict(config.to_dict())
        payload["name"] = validated_name
        self._config_dir.mkdir(parents=True, exist_ok=True)
        target_path = self.config_path(validated_name)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self._config_dir),
            prefix=f".{validated_name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            Path(tmp_path).replace(target_path)
        except OSError as exc:
            raise PluginConfigError(
                f"Failed to persist config for plugin '{validated_name}'."
            ) from exc
        finally:
            leftover = Path(tmp_path)
            if leftover.exists():
                leftover.unlink(missing_ok=True)

    def list_configured_plugins(self) -> list[str]:
        """Return plugin names that have explicit config files."""
        if not self._config_dir.exists():
            return []
        names: list[str] = []
        for entry in sorted(self._config_dir.glob("*.json")):
            candidate = entry.stem
            if _PLUGIN_NAME_PATTERN.match(candidate):
                names.append(candidate)
        return names
