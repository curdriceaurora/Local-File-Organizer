"""Text model implementation using OpenAI-compatible API."""

from __future__ import annotations

from typing import Any

from loguru import logger

from file_organizer.models._openai_client import OPENAI_AVAILABLE, create_openai_client
from file_organizer.models._openai_response import is_openai_token_exhausted
from file_organizer.models.base import (
    MAX_NUM_PREDICT,
    RETRY_MULTIPLIER,
    BaseModel,
    ModelConfig,
    ModelType,
    TokenExhaustionError,
)


class OpenAITextModel(BaseModel):
    """Text generation model using an OpenAI-compatible API.

    Works with any provider that speaks the OpenAI REST format:
    - OpenAI (https://api.openai.com/v1)
    - LM Studio (http://localhost:1234/v1)
    - Groq (https://api.groq.com/openai/v1)
    - Together.ai (https://api.together.xyz/v1)
    - Ollama OpenAI-compat endpoint (http://localhost:11434/v1)
    - vLLM (http://localhost:8000/v1)

    Configure via ``ModelConfig.api_key`` and ``ModelConfig.api_base_url``.
    """

    def __init__(self, config: ModelConfig) -> None:
        """Initialize OpenAI text model.

        Args:
            config: Model configuration. ``config.api_key`` and
                ``config.api_base_url`` are used for authentication and
                endpoint routing.

        Raises:
            ImportError: If the ``openai`` package is not installed.
            ValueError: If model type is not TEXT.
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "The 'openai' package is not installed. "
                "Install it with: pip install 'local-file-organizer[cloud]'"
            )

        if config.model_type != ModelType.TEXT:
            raise ValueError(f"Expected TEXT model type, got {config.model_type}")

        super().__init__(config)
        self.client: Any | None = None  # openai.OpenAI; typed as Any to satisfy mypy without stub

    def initialize(self) -> None:
        """Create the OpenAI client.

        The client validates connectivity lazily on the first API call, so
        ``initialize()`` never makes a network request.
        """
        if self._initialized:
            logger.debug("OpenAI text model {} already initialized", self.config.name)
            return

        self.client = create_openai_client(self.config, "text")
        self._initialized = True

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text using the OpenAI chat completions API.

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
        if not self._initialized or self.client is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        temperature = float(kwargs.get("temperature", self.config.temperature))
        max_tokens = int(kwargs.get("max_tokens", self.config.max_tokens))

        try:
            logger.debug("Generating text with OpenAI model {}", self.config.name)
            response = self.client.chat.completions.create(
                model=self.config.name,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if is_openai_token_exhausted(response):
                retry_max = min(max_tokens * RETRY_MULTIPLIER, MAX_NUM_PREDICT)
                logger.warning(
                    "Token exhaustion detected for OpenAI model {}, retrying with max_tokens={}",
                    self.config.name,
                    retry_max,
                )
                response = self.client.chat.completions.create(
                    model=self.config.name,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=retry_max,
                )
                if is_openai_token_exhausted(response):
                    raise TokenExhaustionError(
                        f"OpenAI model '{self.config.name}' exhausted token budget "
                        f"on retry (max_tokens={retry_max})"
                    )

            if not response.choices:
                logger.warning("OpenAI API returned empty choices for model {}", self.config.name)
                return ""
            content = response.choices[0].message.content or ""
            logger.debug("Generated {} characters", len(content))
            return content.strip()
        except TokenExhaustionError:
            raise
        except Exception as e:
            logger.error("Failed to generate text via OpenAI API: {}", type(e).__name__)
            raise

    def cleanup(self) -> None:
        """Release the OpenAI client."""
        logger.debug("Cleaning up OpenAI text model {}", self.config.name)
        if self.client is not None:
            try:
                self.client.close()
            except Exception:
                pass
        self.client = None
        self._initialized = False

    @staticmethod
    def get_default_config(model_name: str = "gpt-4o-mini") -> ModelConfig:
        """Return a default ModelConfig for an OpenAI text model.

        Args:
            model_name: OpenAI (or compatible) model identifier.

        Returns:
            A ``ModelConfig`` with ``provider="openai"`` and sensible defaults.
        """
        return ModelConfig(
            name=model_name,
            model_type=ModelType.TEXT,
            provider="openai",
            temperature=0.5,
            max_tokens=3000,
        )
