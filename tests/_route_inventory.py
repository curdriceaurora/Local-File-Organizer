"""Compatibility helpers for enumerating public FastAPI routes."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import FastAPI


def iter_effective_routes(app: FastAPI) -> Iterator[Any]:
    """Yield leaf routes across flattened and nested FastAPI router models."""
    for route in app.routes:
        effective_route_contexts = getattr(route, "effective_route_contexts", None)
        if callable(effective_route_contexts):
            for route_context in effective_route_contexts():
                # Most HTTP contexts expose their effective path and methods directly.
                # WebSocket and raw Starlette contexts instead carry the prefixed leaf
                # route in ``starlette_route``.
                yield getattr(route_context, "starlette_route", None) or route_context
        else:
            yield route
