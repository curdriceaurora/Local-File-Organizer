"""Plugin lifecycle orchestration.

All lifecycle calls (``on_load``, ``on_enable``, ``on_disable``, ``on_unload``)
are routed through the plugin's :class:`~file_organizer.plugins.executor.PluginExecutor`
subprocess — no plugin code runs in the host process.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from threading import RLock

from file_organizer.plugins.errors import PluginLifecycleError, PluginNotLoadedError
from file_organizer.plugins.registry import PluginRecord, PluginRegistry
from file_organizer.plugins.security import PluginSecurityPolicy


class PluginState(StrEnum):
    """Plugin lifecycle states."""

    UNLOADED = "unloaded"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


class PluginLifecycleManager:
    """Manage plugin lifecycle transitions consistently.

    Every lifecycle method delegates to the
    :class:`~file_organizer.plugins.registry.PluginRegistry` and ultimately
    to the plugin's subprocess executor so that **no plugin code runs in the
    host process**.
    """

    def __init__(self, registry: PluginRegistry) -> None:
        """Set up lifecycle management using the given plugin registry."""
        self.registry = registry
        self._states: dict[str, PluginState] = {}
        self._lock = RLock()

    def load(
        self,
        plugin_dir: Path,
        *,
        policy: PluginSecurityPolicy | None = None,
    ) -> PluginRecord:
        """Load a plugin from *plugin_dir* into the registry.

        Args:
            plugin_dir: Directory containing ``plugin.json``.
            policy: Optional explicit security policy.

        Returns:
            The :class:`PluginRecord` for the newly loaded plugin.
        """
        with self._lock:
            record = self.registry.load_plugin(plugin_dir, policy=policy)
            self._states[record.name] = PluginState.LOADED
            return record

    def enable(self, name: str) -> None:
        """Enable a loaded plugin via its subprocess executor.

        No-op if the plugin is already ENABLED (mirrors ``disable()``'s guard).
        """
        with self._lock:
            record = self._ensure_loaded(name)
            if self._states.get(name) == PluginState.ENABLED:
                return
            try:
                record.executor.call("on_enable")
            except Exception as exc:
                self._states[name] = PluginState.ERROR
                raise PluginLifecycleError(f"Failed to enable plugin '{name}'.") from exc
            self._states[name] = PluginState.ENABLED

    def disable(self, name: str) -> None:
        """Disable an enabled plugin via its subprocess executor."""
        with self._lock:
            record = self._ensure_loaded(name)
            state = self._states.get(name, PluginState.LOADED)
            if state != PluginState.ENABLED:
                return
            try:
                record.executor.call("on_disable")
            except Exception as exc:
                self._states[name] = PluginState.ERROR
                raise PluginLifecycleError(f"Failed to disable plugin '{name}'.") from exc
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
                # unload_plugin pops the record before calling on_unload, so on
                # failure the plugin is already removed from the registry.
                # Clean up the state entry to avoid a stale ERROR leak.
                self._states.pop(name, None)
                raise PluginLifecycleError(f"Failed to unload plugin '{name}'.") from exc
            # Plugin fully unloaded — remove state entry (no orphaned UNLOADED).
            self._states.pop(name, None)

    def get_state(self, name: str) -> PluginState:
        """Return tracked plugin state."""
        with self._lock:
            return self._states.get(name, PluginState.UNLOADED)

    def list_states(self) -> dict[str, PluginState]:
        """Return all tracked plugin states."""
        with self._lock:
            return dict(self._states)

    def _ensure_loaded(self, name: str) -> PluginRecord:
        """Return the :class:`PluginRecord` for *name*, or raise."""
        try:
            return self.registry.get_plugin(name)
        except PluginNotLoadedError:
            raise PluginNotLoadedError(
                f"Plugin '{name}' is not loaded. Call load() with the plugin directory first."
            ) from None
