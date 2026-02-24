"""Plugin lifecycle orchestration."""

from __future__ import annotations

from enum import StrEnum
from threading import RLock

from file_organizer.plugins.base import Plugin
from file_organizer.plugins.errors import PluginLifecycleError, PluginNotLoadedError
from file_organizer.plugins.registry import PluginRegistry


class PluginState(StrEnum):
    """Plugin lifecycle states."""

    UNLOADED = "unloaded"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class PluginLifecycleManager:
    """Manage plugin lifecycle transitions consistently."""

    def __init__(self, registry: PluginRegistry) -> None:
        """Set up lifecycle management using the given plugin registry."""
        self.registry = registry
        self._states: dict[str, PluginState] = {}
        self._lock = RLock()

    def load(self, name: str) -> Plugin:
        """Load plugin into memory."""
        with self._lock:
            plugin = self.registry.load_plugin(name)
            self._states[name] = PluginState.LOADED
            plugin.set_enabled(False)
            return plugin

    def enable(self, name: str) -> None:
        """Enable a loaded plugin."""
        with self._lock:
            plugin = self._ensure_loaded(name)
            try:
                plugin.on_enable()
            except Exception as exc:
                self._states[name] = PluginState.ERROR
                raise PluginLifecycleError(f"Failed to enable plugin '{name}'.") from exc
            plugin.set_enabled(True)
            self._states[name] = PluginState.ENABLED

    def disable(self, name: str) -> None:
        """Disable an enabled plugin."""
        with self._lock:
            plugin = self._ensure_loaded(name)
            state = self._states.get(name, PluginState.LOADED)
            if state != PluginState.ENABLED:
                return
            try:
                plugin.on_disable()
            except Exception as exc:
                self._states[name] = PluginState.ERROR
                raise PluginLifecycleError(f"Failed to disable plugin '{name}'.") from exc
            plugin.set_enabled(False)
            self._states[name] = PluginState.DISABLED

    def unload(self, name: str) -> None:
        """Unload a plugin and clear runtime state."""
        with self._lock:
            state = self._states.get(name)
            if state == PluginState.ENABLED:
                self.disable(name)
            try:
                self.registry.unload_plugin(name)
            except Exception as exc:
                self._states[name] = PluginState.ERROR
                raise PluginLifecycleError(f"Failed to unload plugin '{name}'.") from exc
            self._states[name] = PluginState.UNLOADED

    def get_state(self, name: str) -> PluginState:
        """Return tracked plugin state."""
        with self._lock:
            return self._states.get(name, PluginState.UNLOADED)

    def list_states(self) -> dict[str, PluginState]:
        """Return all tracked plugin states."""
        with self._lock:
            return dict(self._states)

    def _ensure_loaded(self, name: str) -> Plugin:
        try:
            plugin = self.registry.get_plugin(name)
        except PluginNotLoadedError:
            plugin = self.registry.load_plugin(name)
        if name not in self._states:
            self._states[name] = PluginState.LOADED
        return plugin
