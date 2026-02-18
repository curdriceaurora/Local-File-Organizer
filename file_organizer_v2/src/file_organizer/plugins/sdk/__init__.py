"""Public SDK surface for plugin development."""

from __future__ import annotations

from file_organizer.plugins.sdk.client import PluginClient, PluginClientAuthError, PluginClientError
from file_organizer.plugins.sdk.decorators import (
    command,
    get_command_metadata,
    get_hook_metadata,
    hook,
)
from file_organizer.plugins.sdk.testing import PluginTestCase

__all__ = [
    "PluginClient",
    "PluginClientAuthError",
    "PluginClientError",
    "PluginTestCase",
    "command",
    "get_command_metadata",
    "get_hook_metadata",
    "hook",
]
