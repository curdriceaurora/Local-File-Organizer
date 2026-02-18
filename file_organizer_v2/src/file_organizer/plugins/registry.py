"""Plugin discovery and loading registry."""

from __future__ import annotations

import importlib.util
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from types import ModuleType
from uuid import uuid4

from file_organizer.plugins.base import Plugin, PluginMetadata
from file_organizer.plugins.config import PluginConfig, PluginConfigManager
from file_organizer.plugins.errors import (
    PluginDependencyError,
    PluginDiscoveryError,
    PluginLoadError,
    PluginNotFoundError,
    PluginNotLoadedError,
)
from file_organizer.plugins.security import PluginSandbox, PluginSecurityPolicy


@dataclass(frozen=True)
class PluginRecord:
    """Loaded plugin record."""

    name: str
    path: Path
    module_name: str
    module: ModuleType
    plugin: Plugin
    metadata: PluginMetadata


class PluginRegistry:
    """Discover, load, and unload third-party plugins."""

    def __init__(
        self,
        plugin_dir: str | Path,
        *,
        config_manager: PluginConfigManager | None = None,
    ) -> None:
        self.plugin_dir = Path(plugin_dir)
        self._config_manager = config_manager or PluginConfigManager(self.plugin_dir / ".config")
        self._discovered: dict[str, Path] = {}
        self._loaded: dict[str, PluginRecord] = {}
        self._lock = RLock()

    def discover_plugins(self) -> list[str]:
        """Scan plugin directories and return discovered plugin names."""
        with self._lock:
            self._discovered = self._scan_plugins()
            return sorted(self._discovered)

    def list_loaded_plugins(self) -> list[PluginMetadata]:
        """Return metadata for loaded plugins."""
        with self._lock:
            return sorted(
                (record.metadata for record in self._loaded.values()),
                key=lambda metadata: metadata.name,
            )

    def get_plugin(self, name: str) -> Plugin:
        """Return loaded plugin instance."""
        with self._lock:
            record = self._loaded.get(name)
            if not record:
                raise PluginNotLoadedError(f"Plugin '{name}' is not loaded.")
            return record.plugin

    def load_plugin(self, name: str) -> Plugin:
        """Load plugin module and call its load lifecycle hook."""
        with self._lock:
            existing = self._loaded.get(name)
            if existing:
                return existing.plugin
            plugin_path = self._resolve_plugin_path(name)
            config = self._config_manager.load_config(name)
            module_name = self._build_module_name(name)
            module = self._load_module(module_name, plugin_path)
            try:
                plugin = self._instantiate_plugin(module, config=config)
                metadata = plugin.get_metadata()
                self._validate_metadata(name, metadata)
                self._validate_dependencies(name, metadata)
                plugin.on_load()
            except PluginLoadError:
                self._safe_unload_module(module_name)
                raise
            except Exception as exc:
                self._safe_unload_module(module_name)
                raise PluginLoadError(f"Failed to load plugin '{name}'.") from exc
            record = PluginRecord(
                name=name,
                path=plugin_path,
                module_name=module_name,
                module=module,
                plugin=plugin,
                metadata=metadata,
            )
            self._loaded[name] = record
            return plugin

    def unload_plugin(self, name: str) -> None:
        """Unload a plugin and release its module."""
        with self._lock:
            record = self._loaded.get(name)
            if not record:
                raise PluginNotLoadedError(f"Plugin '{name}' is not loaded.")
            unload_error: Exception | None = None
            try:
                record.plugin.on_unload()
            except Exception as exc:  # pragma: no cover - defensive cleanup branch
                unload_error = exc
            self._safe_unload_module(record.module_name)
            self._loaded.pop(name, None)
            if unload_error is not None:
                raise PluginLoadError(f"Plugin '{name}' failed during unload.") from unload_error

    def get_record(self, name: str) -> PluginRecord:
        """Return loaded plugin record."""
        with self._lock:
            record = self._loaded.get(name)
            if not record:
                raise PluginNotLoadedError(f"Plugin '{name}' is not loaded.")
            return record

    def _scan_plugins(self) -> dict[str, Path]:
        discovered: dict[str, Path] = {}
        if not self.plugin_dir.exists():
            return discovered
        if not self.plugin_dir.is_dir():
            raise PluginDiscoveryError(f"Plugin directory is not a directory: {self.plugin_dir}")
        for entry in sorted(self.plugin_dir.iterdir()):
            if entry.name.startswith("."):
                continue
            if entry.is_dir():
                plugin_file = entry / "plugin.py"
                if plugin_file.is_file():
                    discovered[entry.name] = plugin_file
                continue
            if entry.is_file() and entry.suffix == ".py" and entry.stem != "__init__":
                discovered[entry.stem] = entry
        return discovered

    def _resolve_plugin_path(self, name: str) -> Path:
        path = self._discovered.get(name)
        if path is None:
            self._discovered = self._scan_plugins()
            path = self._discovered.get(name)
        if path is None:
            raise PluginNotFoundError(f"Plugin '{name}' was not discovered in {self.plugin_dir}.")
        return path

    def _build_module_name(self, name: str) -> str:
        normalized = name.replace("-", "_").replace(".", "_")
        return f"file_organizer.user_plugins.{normalized}_{uuid4().hex}"

    def _load_module(self, module_name: str, plugin_path: Path) -> ModuleType:
        spec = importlib.util.spec_from_file_location(module_name, plugin_path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(f"Unable to create module spec for plugin '{plugin_path}'.")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            self._safe_unload_module(module_name)
            raise PluginLoadError(f"Plugin module execution failed for '{plugin_path}'.") from exc
        return module

    def _instantiate_plugin(self, module: ModuleType, *, config: PluginConfig) -> Plugin:
        """Create a plugin instance from module exports.

        Resolution order is explicit:
        1. Use ``create_plugin(config=..., sandbox=...)`` factory when present.
        2. Otherwise instantiate the first discovered ``Plugin`` subclass.

        Only one plugin instance per module is supported; modules with multiple
        plugin classes should expose ``create_plugin`` to control selection.
        """
        sandbox = self._build_sandbox(config)
        factory = getattr(module, "create_plugin", None)
        if callable(factory):
            candidate = factory(config=config.settings, sandbox=sandbox)
            if not isinstance(candidate, Plugin):
                raise PluginLoadError("Factory 'create_plugin' did not return a Plugin instance.")
            return candidate
        plugin_classes = [
            obj
            for obj in module.__dict__.values()
            if inspect.isclass(obj) and issubclass(obj, Plugin) and obj is not Plugin
        ]
        if not plugin_classes:
            raise PluginLoadError("Plugin module does not define a Plugin implementation.")
        plugin_class = plugin_classes[0]
        return plugin_class(config=config.settings, sandbox=sandbox)

    def _build_sandbox(self, config: PluginConfig) -> PluginSandbox:
        if config.permissions:
            policy = PluginSecurityPolicy.from_permissions(
                allowed_operations=config.permissions,
                allow_all_paths=True,
            )
        else:
            policy = PluginSecurityPolicy.unrestricted()
        return PluginSandbox(plugin_name=config.name, policy=policy)

    def _validate_metadata(self, expected_name: str, metadata: PluginMetadata) -> None:
        if metadata.name != expected_name:
            raise PluginLoadError(
                f"Plugin name mismatch: expected '{expected_name}', got '{metadata.name}'."
            )

    def _validate_dependencies(self, plugin_name: str, metadata: PluginMetadata) -> None:
        if not metadata.dependencies:
            return
        unavailable: list[str] = []
        for dependency in metadata.dependencies:
            if dependency in self._loaded:
                continue
            if dependency not in self._discovered:
                unavailable.append(dependency)
        if unavailable:
            missing = ", ".join(sorted(unavailable))
            raise PluginDependencyError(
                f"Plugin '{plugin_name}' has missing dependencies: {missing}."
            )

    def _safe_unload_module(self, module_name: str) -> None:
        sys.modules.pop(module_name, None)
