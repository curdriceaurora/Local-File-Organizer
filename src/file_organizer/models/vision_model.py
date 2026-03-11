"""Vision model implementation using Ollama for multimodal tasks."""

from __future__ import annotations

from pathlib import Path
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
    IMAGE_ANALYSIS_PROMPTS,
    BaseModel,
    ModelConfig,
    ModelType,
    TokenExhaustionError,
)


class VisionModel(BaseModel):
    """Vision-Language model using Ollama for multimodal tasks.

    This model wraps Ollama vision models for:
    - Image understanding and description
    - Video frame analysis
    - Visual content categorization
    - OCR and document understanding
    """

    def __init__(self, config: ModelConfig):
        """Initialize vision model.

        Args:
            config: Model configuration

        Raises:
            ImportError: If Ollama is not installed
            ValueError: If model type is not VISION or VIDEO
        """
        if not OLLAMA_AVAILABLE:
            raise ImportError("Ollama is not installed. Install it with: pip install ollama")

        if config.model_type not in (ModelType.VISION, ModelType.VIDEO):
            raise ValueError(f"Expected VISION or VIDEO model type, got {config.model_type}")

        super().__init__(config)
        self.client: ollama.Client | None = None

    def initialize(self) -> None:
        """Initialize the Ollama client and pull model if needed."""
        if self._initialized:
            logger.debug("Vision model {} already initialized", self.config.name)
            return

        logger.info("Initializing vision model: {}", self.config.name)

        try:
            # Initialize Ollama client
            self.client = ollama.Client()

            # Check if model exists locally, pull if not
            try:
                self.client.show(self.config.name)
                logger.debug("Model {} found locally", self.config.name)
            except ollama.ResponseError:
                logger.info("Model {} not found locally, pulling...", self.config.name)
                logger.warning("Downloading large vision model, this may take several minutes...")
                self.client.pull(self.config.name)
                logger.info("Model {} pulled successfully", self.config.name)

            super().initialize()
            logger.info("Vision model {} initialized successfully", self.config.name)

        except Exception as e:
            logger.error("Failed to initialize vision model: {}", e)
            raise

    def generate(
        self,
        prompt: str,
        image_path: str | Path | None = None,
        image_data: bytes | None = None,
        **kwargs: Any,
    ) -> str:
        """Generate description for an image using vision-language model.

        Args:
            prompt: Text prompt describing what to analyze
            image_path: Path to image file (mutually exclusive with image_data)
            image_data: Image data as bytes (mutually exclusive with image_path)
            **kwargs: Additional generation parameters

        Returns:
            Generated text description

        Raises:
            RuntimeError: If model is not initialized
            ValueError: If neither or both image_path and image_data are provided
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

        # Prepare image input
        if image_path is not None:
            image_path = Path(image_path)
            if not image_path.exists():
                raise FileNotFoundError(f"Image not found: {image_path}")
            images = [str(image_path)]
        else:
            # For bytes data, we'll need to save temporarily or use base64
            # Ollama expects file paths or URLs
            images = [image_data]  # type: ignore

        # Merge config with kwargs
        options = {
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_k": kwargs.get("top_k", self.config.top_k),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
        }
        if self.config.extra_params:
            options.update(self.config.extra_params)

        try:
            logger.debug("Analyzing image with model {}", self.config.name)
            response = self.client.generate(
                model=self.config.name,
                prompt=prompt,
                images=images,
                options=options,
                stream=False,
            )

            # Detect token exhaustion and retry once with doubled budget
            if is_token_exhausted(response):
                diag = format_exhaustion_diagnostics(response, self.config.name)
                logger.warning("Token exhaustion detected, retrying: {}", diag)

                retry_num_predict = compute_retry_num_predict(options["num_predict"])
                retry_options = {**options, "num_predict": retry_num_predict}

                response = self.client.generate(
                    model=self.config.name,
                    prompt=prompt,
                    images=images,
                    options=retry_options,
                    stream=False,
                )

                if is_token_exhausted(response):
                    retry_diag = format_exhaustion_diagnostics(response, self.config.name)
                    raise TokenExhaustionError(
                        f"Model exhausted token budget on retry. {retry_diag}"
                    )

            raw_response = response.get("response")
            if not raw_response:
                raise ValueError(f"Ollama returned empty response for model {self.config.name}")
            generated_text = str(raw_response)
            logger.debug(
                "Generated {} characters in {:.2f}s",
                len(generated_text),
                response.get("total_duration", 0) / 1e9,
            )

            return generated_text.strip()

        except (TokenExhaustionError, ValueError):
            raise
        except Exception as e:
            logger.error("Failed to analyze image: {}", e)
            raise

    def analyze_image(
        self,
        image_path: str | Path,
        task: str = "describe",
        **kwargs: Any,
    ) -> str:
        """Convenience method for common image analysis tasks.

        Args:
            image_path: Path to image file
            task: Type of analysis - 'describe', 'categorize', 'ocr'
            **kwargs: Additional parameters

        Returns:
            Analysis result as text
        """
        prompt = kwargs.pop("custom_prompt", None) or IMAGE_ANALYSIS_PROMPTS.get(
            task, IMAGE_ANALYSIS_PROMPTS["describe"]
        )

        return self.generate(prompt=prompt, image_path=image_path, **kwargs)

    def analyze_video_frame(
        self,
        frame_path: str | Path,
        prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Analyze a single video frame.

        Args:
            frame_path: Path to extracted video frame
            prompt: Optional custom prompt
            **kwargs: Additional parameters

        Returns:
            Frame analysis result
        """
        if prompt is None:
            prompt = (
                "Describe what is happening in this video frame. "
                "Focus on the main action, subjects, and scene."
            )

        return self.generate(prompt=prompt, image_path=frame_path, **kwargs)

    def cleanup(self) -> None:
        """Cleanup model resources.

        Sets ``_initialized`` to *False* under the lifecycle lock so that
        concurrent ``generate()`` calls see a consistent state.
        """
        logger.debug("Cleaning up vision model {}", self.config.name)
        with self._lifecycle_lock:
            self._initialized = False
            self.client = None

    @staticmethod
    def get_default_config(
        model_name: str = "qwen2.5vl:7b-q4_K_M",
    ) -> ModelConfig:
        """Get default configuration for vision model.

        Args:
            model_name: Name of the Ollama vision model

        Returns:
            Default model configuration
        """
        return ModelConfig(
            name=model_name,
            model_type=ModelType.VISION,
            quantization="q4_k_m",
            framework="ollama",
            temperature=0.3,
            max_tokens=3000,
            top_k=3,
            top_p=0.2,
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
                "type": "vision-language",
                "status": "connected",
            }
        except Exception as e:
            logger.error("Failed to get model info: {}", e)
            return {
                "name": self.config.name,
                "type": "vision-language",
                "status": "error",
                "error": str(e),
            }
