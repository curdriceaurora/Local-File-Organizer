"""Base model interface for all AI models."""

from __future__ import annotations

import threading
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
    """Abstract base class for all AI models.

    Thread-safety: ``_initialized`` and ``client`` are protected by
    ``_lifecycle_lock``.  A generation counter (``_active_generations``)
    tracks in-flight ``generate()`` calls so that ``safe_cleanup()``
    can wait for them to complete before tearing down the client.
    """

    #: Maximum seconds ``safe_cleanup`` will wait for in-flight generations.
    CLEANUP_TIMEOUT: float = 30.0

    def __init__(self, config: ModelConfig) -> None:
        """Initialize the model with configuration.

        Args:
            config: Model configuration
        """
        self.config = config
        self.model: Any | None = None
        self._initialized = False

        # Thread-safety primitives
        self._lifecycle_lock = threading.Lock()
        self._active_generations = 0
        self._shutting_down = False
        self._generation_done = threading.Condition(self._lifecycle_lock)

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the model. Must be called before inference.

        Subclasses **must** call ``super().initialize()`` after establishing
        their resources (client, etc.) to reset ``_shutting_down`` and set
        ``_initialized``.
        """
        with self._lifecycle_lock:
            self._shutting_down = False
            self._initialized = True

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

    # ------------------------------------------------------------------
    # Thread-safe generation guards
    # ------------------------------------------------------------------

    def _enter_generate(self) -> None:
        """Increment active generation count; raises if model is shutting down.

        Must be called at the start of ``generate()`` in subclasses.
        """
        with self._lifecycle_lock:
            if self._shutting_down:
                raise RuntimeError("Model is shutting down.")
            if not self._initialized:
                raise RuntimeError("Model not initialized. Call initialize() first.")
            self._active_generations += 1

    def _exit_generate(self) -> None:
        """Decrement active generation count and notify waiters.

        Must be called in a ``finally`` block at the end of ``generate()``.
        """
        with self._generation_done:
            self._active_generations -= 1
            self._generation_done.notify_all()

    def safe_cleanup(self) -> None:
        """Wait for in-flight generations to finish, then call ``cleanup()``.

        Sets ``_shutting_down`` under the lock to reject new ``generate()``
        calls, waits up to ``CLEANUP_TIMEOUT`` seconds for in-flight
        generations, then delegates to ``cleanup()``.
        """
        with self._generation_done:
            self._shutting_down = True
            self._generation_done.wait_for(
                lambda: self._active_generations == 0,
                timeout=self.CLEANUP_TIMEOUT,
            )
        self.cleanup()

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
        """Context manager exit — waits for in-flight generations."""
        self.safe_cleanup()

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"{self.__class__.__name__}("
            f"name={self.config.name}, "
            f"framework={self.config.framework}, "
            f"initialized={self._initialized})"
        )
