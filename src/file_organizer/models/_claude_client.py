# pyre-ignore-all-errors
"""Shared Anthropic client setup for Claude model implementations.

Centralises the optional-dependency guard and client construction logic so that
``ClaudeTextModel`` and ``ClaudeVisionModel`` do not duplicate it.
"""

from __future__ import annotations

from typing import Any

try:
    from anthropic import Anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

from loguru import logger

from file_organizer.models.base import ModelConfig


def create_claude_client(config: ModelConfig, model_type_label: str) -> Any:
    """Build and return an ``anthropic.Anthropic`` client from *config*.

    The Anthropic SDK does not support a ``base_url`` override like the OpenAI
    SDK does.  If ``config.api_base_url`` is set a warning is logged and it is
    silently ignored — all requests go to ``https://api.anthropic.com``.

    Args:
        config: Model configuration.  ``config.api_key`` is forwarded to the
            client constructor when set; otherwise the SDK reads
            ``ANTHROPIC_API_KEY`` from the environment automatically.
        model_type_label: Human-readable label for log messages (e.g.
            ``"text"`` or ``"vision"``).

    Returns:
        An initialised ``anthropic.Anthropic`` client instance.

    Raises:
        ImportError: If the ``anthropic`` package is not installed.
        Exception: Any exception raised by ``Anthropic.__init__`` is re-raised
            after logging only the exception *type* (not the message, which may
            contain partial ``api_key`` fragments).
    """
    if not ANTHROPIC_AVAILABLE:
        raise ImportError(
            "The 'anthropic' package is not installed. "
            "Install it with: pip install 'local-file-organizer[claude]'"
        )

    if config.api_base_url is not None:
        logger.warning(
            "Claude provider does not support a custom base_url (api_base_url={!r}); "
            "ignoring — all requests go to api.anthropic.com.",
            config.api_base_url,
        )

    logger.info("Initializing Claude {} model: {}", model_type_label, config.name)
    client_kwargs: dict[str, Any] = {}
    if config.api_key is not None:
        client_kwargs["api_key"] = config.api_key
    try:
        client = Anthropic(**client_kwargs)
        logger.info("Claude {} model {} initialized", model_type_label, config.name)
        return client
    except Exception as e:
        # Log only the exception type — the message may contain partial api_key fragments.
        logger.error(
            "Failed to initialize Claude {} model {}: {}",
            model_type_label,
            config.name,
            type(e).__name__,
        )
        raise
