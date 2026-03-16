"""Read provider configuration from environment variables and config profiles.

Supported environment variables::

    FO_PROVIDER=openai          # "ollama" (default), "openai", "llama_cpp", "mlx", or "claude"
    FO_OPENAI_API_KEY=sk-...    # Required when FO_PROVIDER=openai and endpoint needs auth
    FO_OPENAI_BASE_URL=https://api.openai.com/v1
    FO_OPENAI_MODEL=gpt-4o      # Text model name
    FO_OPENAI_VISION_MODEL=gpt-4o  # Vision model; falls back to FO_OPENAI_MODEL
    FO_LLAMA_CPP_MODEL_PATH=/path/to/model.gguf  # Required when FO_PROVIDER=llama_cpp
    FO_LLAMA_CPP_N_GPU_LAYERS=0  # Optional; overrides device-based default
    FO_MLX_MODEL_PATH=mlx-community/Qwen2.5-3B-Instruct-4bit  # Required when FO_PROVIDER=mlx
    FO_CLAUDE_API_KEY=sk-ant-...  # Optional when FO_PROVIDER=claude; falls back to ANTHROPIC_API_KEY
    FO_CLAUDE_MODEL=claude-3-5-sonnet-20241022  # Text model name
    FO_CLAUDE_VISION_MODEL=claude-3-5-sonnet-20241022  # Vision model; falls back to FO_CLAUDE_MODEL
    FO_PROFILE=default          # Config profile name to load (default: "default")

Priority cascade (highest wins)::

    1. Explicit ``ModelConfig`` parameters passed to ``FileOrganizer``
    2. Environment variables (``FO_PROVIDER``, ``FO_OPENAI_*``, ``FO_LLAMA_CPP_*``, ``FO_CLAUDE_*``)
    3. Config profile (resolved via ``platformdirs.user_config_dir``)
    4. Hardcoded defaults

Usage::

    text_cfg, vision_cfg = get_model_configs()
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
_CLAUDE_TEXT_DEFAULT = "claude-3-5-sonnet-20241022"


def get_current_provider() -> Literal["ollama", "openai", "llama_cpp", "mlx", "claude"]:
    """Return the active provider from env, validated against known values."""
    raw = os.environ.get("FO_PROVIDER", "ollama").strip().lower()
    if raw not in ("ollama", "openai", "llama_cpp", "mlx", "claude"):
        logger.warning(
            "FO_PROVIDER={} is not a recognised value; falling back to 'ollama'. "
            "Supported values: 'ollama', 'openai', 'llama_cpp', 'mlx', 'claude'.",
            raw,
        )
        return "ollama"
    return raw  # type: ignore[return-value]


def _get_llama_cpp_configs() -> tuple[ModelConfig, ModelConfig]:
    """Build llama.cpp text and vision ``ModelConfig`` objects from env vars.

    Reads ``FO_LLAMA_CPP_MODEL_PATH`` and optionally
    ``FO_LLAMA_CPP_N_GPU_LAYERS``.  Emits a warning if the model path is
    not set, as requests will fail at ``initialize()`` time.

    Returns:
        A ``(text_config, vision_config)`` tuple.  Both share the same
        ``model_path``; vision config is included for API parity even though
        the llama_cpp vision factory is not yet registered (Phase 2).
    """
    model_path = (os.environ.get("FO_LLAMA_CPP_MODEL_PATH") or "").strip()
    n_gpu_layers_raw = (os.environ.get("FO_LLAMA_CPP_N_GPU_LAYERS") or "").strip()

    if not model_path:
        logger.warning(
            "FO_PROVIDER=llama_cpp but FO_LLAMA_CPP_MODEL_PATH is not set. "
            "LlamaCppTextModel.initialize() will raise ValueError. "
            "Set FO_LLAMA_CPP_MODEL_PATH to the path of your .gguf model file."
        )

    extra_params: dict[str, int] = {}
    if n_gpu_layers_raw:
        try:
            extra_params["n_gpu_layers"] = int(n_gpu_layers_raw)
        except ValueError:
            logger.warning(
                "FO_LLAMA_CPP_N_GPU_LAYERS={} is not a valid integer; ignoring.",
                n_gpu_layers_raw,
            )

    text_config = ModelConfig(
        name="llama-cpp",
        model_type=ModelType.TEXT,
        provider="llama_cpp",
        model_path=model_path,
        extra_params=extra_params,
    )
    vision_config = ModelConfig(
        name="llama-cpp",
        model_type=ModelType.VISION,
        provider="llama_cpp",
        model_path=model_path,
        extra_params=extra_params,
    )

    logger.info(
        "Provider configured from env: provider=llama_cpp, model_path={}",
        model_path or "(unset)",
    )
    logger.warning(
        "llama_cpp vision support is not yet available (Phase 2). "
        "Image files will fall back to extension-based organization."
    )

    return text_config, vision_config


def _get_mlx_configs() -> tuple[ModelConfig, ModelConfig]:
    """Build MLX text and vision ``ModelConfig`` objects from env vars.

    Reads ``FO_MLX_MODEL_PATH`` (Hugging Face repo or local path). Emits a
    warning if the model path is not set, as requests will fail at
    ``initialize()`` time.

    Returns:
        A ``(text_config, vision_config)`` tuple. Vision is returned for API
        parity even though an MLX vision factory is not yet registered.
    """
    model_path = (os.environ.get("FO_MLX_MODEL_PATH") or "").strip()
    if not model_path:
        logger.warning(
            "FO_PROVIDER=mlx but FO_MLX_MODEL_PATH is not set. "
            "MLXTextModel.initialize() will raise ValueError. "
            "Set FO_MLX_MODEL_PATH to a local model path or Hugging Face repo id."
        )

    text_config = ModelConfig(
        name="mlx-lm",
        model_type=ModelType.TEXT,
        provider="mlx",
        model_path=model_path,
    )
    vision_config = ModelConfig(
        name="mlx-lm",
        model_type=ModelType.VISION,
        provider="mlx",
        model_path=model_path,
    )

    logger.info(
        "Provider configured from env: provider=mlx, model_path={}",
        model_path or "(unset)",
    )
    logger.warning(
        "mlx vision support is not yet available (Phase 3). "
        "Image files will fall back to extension-based organization."
    )

    return text_config, vision_config


def _get_claude_configs() -> tuple[ModelConfig, ModelConfig]:
    """Build Claude text and vision ``ModelConfig`` objects from env vars.

    Reads ``FO_CLAUDE_API_KEY`` (falls back silently to ``ANTHROPIC_API_KEY``
    which the SDK picks up automatically).  Emits a warning only when **both**
    are absent, since requests would then fail at ``initialize()`` time.

    Returns:
        A ``(text_config, vision_config)`` tuple.  Both may share the same
        model name unless ``FO_CLAUDE_VISION_MODEL`` is set separately.
    """
    api_key: str | None = (os.environ.get("FO_CLAUDE_API_KEY") or "").strip() or None
    text_model_name = (os.environ.get("FO_CLAUDE_MODEL") or "").strip() or _CLAUDE_TEXT_DEFAULT
    vision_model_name = (os.environ.get("FO_CLAUDE_VISION_MODEL") or "").strip() or text_model_name

    # Warn only when neither FO_CLAUDE_API_KEY nor the SDK-native ANTHROPIC_API_KEY is set.
    sdk_key_present = bool(os.environ.get("ANTHROPIC_API_KEY", "").strip())
    if not api_key and not sdk_key_present:
        logger.warning(
            "FO_PROVIDER=claude but neither FO_CLAUDE_API_KEY nor ANTHROPIC_API_KEY "
            "is set.  Requests will fail.  "
            "Set FO_CLAUDE_API_KEY or ANTHROPIC_API_KEY to your Anthropic API key."
        )

    text_config = ModelConfig(
        name=text_model_name,
        model_type=ModelType.TEXT,
        provider="claude",
        api_key=api_key,
    )
    vision_config = ModelConfig(
        name=vision_model_name,
        model_type=ModelType.VISION,
        provider="claude",
        api_key=api_key,
    )

    logger.info(
        "Provider configured from env: provider=claude, text_model={}, vision_model={}",
        text_model_name,
        vision_model_name,
    )

    return text_config, vision_config


def get_model_configs_from_env() -> tuple[ModelConfig, ModelConfig]:
    """Build text and vision ``ModelConfig`` objects from environment variables.

    Returns:
        A ``(text_config, vision_config)`` tuple.  When ``FO_PROVIDER`` is
        ``"ollama"`` (or unset), the Ollama defaults are returned unchanged.
        When ``FO_PROVIDER=openai`` the OpenAI-compatible defaults are used,
        overridden by any ``FO_OPENAI_*`` variables that are set.
        When ``FO_PROVIDER=llama_cpp`` the llama.cpp defaults are used,
        driven by ``FO_LLAMA_CPP_MODEL_PATH`` and optionally
        ``FO_LLAMA_CPP_N_GPU_LAYERS``.
        When ``FO_PROVIDER=mlx`` MLX defaults are used, driven by
        ``FO_MLX_MODEL_PATH``.
        When ``FO_PROVIDER=claude`` the Claude defaults are used, driven by
        ``FO_CLAUDE_API_KEY`` / ``ANTHROPIC_API_KEY``, ``FO_CLAUDE_MODEL``,
        and optionally ``FO_CLAUDE_VISION_MODEL``.

    Note:
        This function reads environment variables at call time and must **not**
        be decorated with ``@lru_cache`` because env vars can change between
        calls (e.g. in tests).
    """
    provider = get_current_provider()

    if provider == "ollama":
        return TextModel.get_default_config(), VisionModel.get_default_config()

    if provider == "llama_cpp":
        return _get_llama_cpp_configs()

    if provider == "mlx":
        return _get_mlx_configs()

    if provider == "claude":
        return _get_claude_configs()

    # --- OpenAI-compatible provider ---
    # Strip whitespace and convert empty strings to None so callers receive
    # clean values (e.g. FO_OPENAI_API_KEY="" is the same as unset).
    api_key: str | None = (os.environ.get("FO_OPENAI_API_KEY") or "").strip() or None
    api_base_url: str | None = (os.environ.get("FO_OPENAI_BASE_URL") or "").strip() or None
    text_model_name = (os.environ.get("FO_OPENAI_MODEL") or "").strip() or _OPENAI_TEXT_DEFAULT
    vision_model_name = (os.environ.get("FO_OPENAI_VISION_MODEL") or "").strip() or text_model_name

    # Suppress the warning when the standard OPENAI_API_KEY env var is set —
    # the SDK will pick it up automatically, so requests will succeed even
    # without FO_OPENAI_API_KEY or FO_OPENAI_BASE_URL.
    sdk_key_present = bool(os.environ.get("OPENAI_API_KEY", "").strip())
    if not api_key and not api_base_url and not sdk_key_present:
        logger.warning(
            "FO_PROVIDER=openai but neither FO_OPENAI_API_KEY nor FO_OPENAI_BASE_URL "
            "is set (and OPENAI_API_KEY is also absent).  Requests will likely fail.  "
            "For local providers (LM Studio, Ollama OpenAI-compat) set FO_OPENAI_BASE_URL."
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
        "Provider configured from env: provider={}, text_model={}, vision_model={}, base_url={}",
        provider,
        text_model_name,
        vision_model_name,
        api_base_url or "(default)",
    )

    return text_config, vision_config


def _get_model_configs_from_profile(
    profile: str = "default",
) -> tuple[ModelConfig, ModelConfig] | None:
    """Try to load model configs from a saved configuration profile.

    Returns:
        A ``(text_config, vision_config)`` tuple if a profile with
        non-default model names exists, otherwise *None*.
    """
    try:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import ModelPreset

        mgr = ConfigManager()
        app_cfg = mgr.load(profile)

        # Only fall through when the entire model preset is still at defaults.
        if app_cfg.models == ModelPreset():
            return None

        text_cfg = mgr.to_text_model_config(app_cfg)
        vision_cfg = mgr.to_vision_model_config(app_cfg)
        logger.info(
            "Model config loaded from profile '{}': text={}, vision={}",
            profile,
            text_cfg.name,
            vision_cfg.name,
        )
        return text_cfg, vision_cfg
    except Exception:
        logger.opt(exception=True).debug("Could not load config profile '{}', skipping", profile)
        return None


def get_model_configs(
    profile: str | None = None,
) -> tuple[ModelConfig, ModelConfig]:
    """Resolve model configs using the priority cascade.

    Priority (highest wins):

    1. Environment variables (``FO_PROVIDER`` / ``FO_OPENAI_*`` / ``FO_LLAMA_CPP_*``)
    2. Config profile from disk
    3. Hardcoded defaults

    Args:
        profile: Config profile name.  Defaults to the ``FO_PROFILE``
            environment variable, falling back to ``"default"``.

    Returns:
        A ``(text_config, vision_config)`` tuple.
    """
    # If provider env var is explicitly set, env takes precedence
    if os.environ.get("FO_PROVIDER", "").strip():
        logger.debug("FO_PROVIDER is set — using environment config")
        return get_model_configs_from_env()

    # Try config profile
    profile_name = profile or os.environ.get("FO_PROFILE", "").strip() or "default"
    profile_configs = _get_model_configs_from_profile(profile_name)
    if profile_configs is not None:
        return profile_configs

    # Fall back to env-based defaults (Ollama defaults)
    return get_model_configs_from_env()
