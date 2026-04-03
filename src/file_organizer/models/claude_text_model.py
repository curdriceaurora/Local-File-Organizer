"""Text model implementation using the Anthropic Claude API."""

from __future__ import annotations

from typing import Any

from loguru import logger

from file_organizer.models._claude_client import ANTHROPIC_AVAILABLE, create_claude_client
from file_organizer.models._claude_response import extract_claude_text, is_claude_token_exhausted
from file_organizer.models.base import (
    MAX_NUM_PREDICT,
    RETRY_MULTIPLIER,
    BaseModel,
    ModelConfig,
    ModelType,
    TokenExhaustionError,
)


class ClaudeTextModel(BaseModel):
    """Text generation model using the Anthropic Claude Messages API.

    Supports all Claude 3.x and later models:
    - claude-3-5-sonnet-20241022 (default)
    - claude-3-5-haiku-20241022
    - claude-3-opus-20240229
    - claude-3-haiku-20240307

    Configure via ``ModelConfig.api_key`` (or set ``ANTHROPIC_API_KEY`` in
    the environment — the SDK reads it automatically).
    """

    def __init__(self, config: ModelConfig) -> None:
        """Initialize Claude text model.

        Args:
            config: Model configuration.  ``config.api_key`` is used for
                authentication when set; otherwise the SDK reads
                ``ANTHROPIC_API_KEY`` from the environment.

        Raises:
            ImportError: If the ``anthropic`` package is not installed.
            ValueError: If model type is not TEXT.
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "The 'anthropic' package is not installed. "
                "Install it with: pip install 'local-file-organizer[claude]'"
            )

        if config.model_type != ModelType.TEXT:
            raise ValueError(f"Expected TEXT model type, got {config.model_type}")

        super().__init__(config)
        self.client: Any | None = None  # anthropic.Anthropic; typed as Any to avoid stubs

    def initialize(self) -> None:
        """Create the Anthropic client.

        The client validates connectivity lazily on the first API call, so
        ``initialize()`` never makes a network request.
        """
        if self._initialized:
            logger.debug("Claude text model {} already initialized", self.config.name)
            return

        self.client = create_claude_client(self.config, "text")
        super().initialize()

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text using the Anthropic Messages API.

        Args:
            prompt: User prompt.
            **kwargs: Override config values:
                - ``temperature`` (float)
                - ``max_tokens`` (int)

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

        try:
            logger.debug("Generating text with Claude model {}", self.config.name)
            response = self.client.messages.create(
                model=self.config.name,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
            )

            if is_claude_token_exhausted(response):
                retry_max = min(max_tokens * RETRY_MULTIPLIER, MAX_NUM_PREDICT)
                logger.warning(
                    "Token exhaustion detected for Claude model {}, retrying with max_tokens={}",
                    self.config.name,
                    retry_max,
                )
                response = self.client.messages.create(
                    model=self.config.name,
                    max_tokens=retry_max,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                )
                if is_claude_token_exhausted(response):
                    raise TokenExhaustionError(
                        f"Claude model '{self.config.name}' exhausted token budget "
                        f"on retry (max_tokens={retry_max})"
                    )

            content = extract_claude_text(response)
            logger.debug("Generated {} characters", len(content))
            return content
        except TokenExhaustionError:
            raise
        except (RuntimeError, ConnectionError, OSError, ValueError) as e:
            logger.error("Failed to generate text via Claude API: {}", type(e).__name__)
            raise

    def cleanup(self) -> None:
        """Release the Anthropic client.

        Calls ``client.close()`` (which closes the underlying ``httpx``
        connection pool) under the lifecycle lock so that concurrent
        ``generate()`` calls see a consistent state.
        """
        logger.debug("Cleaning up Claude text model {}", self.config.name)
        with self._lifecycle_lock:
            if self.client is not None:
                try:
                    self.client.close()
                except (RuntimeError, OSError):
                    logger.opt(exception=True).debug(
                        "Ignoring exception during Claude client close"
                    )
            self.client = None
            self._initialized = False

    @staticmethod
    def get_default_config(model_name: str = "claude-3-5-sonnet-20241022") -> ModelConfig:
        """Return a default ModelConfig for a Claude text model.

        Args:
            model_name: Anthropic model identifier.

        Returns:
            A ``ModelConfig`` with ``provider="claude"`` and sensible defaults.
        """
        return ModelConfig(
            name=model_name,
            model_type=ModelType.TEXT,
            provider="claude",
            temperature=0.5,
            max_tokens=3000,
        )
