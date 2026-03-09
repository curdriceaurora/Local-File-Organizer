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
            "Install it with: pip install 'file-organizer[cloud]'"
        )

    logger.info("Initializing OpenAI %s model: %s", model_type_label, config.name)
    try:
        client = OpenAI(
            api_key=config.api_key,
            base_url=config.api_base_url,
        )
        logger.info("OpenAI %s model %s initialized", model_type_label, config.name)
        return client
    except Exception as e:
        # Log only the exception type — the message may contain partial api_key fragments.
        logger.error(
            "Failed to initialize OpenAI %s model %s: %s",
            model_type_label,
            config.name,
            type(e).__name__,
        )
        raise
