"""Shared helpers for web form coercion and section updates."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar

from fastapi.responses import HTMLResponse

T = TypeVar("T")

# Canonical truthy form values for the whole web layer; other modules
# (e.g. _helpers.TRUE_VALUES) alias this set instead of redefining it.
TRUE_FORM_VALUES = frozenset({"1", "true", "yes", "on"})


def form_bool(value: str | None) -> bool:
    """Convert an HTML checkbox value to ``bool``."""
    if value is None:
        return False
    return value.strip().lower() in TRUE_FORM_VALUES


def coerce_bool(value: object, default: bool) -> bool:
    """Coerce an arbitrary value to ``bool``, falling back to *default*."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in TRUE_FORM_VALUES
    return default


def update_form_section(
    *,
    load: Callable[[], T],
    apply: Callable[[T], None],
    save: Callable[[T], None],
    render_success: Callable[[T], HTMLResponse],
    render_error: Callable[[str], HTMLResponse],
    error_prefix: str,
) -> HTMLResponse:
    """Run the common load/apply/save/render flow for a form section."""
    try:
        state = load()
        apply(state)
        save(state)
        return render_success(state)
    # User-provided form callbacks may fail; return an HTML error response instead of crashing.
    except Exception as exc:
        return render_error(f"{error_prefix}: {exc}")
