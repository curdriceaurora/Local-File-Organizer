"""Shared helpers for detecting llama.cpp token-exhaustion responses.

llama.cpp returns a plain dict response with ``choices[0]["finish_reason"]``
and ``choices[0]["text"]`` — distinct from the OpenAI object-based format.
"""

from __future__ import annotations

from typing import Any

from file_organizer.models.base import MIN_USEFUL_RESPONSE_LENGTH


def is_llama_cpp_token_exhausted(
    response: dict[str, Any],
    min_length: int = MIN_USEFUL_RESPONSE_LENGTH,
) -> bool:
    """Check if a llama.cpp completion exhausted its token budget.

    The condition is: ``finish_reason == "length"`` **and** the visible
    text is shorter than *min_length* characters.

    Args:
        response: llama.cpp completion response dict.
        min_length: Minimum character count for a useful response.

    Returns:
        ``True`` if the model exhausted its token budget without producing
        useful output.
    """
    choices = response.get("choices")
    if not choices:
        return False
    choice = choices[0]
    finish_reason = choice.get("finish_reason") or ""
    text = (choice.get("text") or "").strip()
    return finish_reason == "length" and len(text) < min_length


def extract_llama_cpp_text(response: dict[str, Any]) -> str:
    """Extract and strip the generated text from a llama.cpp response dict.

    Args:
        response: llama.cpp completion response dict.

    Returns:
        The generated text, stripped of leading/trailing whitespace, or
        an empty string if the response contains no choices.
    """
    choices = response.get("choices")
    if not choices:
        return ""
    return (choices[0].get("text") or "").strip()
