"""Text model implementation using Ollama."""

from typing import Any, Dict, Optional

try:
    import ollama
    OLLAMA_AVAILABLE = True
except ImportError:
    OLLAMA_AVAILABLE = False

from file_organizer.models.base import BaseModel, ModelConfig, ModelType
from loguru import logger


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
            raise ImportError(
                "Ollama is not installed. Install it with: pip install ollama"
            )

        if config.model_type != ModelType.TEXT:
            raise ValueError(f"Expected TEXT model type, got {config.model_type}")

        super().__init__(config)
        self.client: Optional[ollama.Client] = None

    def initialize(self) -> None:
        """Initialize the Ollama client and pull model if needed."""
        if self._initialized:
            logger.debug(f"Text model {self.config.name} already initialized")
            return

        logger.info(f"Initializing text model: {self.config.name}")

        try:
            # Initialize Ollama client
            self.client = ollama.Client()

            # Check if model exists locally, pull if not
            try:
                self.client.show(self.config.name)
                logger.debug(f"Model {self.config.name} found locally")
            except ollama.ResponseError:
                logger.info(f"Model {self.config.name} not found locally, pulling...")
                self.client.pull(self.config.name)
                logger.info(f"Model {self.config.name} pulled successfully")

            self._initialized = True
            logger.info(f"Text model {self.config.name} initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize text model: {e}")
            raise

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text response using Ollama.

        Args:
            prompt: Input prompt
            **kwargs: Additional generation parameters (overrides config)

        Returns:
            Generated text response

        Raises:
            RuntimeError: If model is not initialized
        """
        if not self._initialized or self.client is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        # Merge config with kwargs
        options = {
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_k": kwargs.get("top_k", self.config.top_k),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
        }

        # Add any extra params from config
        options.update(self.config.extra_params)

        try:
            logger.debug(f"Generating text with model {self.config.name}")
            response = self.client.generate(
                model=self.config.name,
                prompt=prompt,
                options=options,
                stream=False,
            )

            generated_text = response["response"]
            logger.debug(
                f"Generated {len(generated_text)} characters "
                f"in {response.get('total_duration', 0) / 1e9:.2f}s"
            )

            return generated_text.strip()

        except Exception as e:
            logger.error(f"Failed to generate text: {e}")
            raise

    def generate_streaming(self, prompt: str, **kwargs: Any):
        """Generate text response with streaming.

        Args:
            prompt: Input prompt
            **kwargs: Additional generation parameters

        Yields:
            Generated text chunks

        Raises:
            RuntimeError: If model is not initialized
        """
        if not self._initialized or self.client is None:
            raise RuntimeError("Model not initialized. Call initialize() first.")

        options = {
            "temperature": kwargs.get("temperature", self.config.temperature),
            "top_k": kwargs.get("top_k", self.config.top_k),
            "top_p": kwargs.get("top_p", self.config.top_p),
            "num_predict": kwargs.get("max_tokens", self.config.max_tokens),
        }
        options.update(self.config.extra_params)

        try:
            stream = self.client.generate(
                model=self.config.name,
                prompt=prompt,
                options=options,
                stream=True,
            )

            for chunk in stream:
                if "response" in chunk:
                    yield chunk["response"]

        except Exception as e:
            logger.error(f"Failed to generate streaming text: {e}")
            raise

    def cleanup(self) -> None:
        """Cleanup model resources."""
        logger.debug(f"Cleaning up text model {self.config.name}")
        self.client = None
        self._initialized = False

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

    def test_connection(self) -> Dict[str, Any]:
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
            logger.error(f"Failed to get model info: {e}")
            return {
                "name": self.config.name,
                "status": "error",
                "error": str(e),
            }
