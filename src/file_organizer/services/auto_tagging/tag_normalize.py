"""Canonical tag normalization and validation for auto-tagging.

Provides lossy generation-time normalization (``normalize_tag``, ``normalize_tags``)
and strict load-time validation (``validate_canonical_tags``) for schema v4 plans.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

_ALLOWED_CHARS_RE = re.compile(r"[^a-z0-9/-]+")
_MULTI_SLASH_RE = re.compile(r"/+")
_MULTI_HYPHEN_RE = re.compile(r"-+")
_MIXED_SLASH_HYPHEN_RE = re.compile(r"/-+|-+/+")

MIN_TAG_LENGTH = 2
MAX_TAG_LENGTH = 40
DEFAULT_MAX_TAGS = 8

# Upper bound on collapse/strip iterations in normalize_tag(). Each pass either
# shortens the string or leaves it unchanged, so real inputs converge in 2-3
# passes; this just guards against an unforeseen non-terminating pattern.
_MAX_COLLAPSE_PASSES = 8


def _collapse_separators_once(text: str) -> str:
    """Run one round of mixed/repeated-separator collapsing plus edge strip."""
    text = _MIXED_SLASH_HYPHEN_RE.sub("-", text)
    text = _MULTI_SLASH_RE.sub("/", text)
    text = _MULTI_HYPHEN_RE.sub("-", text)
    return text.strip("-/")


def normalize_tag(raw: str) -> str | None:
    """Normalize a single tag to canonical form, or return None if invalid.

    Normalization rules:
    - Must be ASCII-only; non-ASCII characters cause the tag to be dropped whole
      and logged at DEBUG level (no transliteration or silent mangling).
    - Lowercase.
    - Allowed characters: ``a-z0-9-/``.
    - All other separators (whitespace, underscores, punctuation) collapse to ``-``.
    - Repeated ``-`` and ``/`` collapse, and mixed ``/-`` / ``-/`` collapse to ``-``.
    - Leading and trailing ``-`` and ``/`` are stripped.
    - Length must be between 2 and 40 characters (inclusive).

    Idempotent: ``normalize_tag(normalize_tag(x))`` always equals
    ``normalize_tag(x)`` for any ``x`` where the inner call doesn't return
    ``None``. This matters because ``validate_canonical_tags()`` checks a
    stored tag against a fresh call to this function — a non-idempotent
    normalizer would reject tags this function itself just produced. The
    collapse/strip step therefore loops to a fixed point rather than running
    a single hardcoded pass: one pass can expose a new mixed-separator or
    edge pattern that only the next pass resolves (e.g. stripping a trailing
    ``-`` can reveal a ``/`` that's now itself trailing).
    """
    if not isinstance(raw, str):
        return None

    if not raw.isascii():
        logger.debug("Dropping non-ASCII tag: %r", raw)
        return None

    text = raw.lower().strip()
    if not text:
        return None

    # Replace disallowed characters with hyphens
    text = _ALLOWED_CHARS_RE.sub("-", text)

    # Collapse mixed/repeated separators and strip edges, repeating until
    # a fixed point is reached (see the idempotence note above).
    for _ in range(_MAX_COLLAPSE_PASSES):
        collapsed = _collapse_separators_once(text)
        if collapsed == text:
            break
        text = collapsed
    else:
        logger.debug(
            "normalize_tag did not converge for %r after %d passes",
            raw,
            _MAX_COLLAPSE_PASSES,
        )
        text = collapsed

    if len(text) < MIN_TAG_LENGTH or len(text) > MAX_TAG_LENGTH:
        return None

    return text


def normalize_tags(raws: Iterable[str], *, max_tags: int = DEFAULT_MAX_TAGS) -> list[str]:
    """Normalize an iterable of tags, deduplicating case-insensitively.

    First-occurrence order is preserved. Discarded entries (invalid, non-ASCII,
    out of bounds) are omitted. Output is truncated to *max_tags*.
    """
    normalized_list: list[str] = []
    seen: set[str] = set()

    for item in raws:
        tag = normalize_tag(item)
        if tag is not None and tag not in seen:
            seen.add(tag)
            normalized_list.append(tag)
            if len(normalized_list) >= max_tags:
                break

    return normalized_list


def validate_canonical_tags(raw: Any, *, max_tags: int = DEFAULT_MAX_TAGS) -> list[str]:
    """Strictly validate that a loaded tags value is in canonical form.

    Enforces that:
    - *raw* is a list of strings.
    - Total count does not exceed *max_tags*.
    - Every tag is strictly equal to its ``normalize_tag()`` output.
    - No duplicate tags exist.

    Raises:
        ValueError: If any validation rule is violated.
    """
    if not isinstance(raw, list):
        raise ValueError(f"tags must be a list, got {type(raw).__name__}")

    if len(raw) > max_tags:
        raise ValueError(f"tags count exceeds maximum of {max_tags} (got {len(raw)})")

    seen: set[str] = set()
    validated: list[str] = []

    for tag in raw:
        if not isinstance(tag, str):
            raise ValueError(f"each tag must be a string, got {type(tag).__name__}")

        canonical = normalize_tag(tag)
        if canonical is None or canonical != tag:
            raise ValueError(
                f"tag '{tag}' is not in canonical normalized form (expected '{canonical}')"
            )

        if tag in seen:
            raise ValueError(f"duplicate tag '{tag}' in tags list")

        seen.add(tag)
        validated.append(tag)

    return validated
