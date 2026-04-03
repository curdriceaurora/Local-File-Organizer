# pyre-ignore-all-errors
"""Text model implementation using Apple's MLX runtime (mlx-lm).

This provider targets Apple Silicon local inference through ``mlx_lm`` and is
registered as ``provider="mlx"`` in the provider registry.

Install the optional dependency::

    pip install 'local-file-organizer[mlx]'
"""

from __future__ import annotations

import threading
from typing import Any

from loguru import logger

from file_organizer.models.base import BaseModel, ModelConfig, ModelType

try:
    from mlx_lm import generate as mlx_generate
    from mlx_lm import load as mlx_load

    MLX_LM_AVAILABLE = True
except ImportError:
    mlx_generate = None
    mlx_load = None
    MLX_LM_AVAILABLE = False


class MLXTextModel(BaseModel):
    """Text generation model backed by ``mlx_lm``.

    ``mlx_lm.load()`` returns a ``(model, tokenizer)`` pair that is cached on
    the instance after ``initialize()``. Generation delegates to
    ``mlx_lm.generate``.
    """

    def __init__(self, config: ModelConfig) -> None:
        """Initialize the MLX text model.

        Args:
            config: Model configuration. ``config.model_path`` must be a
                non-empty Hugging Face repo id or local model path.

        Raises:
            ImportError: If ``mlx-lm`` is not installed.
            ValueError: If model type is not TEXT or ``model_path`` is missing.
        """
        if not MLX_LM_AVAILABLE:
            raise ImportError(
                "The 'mlx-lm' package is not installed. "
                "Install it with: pip install 'local-file-organizer[mlx]'"
            )

        if config.model_type != ModelType.TEXT:
            raise ValueError(f"MLXTextModel only supports ModelType.TEXT, got {config.model_type}")

        if not config.model_path:
            raise ValueError("model_path must be a non-empty path or repo id for MLXTextModel")

        super().__init__(config)
        self._model: Any | None = None
        self._tokenizer: Any | None = None
        self._working_variant_idx: int | None = None
        self._init_lock = threading.Lock()

    def initialize(self) -> None:
        """Load model/tokenizer pair via ``mlx_lm.load``.

        Uses double-checked locking to prevent concurrent initialization races.

        Raises:
            RuntimeError: If model loading fails.
        """
        # First check (without lock for performance)
        if self._initialized:
            logger.debug("MLX text model {} already initialized", self.config.name)
            return

        # Acquire lock for critical section
        with self._init_lock:
            # Second check (after acquiring lock)
            if self._initialized:
                return

            if mlx_load is None:  # guarded by MLX_LM_AVAILABLE in __init__; belt-and-suspenders
                raise RuntimeError("mlx_load is None — mlx-lm is required; should not be reachable")
            try:
                loaded = mlx_load(self.config.model_path)
            except (RuntimeError, OSError, ValueError, ImportError) as exc:
                raise RuntimeError(
                    f"Could not load MLX model from '{self.config.model_path}': {exc}"
                ) from exc

            if not isinstance(loaded, tuple) or len(loaded) < 2:
                raise RuntimeError(
                    "mlx_lm.load() returned an unexpected value; expected (model, tokenizer)"
                )

            self._model = loaded[0]
            self._tokenizer = loaded[1]
            super().initialize()

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from prompt via ``mlx_lm.generate``.

        Args:
            prompt: User prompt.
            **kwargs: Generation overrides such as ``temperature`` and
                ``max_tokens``.

        Returns:
            Generated text with surrounding whitespace stripped.
        """
        self._enter_generate()
        try:
            return self._do_generate(prompt, **kwargs)
        finally:
            self._exit_generate()

    def _do_generate(self, prompt: str, **kwargs: Any) -> str:
        """Internal generate logic; called by ``generate()`` while the generation guard is held."""
        if self._model is None or self._tokenizer is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        temperature = float(kwargs.get("temperature", self.config.temperature))
        max_tokens = int(kwargs.get("max_tokens", self.config.max_tokens))
        top_p = float(kwargs.get("top_p", self.config.top_p))
        top_k = int(kwargs.get("top_k", self.config.top_k))

        if mlx_generate is None:  # guarded by MLX_LM_AVAILABLE in __init__; belt-and-suspenders
            raise RuntimeError("mlx_generate is None — mlx-lm is required; should not be reachable")
        try:
            response = self._call_generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
            )
            text = response.strip() if isinstance(response, str) else str(response).strip()
            logger.debug("Generated {} characters via MLX", len(text))
            return text
        except (RuntimeError, OSError, ValueError, TypeError) as exc:
            logger.error("Failed to generate text via MLX: {}", type(exc).__name__)
            raise

    def _call_generate(
        self,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
        top_p: float,
        top_k: int,
    ) -> Any:
        """Call ``mlx_lm.generate`` with conservative compatibility fallbacks.

        ``mlx_lm`` has changed keyword names across versions. We first try the
        most expressive call and gracefully fall back for older signatures.
        The successful variant is cached on the instance so subsequent calls
        skip the probe loop entirely.
        """
        if mlx_generate is None:  # guarded by MLX_LM_AVAILABLE in __init__; belt-and-suspenders
            raise RuntimeError("mlx_generate is None — mlx-lm is required; should not be reachable")
        call_variants: tuple[dict[str, Any], ...] = (
            {"max_tokens": max_tokens, "temp": temperature, "top_p": top_p, "top_k": top_k},
            {"max_tokens": max_tokens, "temperature": temperature, "top_p": top_p, "top_k": top_k},
            {"max_tokens": max_tokens, "temp": temperature},
            {"max_tokens": max_tokens, "temperature": temperature},
            {"max_tokens": max_tokens},
        )

        # Fast path: reuse the variant that succeeded on the first call.
        if self._working_variant_idx is not None:
            return mlx_generate(
                self._model, self._tokenizer, prompt, **call_variants[self._working_variant_idx]
            )

        last_error: TypeError | None = None
        for idx, variant in enumerate(call_variants):
            try:
                result = mlx_generate(self._model, self._tokenizer, prompt, **variant)
                self._working_variant_idx = idx  # cache for all subsequent calls
                return result
            except TypeError as exc:
                if not self._is_signature_mismatch_type_error(exc):
                    raise
                last_error = exc
        if last_error is not None:
            raise last_error
        raise RuntimeError("All mlx_lm.generate signature variants failed unexpectedly")

    @staticmethod
    def _is_signature_mismatch_type_error(exc: TypeError) -> bool:
        """Return True when ``TypeError`` indicates call-signature mismatch."""
        message = str(exc).lower()
        signature_markers = (
            "unexpected keyword argument",
            "got an unexpected keyword",
            "required positional argument",
            "positional arguments but",
            "takes no keyword arguments",
        )
        return any(marker in message for marker in signature_markers)

    def cleanup(self) -> None:
        """Release references to loaded model/tokenizer resources."""
        logger.debug("Cleaning up MLX text model {}", self.config.name)
        with self._generation_done:
            self._shutting_down = True
            drained = self._generation_done.wait_for(
                lambda: self._active_generations == 0,
                timeout=self.CLEANUP_TIMEOUT,
            )
            if not drained:
                logger.warning(
                    "Timed out waiting for {} in-flight MLX generation(s) before cleanup",
                    self._active_generations,
                )
            self._model = None
            self._tokenizer = None
            self._initialized = False

    @staticmethod
    def get_default_config(model_path: str = "") -> ModelConfig:
        """Return a default ``ModelConfig`` for MLX text generation."""
        return ModelConfig(
            name="mlx-lm",
            model_type=ModelType.TEXT,
            provider="mlx",
            model_path=model_path,
            temperature=0.5,
            max_tokens=3000,
            context_window=4096,
        )
