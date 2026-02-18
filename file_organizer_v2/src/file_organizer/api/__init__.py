"""API package exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["app", "create_app"]


def __getattr__(name: str) -> object:
    """Lazily import ``app`` and ``create_app`` to avoid circular imports.

    ``file_organizer.plugins.api.endpoints`` imports from
    ``file_organizer.api.config``, which would trigger this package's
    ``__init__`` and then eagerly import ``api.main``, which in turn
    imports ``plugins.api.endpoints.router`` — creating a circular
    dependency.  Deferring these imports until they are actually
    accessed breaks the cycle.
    """
    if name in {"app", "create_app"}:
        from file_organizer.api.main import app, create_app  # noqa: PLC0415

        globals()["app"] = app
        globals()["create_app"] = create_app
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
