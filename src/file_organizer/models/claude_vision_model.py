# pyre-ignore-all-errors
"""Vision model implementation using the Anthropic Claude API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger

from file_organizer.models._claude_client import ANTHROPIC_AVAILABLE, create_claude_client
from file_organizer.models._claude_response import extract_claude_text, is_claude_token_exhausted
from file_organizer.models._vision_helpers import (
    bytes_to_data_url,
    image_to_data_url,
    split_data_url,
)
from file_organizer.models.base import (
    IMAGE_ANALYSIS_PROMPTS,
    MAX_NUM_PREDICT,
    RETRY_MULTIPLIER,
    BaseModel,
    ModelConfig,
    ModelType,
    TokenExhaustionError,
)


def _build_image_block(data_url: str) -> dict[str, Any]:
    """Convert a base64 data URL into a Claude ``image`` content block.

    The Anthropic Messages API uses a different image format than OpenAI:
    - OpenAI: ``{"type": "image_url", "image_url": {"url": "data:..."}}``
    - Claude:  ``{"type": "image", "source": {"type": "base64",
                   "media_type": "image/png", "data": "<b64>"}}``

    Args:
        data_url: Base64 data URL produced by
            :func:`~file_organizer.models._vision_helpers.image_to_data_url` or
            :func:`~file_organizer.models._vision_helpers.bytes_to_data_url`.

    Returns:
        A dict suitable for the ``content`` list in a Claude messages payload.
    """
    mime_type, base64_data = split_data_url(data_url)
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": mime_type,
            "data": base64_data,
        },
    }


class ClaudeVisionModel(BaseModel):
    """Vision-language model using the Anthropic Claude Messages API.

    Supports Claude 3.x and later vision-capable models:
    - claude-3-5-sonnet-20241022 (default)
    - claude-3-5-haiku-20241022
    - claude-3-opus-20240229

    Configure via ``ModelConfig.api_key`` (or set ``ANTHROPIC_API_KEY`` in
    the environment).
    """

    def __init__(self, config: ModelConfig) -> None:
        """Initialize Claude vision model.

        Args:
            config: Model configuration.

        Raises:
            ImportError: If the ``anthropic`` package is not installed.
            ValueError: If model type is not VISION or VIDEO.
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "The 'anthropic' package is not installed. "
                "Install it with: pip install 'local-file-organizer[claude]'"
            )

        if config.model_type not in (ModelType.VISION, ModelType.VIDEO):
            raise ValueError(f"Expected VISION or VIDEO model type, got {config.model_type}")

        super().__init__(config)
        self.client: Any | None = None  # anthropic.Anthropic; typed as Any to avoid stubs

    def initialize(self) -> None:
        """Create the Anthropic client."""
        if self._initialized:
            logger.debug("Claude vision model {} already initialized", self.config.name)
            return

        self.client = create_claude_client(self.config, "vision")
        super().initialize()

    def generate(
        self,
        prompt: str,
        image_path: str | Path | None = None,
        image_data: bytes | None = None,
        **kwargs: Any,
    ) -> str:
        """Analyse an image using the Anthropic Claude Messages API.

        Args:
            prompt: Text prompt describing what to analyse.
            image_path: Path to image file (mutually exclusive with
                ``image_data``).
            image_data: Raw image bytes (mutually exclusive with
                ``image_path``).
            **kwargs: Override config values:
                - ``temperature`` (float)
                - ``max_tokens`` (int)

        Returns:
            Generated text description, stripped of whitespace.

        Raises:
            RuntimeError: If the model is not initialised.
            ValueError: If neither or both of ``image_path`` / ``image_data``
                are provided.
            TokenExhaustionError: If the model exhausts its token budget on
                both the initial attempt and the retry.
            FileNotFoundError: If ``image_path`` does not exist.
            OSError: If ``image_path`` cannot be read.
        """
        self._enter_generate()
        try:
            return self._do_generate(prompt, image_path, image_data, **kwargs)
        finally:
            self._exit_generate()

    def _do_generate(
        self,
        prompt: str,
        image_path: str | Path | None = None,
        image_data: bytes | None = None,
        **kwargs: Any,
    ) -> str:
        """Internal generate logic, called while generation guard is held."""
        if self.client is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        if (image_path is None and image_data is None) or (
            image_path is not None and image_data is not None
        ):
            raise ValueError("Provide exactly one of image_path or image_data")

        temperature = float(kwargs.get("temperature", self.config.temperature))
        max_tokens = int(kwargs.get("max_tokens", self.config.max_tokens))

        # Build a base64 data URL then convert it to a Claude image block.
        # EAFP: let image_to_data_url raise FileNotFoundError / OSError directly
        # rather than checking existence first (avoids TOCTOU race).
        if image_path is not None:
            data_url = image_to_data_url(Path(image_path))
        else:
            if image_data is None:
                raise ValueError("image_data is None after guard check; this is a caller bug")
            data_url = bytes_to_data_url(image_data)

        image_block = _build_image_block(data_url)
        text_block: dict[str, Any] = {"type": "text", "text": prompt}

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [image_block, text_block],
            }
        ]

        try:
            logger.debug("Analysing image with Claude model {}", self.config.name)
            response = self.client.messages.create(
                model=self.config.name,
                max_tokens=max_tokens,
                messages=messages,
                temperature=temperature,
            )

            if is_claude_token_exhausted(response):
                retry_max = min(max_tokens * RETRY_MULTIPLIER, MAX_NUM_PREDICT)
                logger.warning(
                    "Token exhaustion detected for Claude vision model {}, "
                    "retrying with max_tokens={}",
                    self.config.name,
                    retry_max,
                )
                response = self.client.messages.create(
                    model=self.config.name,
                    max_tokens=retry_max,
                    messages=messages,
                    temperature=temperature,
                )
                if is_claude_token_exhausted(response):
                    raise TokenExhaustionError(
                        f"Claude vision model '{self.config.name}' exhausted token budget "
                        f"on retry (max_tokens={retry_max})"
                    )

            content = extract_claude_text(response)
            logger.debug("Generated {} characters", len(content))
            return content
        except (TokenExhaustionError, ValueError):
            raise
        except (RuntimeError, ConnectionError, OSError) as e:
            if ANTHROPIC_AVAILABLE:
                import anthropic

                if isinstance(e, anthropic.APIError):
                    logger.error(
                        "Claude API error ({}): {}",
                        type(e).__name__,
                        e,
                    )
                    raise
            logger.error("Failed to analyse image via Claude API: {}", type(e).__name__)
            raise

    def analyze_image(
        self,
        image_path: str | Path,
        task: str = "describe",
        **kwargs: Any,
    ) -> str:
        """Convenience wrapper matching the ``VisionModel`` interface.

        Args:
            image_path: Path to image file.
            task: Analysis task — ``'describe'``, ``'categorize'``,
                ``'ocr'``, or ``'filename'``.
            **kwargs: Forwarded to :meth:`generate`.

        Returns:
            Analysis result as text.
        """
        prompt = kwargs.pop("custom_prompt", None) or IMAGE_ANALYSIS_PROMPTS.get(
            task, IMAGE_ANALYSIS_PROMPTS["describe"]
        )
        return self.generate(prompt=prompt, image_path=image_path, **kwargs)

    def cleanup(self) -> None:
        """Release the Anthropic client.

        Calls ``client.close()`` (which closes the underlying ``httpx``
        connection pool) under the lifecycle lock.
        """
        logger.debug("Cleaning up Claude vision model {}", self.config.name)
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
        """Return a default ModelConfig for a Claude vision model.

        Args:
            model_name: Anthropic vision model identifier.

        Returns:
            A ``ModelConfig`` with ``provider="claude"`` and sensible defaults.
        """
        return ModelConfig(
            name=model_name,
            model_type=ModelType.VISION,
            provider="claude",
            temperature=0.3,
            max_tokens=3000,
        )
