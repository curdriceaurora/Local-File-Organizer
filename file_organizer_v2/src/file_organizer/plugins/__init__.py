"""Plugin architecture primitives."""

from __future__ import annotations

from file_organizer.plugins.api.hooks import (
    HookEvent,
    PluginHookManager,
    WebhookDeliveryResult,
    WebhookRegistration,
)
from file_organizer.plugins.base import Plugin, PluginMetadata
from file_organizer.plugins.config import PluginConfig, PluginConfigManager
from file_organizer.plugins.errors import (
    HookExecutionError,
    PluginConfigError,
    PluginDependencyError,
    PluginDiscoveryError,
    PluginError,
    PluginLifecycleError,
    PluginLoadError,
    PluginNotFoundError,
    PluginNotLoadedError,
    PluginPermissionError,
)
from file_organizer.plugins.hooks import HookExecutionResult, HookRegistry
from file_organizer.plugins.lifecycle import PluginLifecycleManager, PluginState
from file_organizer.plugins.marketplace import (
    MarketplaceError,
    MarketplaceService,
    PluginInstaller,
    PluginPackage,
    PluginRepository,
    PluginReview,
)
from file_organizer.plugins.registry import PluginRecord, PluginRegistry
from file_organizer.plugins.sdk import (
    PluginClient,
    PluginClientAuthError,
    PluginClientError,
    PluginTestCase,
    command,
    get_command_metadata,
    get_hook_metadata,
    hook,
)
from file_organizer.plugins.security import PluginSandbox, PluginSecurityPolicy

__all__ = [
    "HookEvent",
    "HookExecutionError",
    "HookExecutionResult",
    "HookRegistry",
    "Plugin",
    "PluginConfig",
    "PluginConfigError",
    "PluginConfigManager",
    "PluginClient",
    "PluginClientAuthError",
    "PluginClientError",
    "PluginDependencyError",
    "PluginDiscoveryError",
    "PluginError",
    "PluginHookManager",
    "PluginLifecycleError",
    "PluginLifecycleManager",
    "PluginLoadError",
    "PluginInstaller",
    "PluginMetadata",
    "PluginPackage",
    "PluginNotFoundError",
    "PluginNotLoadedError",
    "PluginPermissionError",
    "PluginRecord",
    "PluginRegistry",
    "PluginRepository",
    "PluginReview",
    "PluginSandbox",
    "PluginSecurityPolicy",
    "PluginState",
    "PluginTestCase",
    "WebhookDeliveryResult",
    "WebhookRegistration",
    "MarketplaceError",
    "MarketplaceService",
    "command",
    "get_command_metadata",
    "get_hook_metadata",
    "hook",
]
