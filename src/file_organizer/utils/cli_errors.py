"""Helpers for hint-rich CLI validation errors.

Beta-criteria §2: bare error messages like "Invalid value 'cdua' for
device" make beta testers re-read the docs to discover valid values.
This helper centralizes the format so error sites can pass a `valid_values`
list once and get a "valid values: …" tail plus a "did you mean 'cuda'?"
suggestion when the input is a near-typo. Caller passes the canonical
constant (e.g. ``sorted(_VALID_DEVICES)``) so a future addition to that
constant flows into the message automatically.
"""

from __future__ import annotations

import difflib
from collections.abc import Iterable


def format_validation_error(
    *,
    field: str,
    value: object,
    valid_values: Iterable[str],
) -> str:
    """Format a validation error with valid-values list and 'did you mean'.

    The output is a single-line plain string suitable for embedding in a
    Rich-marked-up panel (e.g. ``console.print(f"[red]{...}[/red]")``).
    The caller is responsible for the styling — this helper deliberately
    emits no markup so it's also usable in plain stdout/stderr contexts
    and JSON error payloads without escape concerns.

    Args:
        field: The config / option name being validated, used in the
            "Invalid value … for {field}" prefix.
        value: The user-supplied value that failed validation. Quoted via
            ``repr`` so a stray newline / non-ASCII char is visible
            rather than silently embedded in the message.
        valid_values: The canonical set of acceptable values. The caller
            should pass the same constant the validator checks against
            so the message stays in sync with the schema (avoid inlining
            literal lists here).

    Returns:
        A multi-clause string: ``"Invalid value 'X' for device. Valid
        values: auto, cpu, cuda, mps. Did you mean 'cuda'?"``. The
        "did you mean" clause appears only when a fuzzy match exceeds the
        ``difflib`` cutoff (0.6) and ``value`` is a string.
    """
    valid = list(valid_values)
    base = f"Invalid value {value!r} for {field}. Valid values: {', '.join(valid)}."
    if isinstance(value, str):
        close = difflib.get_close_matches(value, valid, n=1, cutoff=0.6)
        if close:
            base += f" Did you mean {close[0]!r}?"
    return base
