"""Plugin registry with subprocess-isolated lifecycle management.

Plugin metadata is read from a static ``plugin.json`` manifest file — **no
plugin code is ever executed inside the host process**.  The manifest provides
the plugin's identity (name, version, author, …) and declares filesystem
permissions via ``allowed_paths``.

After reading the manifest the registry spawns a
:class:`~file_organizer.plugins.executor.PluginExecutor` subprocess which
imports and runs the plugin module in an isolated child process.

Example::

    from pathlib import Path
    from file_organizer.plugins.registry import PluginRegistry
    from file_organizer.plugins.security import PluginSecurityPolicy

    registry = PluginRegistry()
    registry.load_plugin(
        Path("plugins/my-plugin"),
        policy=PluginSecurityPolicy.unrestricted(),
    )
    registry.unload_plugin("my-plugin")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from file_organizer.plugins.base import PluginLoadError, load_manifest
from file_organizer.plugins.errors import PluginNotLoadedError
from file_organizer.plugins.executor import PluginExecutor
from file_organizer.plugins.security import PluginSecurityPolicy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PluginRecord:
    """Metadata and runtime handles for a single loaded plugin.

    Attributes:
        name: The plugin's canonical name (from ``plugin.json``).
        version: The plugin's version string (from ``plugin.json``).
        plugin_dir: Directory containing the plugin's ``plugin.json`` and
            entry-point source file.
        policy: The security policy applied to this plugin's subprocess.
        manifest: The parsed ``plugin.json`` dictionary.
        executor: The :class:`~file_organizer.plugins.executor.PluginExecutor`
            that owns the plugin's sandboxed child process.
    """

    name: str
    version: str
    plugin_dir: Path
    policy: PluginSecurityPolicy
    manifest: dict[str, Any]
    executor: PluginExecutor


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """Central registry for loading, tracking, and unloading plugins.

    Plugins are registered by directory path (which must contain a
    ``plugin.json`` manifest).  The registry ensures each plugin name is
    unique — attempting to load two plugins with the same name raises
    :class:`~file_organizer.plugins.base.PluginLoadError`.

    All lifecycle calls are routed through each plugin's
    :class:`~file_organizer.plugins.executor.PluginExecutor` so that plugin
    code is isolated in a sandboxed child process.

    **Thread safety:** This class is *not* internally synchronized.
    :class:`~file_organizer.plugins.lifecycle.PluginLifecycleManager` wraps
    all public methods with an ``RLock``; callers that bypass the lifecycle
    manager must provide their own external synchronization.

    Attributes:
        _records: Mapping from plugin name to :class:`PluginRecord`.
    """

    def __init__(self) -> None:
        """Create an empty plugin registry."""
        self._records: dict[str, PluginRecord] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_plugin(
        self,
        plugin_dir: Path,
        *,
        policy: PluginSecurityPolicy | None = None,
    ) -> PluginRecord:
        """Load a plugin from *plugin_dir* into the registry.

        The loading process is as follows:

        1. Read and validate ``plugin.json`` from *plugin_dir* — **no code
           is executed** in the host process.
        2. Check that no plugin with the same name is already registered.
        3. Build the sandbox policy from the manifest if one was not
           explicitly provided.
        4. Resolve the entry-point path and create a
           :class:`~file_organizer.plugins.executor.PluginExecutor`, start
           it, and invoke ``on_load`` through the IPC channel.
        5. Store a :class:`PluginRecord` in the registry and return it.

        Args:
            plugin_dir: Path to the plugin directory containing
                ``plugin.json``.
            policy: Security policy for the plugin's subprocess.  Defaults to
                a policy derived from the manifest's ``allowed_paths``.

        Returns:
            The newly created :class:`PluginRecord`.

        Raises:
            PluginLoadError: If the manifest is missing/invalid, the
                entry-point source file does not exist, a plugin with the
                same name is already loaded, or the subprocess ``on_load``
                call raises an error.
        """
        plugin_dir = Path(plugin_dir)

        # Phase 1: Static manifest read — zero code execution
        manifest = load_manifest(plugin_dir)

        plugin_name: str = manifest["name"]
        plugin_version: str = manifest["version"]

        # Guard against duplicate registrations
        if plugin_name in self._records:
            raise PluginLoadError(
                f"Plugin '{plugin_name}' is already loaded. "
                "Unload the existing plugin before loading a new version."
            )

        # Resolve entry-point (reject path traversal outside plugin_dir)
        resolved_plugin_dir = plugin_dir.resolve()
        entry_point = (plugin_dir / manifest["entry_point"]).resolve()
        if not entry_point.is_relative_to(resolved_plugin_dir):
            raise PluginLoadError(
                f"Entry-point '{manifest['entry_point']}' escapes plugin directory."
            )
        if not entry_point.exists():
            raise PluginLoadError(
                f"Entry-point '{manifest['entry_point']}' not found in {plugin_dir}."
            )

        # Phase 2: Build sandbox policy and spawn isolated subprocess
        effective_policy = (
            policy if policy is not None else self._build_sandbox_from_manifest(manifest)
        )

        executor = PluginExecutor(
            plugin_path=entry_point,
            plugin_name=plugin_name,
            policy=effective_policy,
        )
        try:
            executor.start()
            executor.call("on_load")
        except Exception:
            # Any failure after start() must stop the child process to avoid
            # subprocess leaks (covers PluginError, IPC errors, timeouts, etc.).
            # Guard stop() so a cleanup failure doesn't mask the original error.
            try:
                executor.stop()
            except Exception:
                logger.debug("Cleanup of '%s' executor failed", plugin_name, exc_info=True)
            raise

        record = PluginRecord(
            name=plugin_name,
            version=plugin_version,
            plugin_dir=plugin_dir,
            policy=effective_policy,
            manifest=manifest,
            executor=executor,
        )
        self._records[plugin_name] = record
        logger.info("Loaded plugin '%s' v%s from %s", plugin_name, plugin_version, plugin_dir)
        return record

    def unload_plugin(self, plugin_name: str) -> None:
        """Unload a previously loaded plugin by name.

        Calls ``on_unload`` on the plugin through its executor, then
        terminates the child process and removes the record from the registry.

        Args:
            plugin_name: The canonical name of the plugin to unload.

        Raises:
            PluginNotLoadedError: If no plugin with *plugin_name* is registered.
            PluginError: If ``on_unload`` raises an error in the child process.
        """
        if plugin_name not in self._records:
            raise PluginNotLoadedError(f"Plugin '{plugin_name}' is not loaded.")

        record = self._records.pop(plugin_name)
        try:
            record.executor.call("on_unload")
        finally:
            # Always stop the executor, even if on_unload raised
            record.executor.stop()
        logger.info("Unloaded plugin '%s'", plugin_name)

    def enable_plugin(self, plugin_name: str) -> None:
        """Enable a registered plugin via its executor.

        Calls ``on_enable`` in the plugin's subprocess through the executor.

        Args:
            plugin_name: The canonical name of the plugin to enable.

        Raises:
            PluginNotLoadedError: If no plugin with *plugin_name* is registered.
            PluginError: If ``on_enable`` raises in the child process.
        """
        record = self.get_plugin(plugin_name)
        record.executor.call("on_enable")
        logger.debug("Plugin '%s' enabled.", plugin_name)

    def disable_plugin(self, plugin_name: str) -> None:
        """Disable a registered plugin via its executor.

        Calls ``on_disable`` in the plugin's subprocess through the executor.

        Args:
            plugin_name: The canonical name of the plugin to disable.

        Raises:
            PluginNotLoadedError: If no plugin with *plugin_name* is registered.
            PluginError: If ``on_disable`` raises in the child process.
        """
        record = self.get_plugin(plugin_name)
        record.executor.call("on_disable")
        logger.debug("Plugin '%s' disabled.", plugin_name)

    def get_plugin(self, plugin_name: str) -> PluginRecord:
        """Return the :class:`PluginRecord` for a registered plugin.

        Args:
            plugin_name: The canonical name of the plugin to retrieve.

        Returns:
            The corresponding :class:`PluginRecord`.

        Raises:
            PluginNotLoadedError: If no plugin with *plugin_name* is registered.
        """
        if plugin_name not in self._records:
            raise PluginNotLoadedError(f"Plugin '{plugin_name}' is not loaded.")
        return self._records[plugin_name]

    def list_plugins(self) -> list[str]:
        """Return a sorted list of currently loaded plugin names.

        Returns:
            Sorted list of plugin name strings.
        """
        return sorted(self._records)

    def call_all(self, method: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Invoke *method* on every loaded plugin via its executor.

        Results are collected into a dictionary keyed by plugin name.  If a
        plugin raises an error, the exception is caught and stored as the value
        so that one faulty plugin does not prevent others from being called.

        Args:
            method: Name of the plugin method to invoke on each plugin.
            *args: Positional arguments forwarded to each plugin method.
            **kwargs: Keyword arguments forwarded to each plugin method.

        Returns:
            A dict mapping plugin name → return value (or :class:`PluginError`
            instance on failure).
        """
        results: dict[str, Any] = {}
        for name, record in self._records.items():
            try:
                results[name] = record.executor.call(method, *args, **kwargs)
            except Exception as exc:
                logger.warning(
                    "Plugin '%s' raised an error in '%s': %s",
                    name,
                    method,
                    exc,
                    exc_info=True,
                )
                results[name] = exc
        return results

    def unload_all(self) -> None:
        """Unload every registered plugin, ignoring individual unload errors.

        This is intended for cleanup during application shutdown.  Errors from
        individual plugins are logged at WARNING level but do not interrupt the
        teardown of other plugins.
        """
        for plugin_name in list(self._records):
            try:
                self.unload_plugin(plugin_name)
            except Exception as exc:
                logger.warning(
                    "Error while unloading plugin '%s': %s",
                    plugin_name,
                    exc,
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_sandbox_from_manifest(
        manifest: dict[str, Any],
    ) -> PluginSecurityPolicy:
        """Construct a :class:`PluginSecurityPolicy` from a manifest dict.

        Uses the manifest's ``allowed_paths`` and ``allowed_operations`` lists
        to build a policy that restricts both filesystem and operation access.

        Operation-level restrictions:
        - Common operations: "read", "write", "delete", "execute", "network"
        - Dangerous operations: blocked by default unless explicitly allowed
        - Custom operations: supported via manifest configuration

        Args:
            manifest: Validated manifest dictionary.

        Returns:
            A :class:`PluginSecurityPolicy` scoped to the manifest's declared
            allowed paths and operations.
        """
        # Extract operation restrictions from manifest
        allowed_operations = list(manifest.get("allowed_operations", []))
        allow_all_ops = manifest.get("allow_all_operations", False)

        # If no operations specified, use safe defaults (read-only)
        if not allowed_operations and not allow_all_ops:
            allowed_operations = ["read"]

        return PluginSecurityPolicy.from_permissions(
            allowed_paths=list(manifest.get("allowed_paths", [])),
            allowed_operations=allowed_operations,
            allow_all_operations=allow_all_ops,
        )
