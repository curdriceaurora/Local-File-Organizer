"""Vision model implementation using OpenAI-compatible API."""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from loguru import logger

from file_organizer.models._openai_client import OPENAI_AVAILABLE, create_openai_client
from file_organizer.models._openai_response import is_openai_token_exhausted
from file_organizer.models.base import (
    IMAGE_ANALYSIS_PROMPTS,
    MAX_NUM_PREDICT,
    RETRY_MULTIPLIER,
    BaseModel,
    ModelConfig,
    ModelType,
    TokenExhaustionError,
)

# Ensure .webp is registered — it is absent from the Windows MIME registry
mimetypes.add_type("image/webp", ".webp")

# Fallback MIME type when extension is not recognised
_DEFAULT_IMAGE_MIME = "image/jpeg"


def _image_to_data_url(image_path: Path) -> str:
    """Encode an image file as a base64 data URL.

    Args:
        image_path: Path to the image file.

    Returns:
        Data URL string suitable for the OpenAI vision messages API.

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: If the file cannot be read.
    """
    mime_type, _ = mimetypes.guess_type(str(image_path))
    if not mime_type:
        mime_type = _DEFAULT_IMAGE_MIME
    with open(image_path, "rb") as fh:
        encoded = base64.b64encode(fh.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _bytes_to_data_url(image_data: bytes, mime_type: str = _DEFAULT_IMAGE_MIME) -> str:
    """Encode raw image bytes as a base64 data URL.

    Args:
        image_data: Raw image bytes.
        mime_type: MIME type of the image data.

    Returns:
        Data URL string.
    """
    encoded = base64.b64encode(image_data).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


class OpenAIVisionModel(BaseModel):
    """Vision-language model using an OpenAI-compatible API.

    Works with any provider that supports vision in the OpenAI chat format:
    - OpenAI GPT-4o / GPT-4-vision (https://api.openai.com/v1)
    - LM Studio with a vision-capable model (http://localhost:1234/v1)
    - Groq (https://api.groq.com/openai/v1)

    Configure via ``ModelConfig.api_key`` and ``ModelConfig.api_base_url``.
    """

    def __init__(self, config: ModelConfig) -> None:
        """Initialize OpenAI vision model.

        Args:
            config: Model configuration. ``config.api_key`` and
                ``config.api_base_url`` are used for authentication and
                endpoint routing.

        Raises:
            ImportError: If the ``openai`` package is not installed.
            ValueError: If model type is not VISION or VIDEO.
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "The 'openai' package is not installed. "
                "Install it with: pip install 'local-file-organizer[cloud]'"
            )

        if config.model_type not in (ModelType.VISION, ModelType.VIDEO):
            raise ValueError(f"Expected VISION or VIDEO model type, got {config.model_type}")

        super().__init__(config)
        self.client: Any | None = None  # openai.OpenAI; typed as Any to satisfy mypy without stub

    def initialize(self) -> None:
        """Create the OpenAI client.

        The client validates connectivity lazily on the first API call.
        """
        if self._initialized:
            logger.debug("OpenAI vision model {} already initialized", self.config.name)
            return

        self.client = create_openai_client(self.config, "vision")
        super().initialize()

    def generate(
        self,
        prompt: str,
        image_path: str | Path | None = None,
        image_data: bytes | None = None,
        **kwargs: Any,
    ) -> str:
        """Analyse an image using the OpenAI vision chat completions API.

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

        # Build image URL for the message payload.
        # EAFP: let _image_to_data_url raise FileNotFoundError / OSError directly
        # rather than checking existence first (avoids TOCTOU race).
        if image_path is not None:
            image_url = _image_to_data_url(Path(image_path))
        else:
            if image_data is None:
                raise ValueError("image_data is None after guard check; this is a caller bug")
            image_url = _bytes_to_data_url(image_data)

        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        try:
            logger.debug("Analysing image with OpenAI model {}", self.config.name)
            response = self.client.chat.completions.create(
                model=self.config.name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )

            if is_openai_token_exhausted(response):
                retry_max = min(max_tokens * RETRY_MULTIPLIER, MAX_NUM_PREDICT)
                logger.warning(
                    "Token exhaustion detected for OpenAI vision model {}, "
                    "retrying with max_tokens={}",
                    self.config.name,
                    retry_max,
                )
                response = self.client.chat.completions.create(
                    model=self.config.name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=retry_max,
                )
                if is_openai_token_exhausted(response):
                    raise TokenExhaustionError(
                        f"OpenAI vision model '{self.config.name}' exhausted token budget "
                        f"on retry (max_tokens={retry_max})"
                    )

            if not response.choices:
                return ""
            content = response.choices[0].message.content or ""
            logger.debug("Generated {} characters", len(content))
            return content.strip()
        except (TokenExhaustionError, ValueError):
            raise
        except Exception as e:
            logger.error("Failed to analyse image via OpenAI API: {}", type(e).__name__)
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
        """Release the OpenAI client.

        Sets ``_initialized`` to *False* under the lifecycle lock so that
        concurrent ``generate()`` calls see a consistent state.
        """
        logger.debug("Cleaning up OpenAI vision model {}", self.config.name)
        with self._lifecycle_lock:
            if self.client is not None:
                try:
                    self.client.close()
                except Exception:
                    logger.opt(exception=True).debug(
                        "Ignoring exception during OpenAI client close"
                    )
            self.client = None
            self._initialized = False

    @staticmethod
    def get_default_config(model_name: str = "gpt-4o-mini") -> ModelConfig:
        """Return a default ModelConfig for an OpenAI vision model.

        Args:
            model_name: OpenAI (or compatible) vision model identifier.

        Returns:
            A ``ModelConfig`` with ``provider="openai"`` and sensible defaults.
        """
        return ModelConfig(
            name=model_name,
            model_type=ModelType.VISION,
            provider="openai",
            temperature=0.3,
            max_tokens=3000,
        )
