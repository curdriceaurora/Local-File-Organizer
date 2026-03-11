"""Base model interface for all AI models."""

from __future__ import annotations

import types
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Token-exhaustion constants
# ---------------------------------------------------------------------------
MIN_USEFUL_RESPONSE_LENGTH: int = 10
"""Responses shorter than this (chars) are considered effectively empty."""

MAX_NUM_PREDICT: int = 16384
"""Hard cap for ``num_predict`` / ``max_tokens`` on retry."""

RETRY_MULTIPLIER: int = 2
"""Factor by which the token budget is multiplied on retry."""


# ---------------------------------------------------------------------------
# Shared image-analysis prompt templates
# ---------------------------------------------------------------------------
IMAGE_ANALYSIS_PROMPTS: dict[str, str] = {
    "describe": (
        "Please provide a detailed description of this image, "
        "focusing on the main subject and any important details."
    ),
    "categorize": (
        "Based on this image, generate a general category or theme "
        "that best represents the main subject. "
        "Limit the category to a maximum of 2 words. "
        "Use nouns and avoid verbs."
    ),
    "ocr": (
        "Extract all visible text from this image. "
        "Provide the text exactly as it appears, preserving formatting where possible."
    ),
    "filename": (
        "Based on this image, generate a specific and descriptive filename. "
        "Limit the filename to a maximum of 3 words. "
        "Use nouns and avoid starting with verbs. "
        "Use only letters and connect words with underscores."
    ),
}
"""Reusable prompt templates for common image analysis tasks."""


class TokenExhaustionError(RuntimeError):
    """Raised when a model exhausts its token budget without producing useful output.

    This typically happens when thinking-enabled models (e.g. qwen3, deepseek-r1)
    spend all allocated tokens on internal reasoning, or when ``num_predict`` /
    ``max_tokens`` is too low for the given prompt complexity.

    Callers should either increase the token budget or simplify the prompt.
    """


class ModelType(Enum):
    """Types of AI models supported."""

    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"
    VIDEO = "video"


class DeviceType(Enum):
    """Types of devices for inference."""

    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"  # Apple Silicon
    METAL = "metal"  # Apple Silicon (MLX)


@dataclass
class ModelConfig:
    """Configuration for AI models."""

    name: str
    model_type: ModelType
    quantization: str = "q4_k_m"
    device: DeviceType = DeviceType.AUTO
    temperature: float = 0.5
    max_tokens: int = 3000
    top_k: int = 3
    top_p: float = 0.3
    context_window: int = 4096
    batch_size: int = 1

    # Framework specific
    framework: str = "ollama"  # ollama, llama_cpp, mlx

    # Provider selection
    provider: Literal["ollama", "openai"] = "ollama"
    api_key: str | None = None  # For OpenAI-compatible providers
    api_base_url: str | None = None  # Custom endpoint (LM Studio, Groq, vLLM, etc.)

    # Model paths
    model_path: str | None = None
    local_path: str | None = None

    # Additional parameters
    extra_params: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """Initialize extra params and sync legacy ``framework`` field."""
        if self.extra_params is None:
            self.extra_params = {}
        # Keep the legacy ``framework`` field in sync with ``provider``.
        # ``provider`` is the authoritative routing field used by
        # ``provider_factory``; ``framework`` is retained for backward
        # compatibility with code that reads it directly.
        if self.provider == "openai" and self.framework == "ollama":
            self.framework = "openai"


class BaseModel(ABC):
    """Abstract base class for all AI models."""

    def __init__(self, config: ModelConfig) -> None:
        """Initialize the model with configuration.

        Args:
            config: Model configuration
        """
        self.config = config
        self.model: Any | None = None
        self._initialized = False

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the model. Must be called before inference."""
        pass

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate response from the model.

        Args:
            prompt: Input prompt
            **kwargs: Additional generation parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup model resources."""
        pass

    @property
    def is_initialized(self) -> bool:
        """Check if model is initialized."""
        return self._initialized

    def __enter__(self) -> BaseModel:
        """Context manager entry."""
        if not self._initialized:
            self.initialize()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Context manager exit."""
        self.cleanup()

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"{self.__class__.__name__}("
            f"name={self.config.name}, "
            f"framework={self.config.framework}, "
            f"initialized={self._initialized})"
        )
