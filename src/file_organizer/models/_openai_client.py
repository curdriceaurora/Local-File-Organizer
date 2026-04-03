# pyre-ignore-all-errors
"""Shared OpenAI client setup for OpenAI-compatible model implementations.

Centralises the optional-dependency guard and the client construction logic so
that ``OpenAITextModel`` and ``OpenAIVisionModel`` do not duplicate it.
"""

from __future__ import annotations

from typing import Any

try:
    from openai import OpenAI

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from loguru import logger

from file_organizer.models.base import ModelConfig


def create_openai_client(config: ModelConfig, model_type_label: str) -> Any:
    """Build and return an ``openai.OpenAI`` client from *config*.

    Args:
        config: Model configuration.  ``config.api_key`` and
            ``config.api_base_url`` are forwarded to the client constructor.
        model_type_label: Human-readable label for log messages (e.g.
            ``"text"`` or ``"vision"``).

    Returns:
        An initialised ``openai.OpenAI`` client instance.

    Raises:
        ImportError: If the ``openai`` package is not installed.
        Exception: Any exception raised by ``OpenAI.__init__`` is re-raised
            after logging only the exception *type* (not the message, which may
            contain partial ``api_key`` fragments).
    """
    if not OPENAI_AVAILABLE:
        raise ImportError(
            "The 'openai' package is not installed. "
            "Install it with: pip install 'local-file-organizer[cloud]'"
        )

    logger.info("Initializing OpenAI {} model: {}", model_type_label, config.name)
    # Only pass api_key when explicitly set — when None, the SDK falls back to
    # the OPENAI_API_KEY environment variable (standard for local endpoints).
    client_kwargs: dict[str, Any] = {}
    if config.api_key is not None:
        client_kwargs["api_key"] = config.api_key
    if config.api_base_url is not None:
        client_kwargs["base_url"] = config.api_base_url
    try:
        client = OpenAI(**client_kwargs)
        logger.info("OpenAI {} model {} initialized", model_type_label, config.name)
        return client
    except Exception as e:
        # Log only the exception type — the message may contain partial api_key fragments.
        logger.error(
            "Failed to initialize OpenAI {} model {}: {}",
            model_type_label,
            config.name,
            type(e).__name__,
        )
        raise
