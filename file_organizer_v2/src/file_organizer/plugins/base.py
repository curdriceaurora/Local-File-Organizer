"""Base plugin interface and core exceptions for the plugin system.

All user-defined plugins must subclass :class:`Plugin` and implement
the lifecycle hooks that are appropriate for their use case.

The sandbox enforcement layer (``PluginExecutor``) uses these exceptions
to surface isolation violations back to the host process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class PluginError(Exception):
    """Base class for all plugin-related errors."""


class PluginLoadError(PluginError):
    """Raised when a plugin fails to load or initialise.

    This includes syntax errors in the plugin module, import failures,
    and any exception raised during ``on_load()``.
    """


class PluginPermissionError(PluginError):
    """Raised when a plugin attempts a disallowed operation.

    Examples of disallowed operations (enforced by the sandbox executor):

    * Calling :func:`os.system` or :func:`os.popen`.
    * Spawning a subprocess via :mod:`subprocess`.
    * Opening files outside the plugin's declared ``allowed_paths``.
    * Importing security-sensitive modules such as ``ctypes`` or ``socket``.
    """


class Plugin:
    """Base class that every plugin must subclass.

    Lifecycle hooks are called in this order:

    1. :meth:`on_load`  — called once when the plugin is loaded into the host.
    2. :meth:`on_file`  — called for each file the organiser processes.
    3. :meth:`on_unload` — called when the plugin is being removed.

    All hooks are optional (default implementations are no-ops) so that
    plugins only need to override the hooks they care about.

    Attributes:
        name: Human-readable plugin name (set by subclass or overrideable).
        version: SemVer string for the plugin.
        allowed_paths: Filesystem paths the plugin is permitted to read/write.
            The sandbox executor enforces these at runtime.
    """

    name: str = "unnamed-plugin"
    version: str = "0.0.0"
    allowed_paths: list[Path] = []

    def on_load(self) -> None:
        """Called once when the plugin is loaded.

        Raises:
            PluginLoadError: If the plugin cannot initialise.
            PluginPermissionError: If the plugin attempts a forbidden
                operation during initialisation (enforced by sandbox).
        """

    def on_file(self, file_path: Path, metadata: dict[str, Any]) -> dict[str, Any] | None:
        """Called for every file the organiser processes.

        Args:
            file_path: Absolute path to the file being processed.
            metadata: Current metadata dictionary for the file.

        Returns:
            An optional dictionary of metadata updates.  ``None`` means
            "no changes".
        """
        return None

    def on_unload(self) -> None:
        """Called when the plugin is being unloaded from the host."""
