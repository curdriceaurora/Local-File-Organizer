"""API package exports."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["app", "create_app", "get_app"]

# Module-level cache for lazy initialization with thread safety
_app_cache: Optional[FastAPI] = None
_app_lock = threading.Lock()
_create_app_cache: Optional[Callable] = None


def create_app(settings: Optional[dict] = None) -> FastAPI:
    """Lazily import and call create_app from main module.

    This wrapper breaks the circular dependency and defers app creation.
    It delegates to the real create_app in file_organizer.api.main.

    Args:
        settings: Optional configuration dictionary for the app.

    Returns:
        The initialized FastAPI application instance.
    """
    global _create_app_cache
    if _create_app_cache is None:
        from file_organizer.api.main import create_app as _real_create_app

        _create_app_cache = _real_create_app
    return _create_app_cache(settings)


def get_app() -> FastAPI:
    """Get or create the FastAPI application instance (thread-safe).

    This function implements lazy initialization with thread safety to avoid:
    - Import-time side effects (creating .config directories)
    - Multiple app instances due to race conditions
    - Test isolation issues in concurrent test environments

    The first call to this function will trigger app creation. Subsequent
    calls return the cached instance. Thread-safe via lock protection.

    Returns:
        The initialized and cached FastAPI application instance.
    """
    global _app_cache

    # Quick check without lock for performance (okay if reads stale value briefly)
    if _app_cache is not None:
        return _app_cache

    # Double-checked locking pattern for efficiency
    with _app_lock:
        # Re-check after acquiring lock (another thread may have created it)
        if _app_cache is None:
            # Import here to avoid circular dependencies at module level
            # Call main.get_app() to respect singleton pattern there
            import file_organizer.api.main
            globals()['_app_cache'] = file_organizer.api.main.get_app()

        return _app_cache


# Keep __getattr__ for backwards compatibility with attribute access
def __getattr__(name: str) -> object:
    """Fallback for attribute access patterns.

    Provided for backwards compatibility with code that uses attribute
    access instead of function calls.
    """
    if name == "app":
        return get_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
