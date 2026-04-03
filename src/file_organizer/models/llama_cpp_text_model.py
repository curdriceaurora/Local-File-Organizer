# pyre-ignore-all-errors
"""Text model implementation using llama.cpp C bindings (llama-cpp-python).

Loads GGUF model files directly — no Ollama server required.

Install the optional dependency::

    pip install 'local-file-organizer[llama]'
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from file_organizer.models._llama_cpp_helpers import (
    extract_llama_cpp_text,
    is_llama_cpp_token_exhausted,
)
from file_organizer.models.base import (
    MAX_NUM_PREDICT,
    RETRY_MULTIPLIER,
    BaseModel,
    DeviceType,
    ModelConfig,
    ModelType,
    TokenExhaustionError,
)

try:
    from llama_cpp import Llama

    LLAMA_CPP_AVAILABLE = True
except ImportError:
    Llama = None
    LLAMA_CPP_AVAILABLE = False


_GPU_DEVICE_TYPES = {DeviceType.CUDA, DeviceType.MPS, DeviceType.METAL}


class LlamaCppTextModel(BaseModel):
    """Text generation model using llama.cpp C bindings.

    Loads a GGUF quantised model file directly via the ``llama-cpp-python``
    package.  No Ollama server or external service is required.

    Configure via ``ModelConfig.model_path`` (path to the ``.gguf`` file) and
    ``ModelConfig.device`` (CPU/CUDA/MPS/METAL/AUTO).  Override GPU layer
    offloading via ``ModelConfig.extra_params["n_gpu_layers"]``.
    """

    def __init__(self, config: ModelConfig) -> None:
        """Initialize the llama.cpp text model.

        Args:
            config: Model configuration. ``config.model_path`` must be a
                non-empty path to a ``.gguf`` file.

        Raises:
            ImportError: If ``llama-cpp-python`` is not installed.
            ValueError: If model type is not TEXT or ``model_path`` is missing.
        """
        if not LLAMA_CPP_AVAILABLE:
            raise ImportError(
                "The 'llama-cpp-python' package is not installed. "
                "Install it with: pip install 'local-file-organizer[llama]'"
            )

        if config.model_type != ModelType.TEXT:
            raise ValueError(
                f"LlamaCppTextModel only supports ModelType.TEXT, got {config.model_type}"
            )

        if not config.model_path:
            raise ValueError(
                "model_path must be a non-empty path to a .gguf file for LlamaCppTextModel"
            )

        super().__init__(config)
        self.client: Any | None = None  # llama_cpp.Llama; typed as Any for mypy without stubs

    def initialize(self) -> None:
        """Load the GGUF model file and create the Llama client.

        Raises:
            RuntimeError: If the model file cannot be loaded.
        """
        if self._initialized:
            logger.debug("LlamaCpp text model {} already initialized", self.config.name)
            return

        n_gpu_layers = self._device_to_gpu_layers()
        try:
            self.client = Llama(
                model_path=self.config.model_path,
                n_ctx=self.config.context_window,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
        except (RuntimeError, OSError, ValueError) as e:
            raise RuntimeError(
                f"Could not load GGUF model from '{self.config.model_path}': {e}"
            ) from e

        super().initialize()

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text using the loaded llama.cpp model.

        Args:
            prompt: User prompt.
            **kwargs: Override config values:
                - ``temperature`` (float)
                - ``max_tokens`` (int)
                - ``top_k`` (int)
                - ``top_p`` (float)

        Returns:
            Generated text, stripped of leading/trailing whitespace.

        Raises:
            RuntimeError: If the model is not initialised.
            TokenExhaustionError: If the model exhausts its token budget on
                both the initial attempt and the retry.
        """
        self._enter_generate()
        try:
            return self._do_generate(prompt, **kwargs)
        finally:
            self._exit_generate()

    def _do_generate(self, prompt: str, **kwargs: Any) -> str:
        """Internal generate logic, called while generation guard is held."""
        if self.client is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        temperature = float(kwargs.get("temperature", self.config.temperature))
        max_tokens = int(kwargs.get("max_tokens", self.config.max_tokens))
        top_k = int(kwargs.get("top_k", self.config.top_k))
        top_p = float(kwargs.get("top_p", self.config.top_p))

        try:
            logger.debug("Generating text with llama.cpp model {}", self.config.name)
            response = self.client(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                top_k=top_k,
                top_p=top_p,
            )

            if is_llama_cpp_token_exhausted(response):
                retry_max = min(max_tokens * RETRY_MULTIPLIER, MAX_NUM_PREDICT)
                logger.warning(
                    "Token exhaustion detected for llama.cpp model {}, retrying with max_tokens={}",
                    self.config.name,
                    retry_max,
                )
                response = self.client(
                    prompt,
                    temperature=temperature,
                    max_tokens=retry_max,
                    top_k=top_k,
                    top_p=top_p,
                )
                if is_llama_cpp_token_exhausted(response):
                    raise TokenExhaustionError(
                        f"llama.cpp model '{self.config.name}' exhausted token budget "
                        f"on retry (max_tokens={retry_max})"
                    )

            text = extract_llama_cpp_text(response)
            logger.debug("Generated {} characters", len(text))
            return text
        except TokenExhaustionError:
            raise
        except (RuntimeError, OSError, ValueError) as e:
            logger.error("Failed to generate text via llama.cpp: {}", type(e).__name__)
            raise

    def cleanup(self) -> None:
        """Release the Llama client and free model memory.

        Sets ``_initialized`` to *False* under the lifecycle lock so that
        concurrent ``generate()`` calls see a consistent state.  Unlike some
        providers, this class does not set a ``_shutting_down`` flag; cleanup
        is idempotent and can be called multiple times safely.
        """
        logger.debug("Cleaning up llama.cpp text model {}", self.config.name)
        with self._lifecycle_lock:
            if self.client is not None:
                try:
                    self.client.close()
                except (RuntimeError, OSError):
                    logger.opt(exception=True).debug(
                        "Ignoring exception during llama.cpp client close"
                    )
            self.client = None
            self._initialized = False

    def _device_to_gpu_layers(self) -> int:
        """Map ``config.device`` to an ``n_gpu_layers`` value for llama.cpp.

        Returns:
            ``-1`` to offload all layers to GPU (CUDA/MPS/METAL), ``0`` for
            CPU-only inference, or the explicit override from
            ``config.extra_params["n_gpu_layers"]``.
        """
        extra = self.config.extra_params or {}
        if "n_gpu_layers" in extra:
            return int(extra["n_gpu_layers"])
        if self.config.device in _GPU_DEVICE_TYPES:
            return -1
        logger.debug(
            "Device '{}' is not a GPU type; defaulting to CPU-only inference (n_gpu_layers=0)",
            self.config.device,
        )
        return 0  # CPU and AUTO

    @staticmethod
    def get_default_config(model_path: str = "") -> ModelConfig:
        """Return a default ``ModelConfig`` for a llama.cpp text model.

        Args:
            model_path: Path to the ``.gguf`` model file.  An empty string is
                valid here; the path is validated at ``LlamaCppTextModel()``
                construction time.

        Returns:
            A ``ModelConfig`` with ``provider="llama_cpp"`` and sensible
            defaults.
        """
        return ModelConfig(
            name="llama-cpp",
            model_type=ModelType.TEXT,
            provider="llama_cpp",
            model_path=model_path,
            temperature=0.5,
            max_tokens=3000,
            context_window=4096,
        )
