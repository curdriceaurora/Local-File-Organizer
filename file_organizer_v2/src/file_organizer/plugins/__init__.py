"""Plugin system for file-organizer.

This package provides the plugin infrastructure including the base Plugin class,
sandbox isolation via PluginExecutor, and IPC utilities.
"""

from file_organizer.plugins.base import Plugin, PluginLoadError, PluginPermissionError

__all__ = ["Plugin", "PluginLoadError", "PluginPermissionError"]
