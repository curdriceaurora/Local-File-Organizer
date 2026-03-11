"""Shared helpers for detecting and handling Ollama token-exhaustion responses.

These pure functions are used by ``TextModel`` and ``VisionModel`` to detect
when an Ollama response indicates that the ``num_predict`` budget was consumed
without producing useful output, and to compute retry parameters.
"""

from __future__ import annotations

from typing import Any

from file_organizer.models.base import (
    MAX_NUM_PREDICT,
    MIN_USEFUL_RESPONSE_LENGTH,
    RETRY_MULTIPLIER,
)


def is_token_exhausted(
    response: Any,
    min_length: int = MIN_USEFUL_RESPONSE_LENGTH,
) -> bool:
    """Return ``True`` when *response* indicates token-budget exhaustion.

    The condition is: ``done_reason == "length"`` **and** the visible
    ``response`` text is shorter than *min_length* characters.

    Args:
        response: Raw Ollama response dict.
        min_length: Minimum character count for a useful response.

    Returns:
        ``True`` if the model exhausted its token budget without producing
        useful output.
    """
    done_reason = response.get("done_reason", "")
    text = response.get("response", "") or ""
    return done_reason == "length" and len(text.strip()) < min_length


def compute_retry_num_predict(
    current: int,
    cap: int = MAX_NUM_PREDICT,
) -> int:
    """Return the ``num_predict`` value for a single retry attempt.

    Doubles the current budget, clamped to *cap*.

    Args:
        current: Current ``num_predict`` value.
        cap: Maximum allowed value.

    Returns:
        New ``num_predict`` value.
    """
    return min(current * RETRY_MULTIPLIER, cap)


def format_exhaustion_diagnostics(
    response: Any,
    model_name: str,
) -> str:
    """Format a human-readable diagnostic string for token exhaustion.

    Includes the key fields that help users understand *why* the response
    was empty and what to adjust.

    Args:
        response: Raw Ollama response dict.
        model_name: Name of the model that produced the response.

    Returns:
        Multi-line diagnostic string.
    """
    done_reason = response.get("done_reason", "unknown")
    eval_count = response.get("eval_count", "N/A")
    prompt_eval_count = response.get("prompt_eval_count", "N/A")
    total_duration_ns = response.get("total_duration", 0)
    total_duration_s = total_duration_ns / 1e9 if total_duration_ns else 0.0
    response_text = (response.get("response", "") or "").strip()
    response_len = len(response_text)

    return (
        f"Token exhaustion for model '{model_name}': "
        f"done_reason={done_reason}, "
        f"response_length={response_len} chars, "
        f"eval_count={eval_count}, "
        f"prompt_eval_count={prompt_eval_count}, "
        f"duration={total_duration_s:.2f}s"
    )
