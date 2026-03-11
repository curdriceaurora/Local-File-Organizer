"""Shared helpers for detecting OpenAI token-exhaustion responses.

Mirrors ``_ollama_response.py`` for the OpenAI-compatible API response format.
"""

from __future__ import annotations

from typing import Any

from file_organizer.models.base import MIN_USEFUL_RESPONSE_LENGTH


def is_openai_token_exhausted(
    response: Any,
    min_length: int = MIN_USEFUL_RESPONSE_LENGTH,
) -> bool:
    """Check if an OpenAI chat completion exhausted its token budget.

    The condition is: ``finish_reason == "length"`` **and** the visible
    content is shorter than *min_length* characters.

    Args:
        response: OpenAI ChatCompletion response object.
        min_length: Minimum character count for a useful response.

    Returns:
        ``True`` if the model exhausted its token budget without producing
        useful output.
    """
    if not response.choices:
        return False
    choice = response.choices[0]
    finish_reason = getattr(choice, "finish_reason", None) or ""
    content = (getattr(choice.message, "content", None) or "").strip()
    return finish_reason == "length" and len(content) < min_length
