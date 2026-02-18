"""Plugin API package."""

from __future__ import annotations

from file_organizer.plugins.api.endpoints import get_hook_manager, router
from file_organizer.plugins.api.hooks import (
    HookEvent,
    PluginHookManager,
    WebhookDeliveryResult,
    WebhookRegistration,
)

__all__ = [
    "HookEvent",
    "PluginHookManager",
    "WebhookDeliveryResult",
    "WebhookRegistration",
    "get_hook_manager",
    "router",
]
