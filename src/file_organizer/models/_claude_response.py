"""Shared helpers for detecting Claude token-exhaustion responses.

Mirrors ``_openai_response.py`` for the Anthropic Messages API response format.

Key differences from OpenAI:
- Exhaustion signal: ``response.stop_reason == "max_tokens"`` (not ``finish_reason == "length"``)
- Content access: ``response.content[0].text`` (not ``choices[0].message.content``)
"""

from __future__ import annotations

from typing import Any

from file_organizer.models.base import MIN_USEFUL_RESPONSE_LENGTH


def is_claude_token_exhausted(
    response: Any,
    min_length: int = MIN_USEFUL_RESPONSE_LENGTH,
) -> bool:
    """Check if a Claude Messages API response exhausted its token budget.

    The condition is: ``stop_reason == "max_tokens"`` **and** the visible
    content is shorter than *min_length* characters.

    Args:
        response: Anthropic ``Message`` response object.
        min_length: Minimum character count for a useful response.

    Returns:
        ``True`` if the model exhausted its token budget without producing
        useful output.
    """
    stop_reason = getattr(response, "stop_reason", None) or ""
    if stop_reason != "max_tokens":
        return False
    content = extract_claude_text(response)
    return len(content) < min_length


def extract_claude_text(response: Any) -> str:
    """Extract and strip the text content from a Claude Messages API response.

    Args:
        response: Anthropic ``Message`` response object.

    Returns:
        The text content of the first content block, stripped of whitespace.
        Returns an empty string if there is no content.
    """
    content_blocks = getattr(response, "content", None) or []
    if not content_blocks:
        return ""
    first = content_blocks[0]
    text = getattr(first, "text", None) or ""
    return text.strip()
