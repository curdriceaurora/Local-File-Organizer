"""Read provider configuration from environment variables.

Supported variables::

    FO_PROVIDER=openai          # "ollama" (default) or "openai"
    FO_OPENAI_API_KEY=sk-...    # Required when FO_PROVIDER=openai and endpoint needs auth
    FO_OPENAI_BASE_URL=https://api.openai.com/v1
    FO_OPENAI_MODEL=gpt-4o      # Text model name
    FO_OPENAI_VISION_MODEL=gpt-4o  # Vision model; falls back to FO_OPENAI_MODEL

Usage::

    text_cfg, vision_cfg = get_model_configs_from_env()
    organizer = FileOrganizer(text_model_config=text_cfg, vision_model_config=vision_cfg)
"""

from __future__ import annotations

import os
from typing import Literal

from loguru import logger

from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.models.text_model import TextModel
from file_organizer.models.vision_model import VisionModel

_OPENAI_TEXT_DEFAULT = "gpt-4o-mini"
_OPENAI_VISION_DEFAULT = "gpt-4o-mini"


def get_current_provider() -> Literal["ollama", "openai"]:
    """Return the active provider from env, validated against known values."""
    raw = os.environ.get("FO_PROVIDER", "ollama").strip().lower()
    if raw not in ("ollama", "openai"):
        logger.warning(
            "FO_PROVIDER=%r is not a recognised value; falling back to 'ollama'. "
            "Supported values: 'ollama', 'openai'.",
            raw,
        )
        return "ollama"
    return raw  # type: ignore[return-value]


def get_model_configs_from_env() -> tuple[ModelConfig, ModelConfig]:
    """Build text and vision ``ModelConfig`` objects from environment variables.

    Returns:
        A ``(text_config, vision_config)`` tuple.  When ``FO_PROVIDER`` is
        ``"ollama"`` (or unset), the Ollama defaults are returned unchanged.
        When ``FO_PROVIDER=openai`` the OpenAI-compatible defaults are used,
        overridden by any ``FO_OPENAI_*`` variables that are set.

    Note:
        This function reads environment variables at call time and must **not**
        be decorated with ``@lru_cache`` because env vars can change between
        calls (e.g. in tests).
    """
    provider = get_current_provider()

    if provider == "ollama":
        return TextModel.get_default_config(), VisionModel.get_default_config()

    # --- OpenAI-compatible provider ---
    api_key: str | None = os.environ.get("FO_OPENAI_API_KEY") or None
    api_base_url: str | None = os.environ.get("FO_OPENAI_BASE_URL") or None
    text_model_name = os.environ.get("FO_OPENAI_MODEL", _OPENAI_TEXT_DEFAULT)
    vision_model_name = os.environ.get("FO_OPENAI_VISION_MODEL") or text_model_name

    if not api_key and not api_base_url:
        logger.warning(
            "FO_PROVIDER=openai but neither FO_OPENAI_API_KEY nor FO_OPENAI_BASE_URL "
            "is set.  Requests will likely fail.  For local providers (LM Studio, "
            "Ollama OpenAI-compat) set FO_OPENAI_BASE_URL."
        )

    text_config = ModelConfig(
        name=text_model_name,
        model_type=ModelType.TEXT,
        provider="openai",
        api_key=api_key,
        api_base_url=api_base_url,
    )
    vision_config = ModelConfig(
        name=vision_model_name,
        model_type=ModelType.VISION,
        provider="openai",
        api_key=api_key,
        api_base_url=api_base_url,
    )

    logger.info(
        "Provider configured from env: provider=%s, text_model=%s, vision_model=%s, "
        "base_url=%s",
        provider,
        text_model_name,
        vision_model_name,
        api_base_url or "(default)",
    )

    return text_config, vision_config
