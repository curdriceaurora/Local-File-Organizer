"""Plugin registry with subprocess-isolated lifecycle management.

Each plugin is loaded in two phases:

1. **In-process metadata extraction** — the plugin module is imported inside
   the host process *once*, solely to read :attr:`Plugin.name`,
   :attr:`Plugin.version`, and :attr:`Plugin.allowed_paths`.  This phase also
   validates inter-plugin dependencies before committing resources.

2. **Subprocess isolation** — a :class:`~file_organizer.plugins.executor.PluginExecutor`
   is created and started.  All subsequent lifecycle calls (``on_load``,
   ``on_file``, ``on_unload``) are routed through the executor's JSON-IPC
   channel so that plugin code never runs inside the host process after
   initial metadata extraction.

Example::

    from pathlib import Path
    from file_organizer.plugins.registry import PluginRegistry
    from file_organizer.plugins.security import PluginSecurityPolicy

    registry = PluginRegistry()
    registry.load_plugin(
        Path("my_plugin.py"),
        policy=PluginSecurityPolicy.unrestricted(),
    )
    registry.unload_plugin("my-plugin")
"""

from __future__ import annotations

import importlib.util
import logging
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from file_organizer.plugins.base import Plugin, PluginError, PluginLoadError
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
        name: The plugin's canonical name (from :attr:`Plugin.name`).
        version: The plugin's version string (from :attr:`Plugin.version`).
        plugin_path: Filesystem path to the plugin ``.py`` source file.
        policy: The security policy applied to this plugin's subprocess.
        plugin: In-process plugin instance retained for metadata access and
            dependency validation.  Lifecycle hooks are *not* called on this
            instance after initial loading; all calls go through ``executor``.
        executor: The :class:`~file_organizer.plugins.executor.PluginExecutor`
            that owns the plugin's sandboxed child process.
    """

    name: str
    version: str
    plugin_path: Path
    policy: PluginSecurityPolicy
    plugin: Plugin
    executor: PluginExecutor


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class PluginRegistry:
    """Central registry for loading, tracking, and unloading plugins.

    Plugins are registered by filesystem path.  The registry ensures each
    plugin name is unique — attempting to load two plugins with the same
    :attr:`Plugin.name` raises :class:`~file_organizer.plugins.base.PluginLoadError`.

    All lifecycle calls after initial loading are routed through each plugin's
    :class:`~file_organizer.plugins.executor.PluginExecutor` so that plugin
    code is isolated in a sandboxed child process.

    Attributes:
        _records: Mapping from plugin name to :class:`PluginRecord`.
    """

    def __init__(self) -> None:
        self._records: dict[str, PluginRecord] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_plugin(
        self,
        plugin_path: Path,
        *,
        policy: PluginSecurityPolicy | None = None,
    ) -> PluginRecord:
        """Load a plugin from *plugin_path* into the registry.

        The loading process is as follows:

        1. Import the plugin module in-process to extract metadata and
           validate dependencies (see :meth:`_load_module` and
           :meth:`_instantiate_plugin`).
        2. Check that no plugin with the same name is already registered.
        3. Build the sandbox policy if one was not provided.
        4. Create a :class:`~file_organizer.plugins.executor.PluginExecutor`,
           start it, and invoke ``on_load`` through the IPC channel.
        5. Store a :class:`PluginRecord` in the registry and return it.

        Args:
            plugin_path: Path to the plugin ``.py`` file.
            policy: Security policy for the plugin's subprocess.  Defaults to
                :meth:`~file_organizer.plugins.security.PluginSecurityPolicy.unrestricted`
                when *None*.

        Returns:
            The newly created :class:`PluginRecord`.

        Raises:
            PluginLoadError: If the module cannot be imported, contains no
                :class:`~file_organizer.plugins.base.Plugin` subclass, a
                plugin with the same name is already loaded, or the
                subprocess ``on_load`` call raises an error.
        """
        # Phase 1: In-process import for metadata extraction + dependency check
        module = self._load_module(plugin_path)
        plugin_instance = self._instantiate_plugin(module, plugin_path)

        plugin_name = plugin_instance.name
        plugin_version = plugin_instance.version

        # Guard against duplicate registrations
        if plugin_name in self._records:
            raise PluginLoadError(
                f"Plugin '{plugin_name}' is already loaded. "
                "Unload the existing plugin before loading a new version."
            )

        # Phase 2: Build sandbox policy and spawn isolated subprocess
        effective_policy = policy if policy is not None else self._build_sandbox(plugin_instance)

        executor = PluginExecutor(
            plugin_path=plugin_path,
            plugin_name=plugin_name,
            policy=effective_policy,
        )
        executor.start()

        try:
            executor.call("on_load")
        except PluginError:
            # Ensure the child process is cleaned up if on_load fails
            executor.stop()
            raise

        record = PluginRecord(
            name=plugin_name,
            version=plugin_version,
            plugin_path=plugin_path,
            policy=effective_policy,
            plugin=plugin_instance,
            executor=executor,
        )
        self._records[plugin_name] = record
        logger.info("Loaded plugin '%s' v%s from %s", plugin_name, plugin_version, plugin_path)
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
        """Enable a registered plugin (no-op stub; plugins are active on load).

        This method is provided for API symmetry with :meth:`disable_plugin`.
        All routing of lifecycle calls is handled by the executor; there is no
        separate "enabled" flag maintained by the registry.

        Args:
            plugin_name: The canonical name of the plugin to enable.

        Raises:
            PluginNotLoadedError: If no plugin with *plugin_name* is registered.
        """
        if plugin_name not in self._records:
            raise PluginNotLoadedError(f"Plugin '{plugin_name}' is not loaded.")
        logger.debug("Plugin '%s' is already active (enabled on load).", plugin_name)

    def disable_plugin(self, plugin_name: str) -> None:
        """Disable a registered plugin by unloading it from the registry.

        Because subprocess isolation means the plugin runs in its own process,
        "disabling" is equivalent to calling :meth:`unload_plugin`.  The
        plugin can be re-enabled by calling :meth:`load_plugin` again.

        Args:
            plugin_name: The canonical name of the plugin to disable.

        Raises:
            PluginNotLoadedError: If no plugin with *plugin_name* is registered.
            PluginError: If ``on_unload`` raises during teardown.
        """
        self.unload_plugin(plugin_name)

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
            except PluginError as exc:
                logger.warning("Plugin '%s' raised an error in '%s': %s", name, method, exc)
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
            except Exception as exc:  # noqa: BLE001
                logger.warning("Error while unloading plugin '%s': %s", plugin_name, exc)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_module(self, plugin_path: Path) -> types.ModuleType:
        """Import a plugin module from *plugin_path* in-process.

        This method is used exclusively for metadata extraction before the
        subprocess executor is started.  It does *not* invoke any plugin
        lifecycle hooks.

        Args:
            plugin_path: Filesystem path to the plugin ``.py`` source file.

        Returns:
            The imported :class:`types.ModuleType`.

        Raises:
            PluginLoadError: If the path does not exist or the module cannot
                be imported.
        """
        if not plugin_path.exists():
            raise PluginLoadError(f"Plugin file not found: {plugin_path}")

        spec = importlib.util.spec_from_file_location(plugin_path.stem, plugin_path)
        if spec is None or spec.loader is None:
            raise PluginLoadError(
                f"Cannot create an import spec for plugin: {plugin_path}"
            )

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            raise PluginLoadError(
                f"Error importing plugin module '{plugin_path}': {exc}"
            ) from exc

        return module

    def _instantiate_plugin(
        self, module: types.ModuleType, plugin_path: Path
    ) -> Plugin:
        """Find and instantiate the first :class:`Plugin` subclass in *module*.

        This is used in-process solely to read :attr:`Plugin.name`,
        :attr:`Plugin.version`, and :attr:`Plugin.allowed_paths` for metadata
        extraction and dependency validation.  No lifecycle hooks are called
        on the returned instance.

        Args:
            module: A module object produced by :meth:`_load_module`.
            plugin_path: Path used in error messages.

        Returns:
            An instantiated :class:`Plugin` subclass.

        Raises:
            PluginLoadError: If no :class:`Plugin` subclass is found or
                instantiation raises an exception.
        """
        for attr_name in dir(module):
            obj = getattr(module, attr_name)
            if (
                isinstance(obj, type)
                and issubclass(obj, Plugin)
                and obj is not Plugin
            ):
                try:
                    return obj()
                except Exception as exc:
                    raise PluginLoadError(
                        f"Error instantiating plugin class '{attr_name}' "
                        f"from '{plugin_path}': {exc}"
                    ) from exc

        raise PluginLoadError(
            f"No Plugin subclass found in: {plugin_path}"
        )

    def _build_sandbox(self, plugin: Plugin) -> PluginSecurityPolicy:
        """Construct a :class:`PluginSecurityPolicy` from a plugin's declarations.

        Uses the plugin's :attr:`~Plugin.allowed_paths` class attribute to
        build a policy that restricts filesystem access to the declared paths.

        Args:
            plugin: In-process plugin instance used to read ``allowed_paths``.

        Returns:
            A :class:`PluginSecurityPolicy` scoped to the plugin's declared
            allowed paths, with no operation restrictions.
        """
        return PluginSecurityPolicy.from_permissions(
            allowed_paths=list(plugin.allowed_paths),
            allow_all_operations=True,
        )
