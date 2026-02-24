"""Plugin base contracts."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from file_organizer.plugins.errors import (
    PluginError,
    PluginLoadError,
    PluginPermissionError,
)
from file_organizer.plugins.security import PluginSandbox

# Re-export errors for backward compatibility with code that imports
# PluginError/PluginLoadError/PluginPermissionError from this module.
__all__ = [
    "Plugin",
    "PluginError",
    "PluginLoadError",
    "PluginMetadata",
    "PluginPermissionError",
    "load_manifest",
    "validate_manifest",
]

# ---------------------------------------------------------------------------
# Manifest schema constants
# ---------------------------------------------------------------------------

MANIFEST_FILENAME = "plugin.json"

MANIFEST_REQUIRED_FIELDS: dict[str, type] = {
    "name": str,
    "version": str,
    "author": str,
    "description": str,
    "entry_point": str,
}

MANIFEST_OPTIONAL_FIELDS: dict[str, tuple[type | None, Any]] = {
    # field_name -> (expected_type_or_None, default_value)
    # Defaults are tuples/strings/None — intentionally immutable so that callers
    # who read this schema directly cannot accidentally mutate shared state.
    "license": (str, "MIT"),
    "homepage": (str, None),  # nullable
    "dependencies": (list, ()),
    "min_organizer_version": (str, "2.0.0"),
    "max_organizer_version": (str, None),  # nullable
    "allowed_paths": (list, ()),
}


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def load_manifest(plugin_dir: Path) -> dict[str, Any]:
    """Read and validate ``plugin.json`` from *plugin_dir*.

    Args:
        plugin_dir: Directory containing ``plugin.json``.

    Returns:
        Validated manifest dictionary with defaults applied for optional
        fields.

    Raises:
        PluginLoadError: If the file is missing, unreadable, or invalid.
    """
    manifest_path = plugin_dir / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise PluginLoadError(
            f"Manifest file not found: {manifest_path}. "
            "Every plugin directory must contain a plugin.json file."
        )

    try:
        raw = manifest_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PluginLoadError(f"Cannot read manifest {manifest_path}: {exc}") from exc

    try:
        manifest: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PluginLoadError(
            f"Invalid JSON in {manifest_path}: {exc}"
        ) from exc

    if not isinstance(manifest, dict):
        raise PluginLoadError(
            f"Manifest must be a JSON object, got {type(manifest).__name__}: {manifest_path}"
        )

    validate_manifest(manifest, manifest_path)

    # Apply defaults for missing optional fields.  Schema defaults are
    # immutable (tuples/strings/None); convert sequence defaults to lists
    # so downstream code gets the mutable type it expects.
    for field_name, (_ftype, default) in MANIFEST_OPTIONAL_FIELDS.items():
        if field_name not in manifest:
            manifest[field_name] = list(default) if isinstance(default, (list, tuple)) else default

    return manifest


def validate_manifest(
    manifest: dict[str, Any],
    source: Path | str = "<unknown>",
) -> None:
    """Check that *manifest* contains all required fields with correct types.

    Args:
        manifest: Parsed JSON dictionary.
        source: Path or label used in error messages.

    Raises:
        PluginLoadError: On missing or wrongly-typed fields.
    """
    # Required fields
    for field_name, expected_type in MANIFEST_REQUIRED_FIELDS.items():
        if field_name not in manifest:
            raise PluginLoadError(
                f"Manifest {source} is missing required field '{field_name}'."
            )
        value = manifest[field_name]
        if not isinstance(value, expected_type):
            raise PluginLoadError(
                f"Manifest {source}: field '{field_name}' must be "
                f"{expected_type.__name__}, got {type(value).__name__}."
            )

    # Optional fields — only type-check if present
    for field_name, (expected_type, default) in MANIFEST_OPTIONAL_FIELDS.items():
        if field_name not in manifest:
            continue
        value = manifest[field_name]
        # Allow None only for explicitly nullable fields (those whose default is None)
        if value is None and default is None:
            continue
        if value is None:
            raise PluginLoadError(
                f"Manifest {source}: field '{field_name}' must not be null."
            )
        if expected_type is not None and not isinstance(value, expected_type):
            raise PluginLoadError(
                f"Manifest {source}: field '{field_name}' must be "
                f"{expected_type.__name__}, got {type(value).__name__}."
            )


@dataclass(frozen=True)
class PluginMetadata:
    """Immutable metadata describing plugin identity and compatibility."""

    name: str
    version: str
    author: str
    description: str
    homepage: str | None = None
    license: str = "MIT"
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    min_organizer_version: str = "2.0.0"
    max_organizer_version: str | None = None


class Plugin(ABC):
    """Base interface all plugins must implement."""

    def __init__(
        self,
        config: Mapping[str, Any] | None = None,
        *,
        sandbox: PluginSandbox | None = None,
    ) -> None:
        """Set up the plugin with the given configuration and sandbox."""
        self.config: dict[str, Any] = dict(config or {})
        self.sandbox = sandbox or PluginSandbox(plugin_name=self.__class__.__name__)
        self._enabled = False

    @property
    def enabled(self) -> bool:
        """Return whether the plugin is active."""
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Set runtime activation state for lifecycle orchestration."""
        self._enabled = enabled

    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""

    @abstractmethod
    def on_load(self) -> None:
        """Handle load lifecycle event."""

    @abstractmethod
    def on_enable(self) -> None:
        """Handle enable lifecycle event."""

    @abstractmethod
    def on_disable(self) -> None:
        """Handle disable lifecycle event."""

    @abstractmethod
    def on_unload(self) -> None:
        """Handle unload lifecycle event."""
