"""Text model implementation using Ollama."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

try:
    import ollama

    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from loguru import logger

from file_organizer.models._ollama_response import (
    compute_retry_num_predict,
    format_exhaustion_diagnostics,
    is_token_exhausted,
)
from file_organizer.models.base import (
    MIN_USEFUL_RESPONSE_LENGTH,
    BaseModel,
    ModelConfig,
    ModelType,
    TokenExhaustionError,
)


class _GuardedIterator:
    """Wraps a generator to guarantee a cleanup callback fires on close.

    Unlike a bare generator whose ``finally`` only runs when the iterator is
    fully consumed or explicitly ``.close()``-d, this wrapper also invokes the
    callback from ``__del__`` so that abandoned iterators release the
    generation guard deterministically on garbage collection.
    """

    __slots__ = ("_inner", "_on_close", "_closed")

    def __init__(self, inner: Iterator[str], on_close: Callable[[], None]) -> None:
        self._inner = inner
        self._on_close = on_close
        self._closed = False

    def __iter__(self) -> _GuardedIterator:
        return self

    def __next__(self) -> str:
        try:
            return next(self._inner)
        except BaseException:
            self._finish()
            raise

    def close(self) -> None:
        """Explicitly close the iterator and release the generation guard."""
        self._finish()

    def _finish(self) -> None:
        if not self._closed:
            self._closed = True
            if hasattr(self._inner, "close"):
                self._inner.close()
            self._on_close()

    def __del__(self) -> None:
        self._finish()


class TextModel(BaseModel):
    """Text generation model using Ollama.

    This model wraps Ollama for text generation tasks like:
    - Content summarization
    - Category generation
    - Filename generation
    - Metadata extraction
    """

    def __init__(self, config: ModelConfig):
        """Initialize text model.

        Args:
            config: Model configuration

        Raises:
            ImportError: If Ollama is not installed
            ValueError: If model type is not TEXT
        """
        if not OLLAMA_AVAILABLE:
            raise ImportError("Ollama is not installed. Install it with: pip install ollama")

        if config.model_type != ModelType.TEXT:
            raise ValueError(f"Expected TEXT model type, got {config.model_type}")

        super().__init__(config)
        self.client: ollama.Client | None = None

    def initialize(self) -> None:
        """Initialize the Ollama client and pull model if needed."""
        if self._initialized:
            logger.debug("Text model {} already initialized", self.config.name)
            return

        logger.info("Initializing text model: {}", self.config.name)

        try:
            # Initialize Ollama client
            self.client = ollama.Client()

            # Check if model exists locally, pull if not
            try:
                self.client.show(self.config.name)
                logger.debug("Model {} found locally", self.config.name)
            except ollama.ResponseError:
                logger.info("Model {} not found locally, pulling...", self.config.name)
                self.client.pull(self.config.name)
                logger.info("Model {} pulled successfully", self.config.name)

            super().initialize()
            logger.info("Text model {} initialized successfully", self.config.name)

        except Exception as e:
            logger.error("Failed to initialize text model: {}", e)
            raise

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text response using Ollama.

        Args:
            prompt: Input prompt
            **kwargs: Additional generation parameters (overrides config)

        Returns:
            Generated text response

        Raises:
            RuntimeError: If model is not initialized.
            TokenExhaustionError: If the model exhausts its token budget on
                both the initial attempt and the retry without producing useful
                output.
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

        # Merge config with kwargs
        options = {
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_k": kwargs.get("top_k", self.config.top_k),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
        }

        # Add any extra params from config
        if self.config.extra_params:
            options.update(self.config.extra_params)

        try:
            logger.debug("Generating text with model {}", self.config.name)
            response = self.client.generate(
                model=self.config.name,
                prompt=prompt,
                options=options,
                stream=False,
            )

            # Detect token exhaustion and retry once with doubled budget
            if is_token_exhausted(response):
                diag = format_exhaustion_diagnostics(response, self.config.name)
                logger.warning("Token exhaustion detected, retrying: {}", diag)

                retry_num_predict = compute_retry_num_predict(options["num_predict"])
                options["num_predict"] = retry_num_predict

                response = self.client.generate(
                    model=self.config.name,
                    prompt=prompt,
                    options=options,
                    stream=False,
                )

                if is_token_exhausted(response):
                    retry_diag = format_exhaustion_diagnostics(response, self.config.name)
                    raise TokenExhaustionError(
                        f"Model exhausted token budget on retry. {retry_diag}"
                    )

            generated_text = str(response.get("response", "") or "")
            logger.debug(
                "Generated {} characters in {:.2f}s",
                len(generated_text),
                response.get("total_duration", 0) / 1e9,
            )

            return generated_text.strip()

        except TokenExhaustionError:
            raise
        except Exception as e:
            logger.error("Failed to generate text: {}", e)
            raise

    def generate_streaming(self, prompt: str, **kwargs: Any) -> Iterator[str]:
        """Generate text response with streaming.

        Returns a :class:`_GuardedIterator` that ensures the generation guard
        is released even if the caller abandons the iterator without fully
        consuming it or calling ``.close()``.

        .. note::
            Streaming cannot retry on token exhaustion because chunks have
            already been yielded to the caller.  If ``done_reason == "length"``
            the method logs a warning (or error for empty output) instead.

        Args:
            prompt: Input prompt
            **kwargs: Additional generation parameters

        Returns:
            An iterator of generated text chunks.

        Raises:
            RuntimeError: If model is not initialized
        """
        self._enter_generate()
        return _GuardedIterator(
            self._do_generate_streaming(prompt, **kwargs),
            self._exit_generate,
        )

    def _do_generate_streaming(self, prompt: str, **kwargs: Any) -> Iterator[str]:
        """Internal streaming logic, called while generation guard is held."""
        if self.client is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        options = {
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_k": kwargs.get("top_k", self.config.top_k),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
        }
        if self.config.extra_params:
            options.update(self.config.extra_params)

        try:
            stream = self.client.generate(
                model=self.config.name,
                prompt=prompt,
                options=options,
                stream=True,
            )

            accumulated_length = 0
            last_chunk: Any = {}

            for chunk in stream:
                last_chunk = chunk
                if "response" in chunk:
                    text = chunk["response"]
                    accumulated_length += len(text)
                    yield text

            # Post-stream: warn if token budget was exhausted
            if (
                last_chunk.get("done_reason") == "length"
                and accumulated_length < MIN_USEFUL_RESPONSE_LENGTH
            ):
                diag = format_exhaustion_diagnostics(last_chunk, self.config.name)
                logger.error("Streaming token exhaustion (no useful output): {}", diag)
            elif last_chunk.get("done_reason") == "length":
                logger.warning(
                    "Streaming response truncated at {} chars (done_reason=length) for model {}",
                    accumulated_length,
                    self.config.name,
                )

        except Exception as e:
            logger.error("Failed to generate streaming text: {}", e)
            raise

    def cleanup(self) -> None:
        """Cleanup model resources.

        Sets ``_initialized`` to *False* under the lifecycle lock so that
        concurrent ``generate()`` calls see a consistent state.
        """
        logger.debug("Cleaning up text model {}", self.config.name)
        with self._lifecycle_lock:
            self._initialized = False
            self.client = None

    @staticmethod
    def get_default_config(model_name: str = "qwen2.5:3b-instruct-q4_K_M") -> ModelConfig:
        """Get default configuration for text model.

        Args:
            model_name: Name of the Ollama model

        Returns:
            Default model configuration
        """
        return ModelConfig(
            name=model_name,
            model_type=ModelType.TEXT,
            quantization="q4_k_m",
            framework="ollama",
            temperature=0.5,
            max_tokens=3000,
            top_k=3,
            top_p=0.3,
            context_window=4096,
        )

    def test_connection(self) -> dict[str, Any]:
        """Test model connection and get info.

        Returns:
            Model information dictionary

        Raises:
            RuntimeError: If model is not initialized
        """
        if not self._initialized or self.client is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        try:
            info = self.client.show(self.config.name)
            return {
                "name": self.config.name,
                "size": info.get("size", "unknown"),
                "quantization": self.config.quantization,
                "status": "connected",
            }
        except Exception as e:
            logger.error("Failed to get model info: {}", e)
            return {
                "name": self.config.name,
                "status": "error",
                "error": str(e),
            }
