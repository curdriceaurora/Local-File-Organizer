"""Decorators for plugin hook and command registration metadata."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from file_organizer.plugins.api.hooks import HookEvent

F = TypeVar("F", bound=Callable[..., Any])

_HOOK_EVENT_ATTR = "__fo_hook_event__"
_HOOK_PRIORITY_ATTR = "__fo_hook_priority__"
_COMMAND_NAME_ATTR = "__fo_command_name__"
_COMMAND_DESCRIPTION_ATTR = "__fo_command_description__"


def hook(event: HookEvent | str, *, priority: int = 10) -> Callable[[F], F]:
    """Mark a function as a plugin hook callback."""
    if priority < 0:
        raise ValueError("Hook priority must be >= 0")
    event_name = event.value if isinstance(event, HookEvent) else str(event).strip()
    if not event_name:
        raise ValueError("Hook event must not be empty")

    def decorator(func: F) -> F:
        setattr(func, _HOOK_EVENT_ATTR, event_name)
        setattr(func, _HOOK_PRIORITY_ATTR, priority)
        return func

    return decorator


def command(name: str, *, description: str = "") -> Callable[[F], F]:
    """Mark a function as an invokable plugin command."""
    command_name = name.strip()
    if not command_name:
        raise ValueError("Command name must not be empty")

    def decorator(func: F) -> F:
        setattr(func, _COMMAND_NAME_ATTR, command_name)
        setattr(func, _COMMAND_DESCRIPTION_ATTR, description.strip())
        return func

    return decorator


def get_hook_metadata(func: Callable[..., Any]) -> tuple[str, int] | None:
    """Return (event, priority) when function is a hook callback."""
    event = getattr(func, _HOOK_EVENT_ATTR, None)
    priority = getattr(func, _HOOK_PRIORITY_ATTR, None)
    if isinstance(event, str) and isinstance(priority, int):
        return event, priority
    return None


def get_command_metadata(func: Callable[..., Any]) -> tuple[str, str] | None:
    """Return (name, description) when function is a command callback."""
    name = getattr(func, _COMMAND_NAME_ATTR, None)
    description = getattr(func, _COMMAND_DESCRIPTION_ATTR, None)
    if isinstance(name, str) and isinstance(description, str):
        return name, description
    return None
