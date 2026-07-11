"""Canonical organization-methodology vocabulary.

Single source of truth for the three organization methodologies (flat/none,
PARA, Johnny Decimal) shared across ``AppConfig``, the TUI, the web UI, and
the API. Previously the web layer defined its own, partially incompatible
vocabulary (``content_based`` / ``date_based`` instead of ``none``), with no
implementation ever backing ``date_based`` — see #1538.
"""

from __future__ import annotations

NONE = "none"
PARA = "para"
JOHNNY_DECIMAL = "jd"

DEFAULT = NONE

ORDER: tuple[str, ...] = (NONE, PARA, JOHNNY_DECIMAL)

LABELS: dict[str, str] = {
    NONE: "None (flat / content-based)",
    PARA: "PARA",
    JOHNNY_DECIMAL: "Johnny Decimal",
}

# Legacy string values from before the vocabulary was unified (old
# web-settings.json files, in-memory web job metadata, hand-typed API
# requests). Mapped to their canonical equivalent by normalize(); never
# written back out. ``date_based`` is deliberately absent: it was a web-only
# dropdown option with no organizer implementation behind it anywhere in the
# codebase, so there is no canonical value to alias it to.
_ALIASES: dict[str, str] = {
    "content_based": NONE,
    "johnny_decimal": JOHNNY_DECIMAL,
}


def normalize(value: object, *, default: str = DEFAULT) -> str:
    """Return a canonical methodology value, mapping known legacy aliases.

    Args:
        value: Candidate methodology value from any surface (form field,
            API request, persisted config/settings).
        default: Value to return when *value* is unrecognized.

    Returns:
        One of :data:`ORDER`, or *default* if *value* is not a canonical
        value or a known legacy alias.
    """
    if isinstance(value, str):
        candidate = value.strip().lower()
        if candidate in ORDER:
            return candidate
        if candidate in _ALIASES:
            return _ALIASES[candidate]
    return default
