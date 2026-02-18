"""Plugin subsystem exceptions."""

from __future__ import annotations


class PluginError(Exception):
    """Base class for plugin subsystem failures."""


class PluginDiscoveryError(PluginError):
    """Raised when plugin discovery fails."""


class PluginLoadError(PluginError):
    """Raised when a plugin cannot be loaded."""


class PluginDependencyError(PluginLoadError):
    """Raised when plugin dependencies are unavailable."""


class PluginNotFoundError(PluginLoadError):
    """Raised when a requested plugin cannot be found."""


class PluginNotLoadedError(PluginError):
    """Raised when operations require a loaded plugin."""


class PluginConfigError(PluginError):
    """Raised when plugin configuration is invalid or unreadable."""


class PluginPermissionError(PluginError):
    """Raised when a plugin violates its sandbox policy."""


class PluginLifecycleError(PluginError):
    """Raised when lifecycle transitions fail."""


class HookExecutionError(PluginError):
    """Raised when a hook callback fails in fail-fast mode."""
