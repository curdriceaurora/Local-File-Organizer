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

    # Collapse mixed and repeated separators
    text = _MIXED_SLASH_HYPHEN_RE.sub("-", text)
    text = _MULTI_SLASH_RE.sub("/", text)
    text = _MULTI_HYPHEN_RE.sub("-", text)

    # Strip leading/trailing delimiters
    text = text.strip("-/")

    # Clean any artifacts resulting from stripping
    text = _MIXED_SLASH_HYPHEN_RE.sub("-", text)
    text = _MULTI_HYPHEN_RE.sub("-", text)
    text = _MULTI_SLASH_RE.sub("/", text)

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
