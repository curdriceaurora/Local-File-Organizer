"""Tagging style presets and prompt validators.

Provides validation for style names and custom prompts for auto-tagging.
"""

from __future__ import annotations

_STYLE_NAMES: frozenset[str] = frozenset({"sfx", "audio", "code", "descriptive", "hierarchical"})

MAX_TAG_PROMPT_LENGTH = 500


def validate_tag_style(name: str | None) -> None:
    """Validate that *name* is an allowed style name or None.

    Raises:
        ValueError: If *name* is not None and not in ``_STYLE_NAMES``, or if not a str.
    """
    if name is None:
        return

    if not isinstance(name, str):
        raise ValueError(f"tag_style must be a string or None, got {type(name).__name__}")

    if name not in _STYLE_NAMES:
        valid = ", ".join(sorted(_STYLE_NAMES))
        raise ValueError(f"Invalid tag_style '{name}'. Must be one of: {valid}")


def normalize_tag_prompt(prompt: str | None) -> str | None:
    """Normalize and validate a user-supplied tagging guidance prompt.

    Strips leading/trailing whitespace. An empty or whitespace-only prompt
    normalizes to ``None``.

    Raises:
        ValueError: If *prompt* is not a string/None, or exceeds 500 characters.
    """
    if prompt is None:
        return None

    if not isinstance(prompt, str):
        raise ValueError(f"tag_prompt must be a string or None, got {type(prompt).__name__}")

    cleaned = prompt.strip()
    if not cleaned:
        return None

    if len(cleaned) > MAX_TAG_PROMPT_LENGTH:
        raise ValueError(
            f"tag_prompt exceeds maximum length of {MAX_TAG_PROMPT_LENGTH} characters "
            f"(got {len(cleaned)})"
        )

    return cleaned
