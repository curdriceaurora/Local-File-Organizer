"""Lazy model loader using the proxy pattern.

Defers model loading until the model is first accessed, reducing startup
time and memory usage for models that may not be needed.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

from file_organizer.models.base import BaseModel, ModelConfig

logger = logging.getLogger(__name__)


class LazyModelLoader:
    """Proxy that defers model loading until first access.

    Acts as a stand-in for a BaseModel instance. The actual model is only
    loaded when the ``model`` property is first accessed. This enables
    registration of many models at startup without paying the loading cost
    until each is actually needed.

    Args:
        model_config: Configuration for the model to load.
        loader: Optional callable that takes a ModelConfig and returns a
            BaseModel. If not provided, the model is instantiated based
            on the framework specified in the config.

    Example:
        >>> config = ModelConfig(name="qwen2.5:3b", model_type=ModelType.TEXT)
        >>> lazy = LazyModelLoader(config)
        >>> lazy.is_loaded  # False - not loaded yet
        False
        >>> model = lazy.model  # Loads the model now
        >>> lazy.is_loaded
        True
    """

    def __init__(
        self,
        model_config: ModelConfig,
        loader: Callable[[ModelConfig], BaseModel] | None = None,
    ) -> None:
        """Initialize the lazy loader.

        Args:
            model_config: Configuration for the model.
            loader: Optional callable(ModelConfig) -> BaseModel.
        """
        self._config = model_config
        self._loader = loader
        self._model: BaseModel | None = None
        self._lock = threading.Lock()

    @property
    def model(self) -> BaseModel:
        """Access the loaded model, loading it on first access.

        Thread-safe: only one thread will perform the actual loading.

        Returns:
            The loaded BaseModel instance.

        Raises:
            RuntimeError: If model loading fails.
        """
        if self._model is not None:
            return self._model

        with self._lock:
            # Double-checked locking
            if self._model is not None:
                return self._model

            logger.info(
                "Lazy loading model '%s' (framework: %s)",
                self._config.name,
                self._config.framework,
            )
            try:
                self._model = self._load_model()
                logger.info("Model '%s' loaded successfully", self._config.name)
            except Exception as exc:
                logger.error(
                    "Failed to load model '%s': %s",
                    self._config.name,
                    exc,
                    exc_info=True,
                )
                raise RuntimeError(f"Failed to load model '{self._config.name}': {exc}") from exc

        return self._model

    @property
    def is_loaded(self) -> bool:
        """Check if the model has been loaded.

        Returns:
            True if the model has been loaded into memory.
        """
        return self._model is not None

    @property
    def config(self) -> ModelConfig:
        """Get the model configuration.

        Returns:
            The ModelConfig for this loader.
        """
        return self._config

    def unload(self) -> None:
        """Unload the model and free resources.

        Calls cleanup() on the model if it was loaded, then releases the
        reference. The model can be re-loaded by accessing the ``model``
        property again.
        """
        with self._lock:
            if self._model is not None:
                logger.info("Unloading model '%s'", self._config.name)
                try:
                    self._model.cleanup()
                except Exception:
                    logger.warning(
                        "Error during cleanup of model '%s'",
                        self._config.name,
                        exc_info=True,
                    )
                self._model = None

    def _load_model(self) -> BaseModel:
        """Load the model using the configured loader or default factory.

        Returns:
            A loaded BaseModel instance.

        Raises:
            ValueError: If no loader is available for the framework.
        """
        if self._loader is not None:
            return self._loader(self._config)

        return self._default_loader(self._config)

    @staticmethod
    def _default_loader(config: ModelConfig) -> BaseModel:
        """Load a model using the default factory based on framework.

        Args:
            config: Model configuration.

        Returns:
            A loaded BaseModel instance.

        Raises:
            ValueError: If the framework is not supported.
        """
        framework = config.framework.lower()

        if framework == "ollama":
            from file_organizer.models.text_model import TextModel

            model = TextModel(config)
            model.initialize()
            return model

        if framework in ("openai", "llama_cpp"):
            from file_organizer.models.provider_factory import get_text_model

            model = get_text_model(config)
            model.initialize()
            return model

        raise ValueError(
            f"Unsupported framework '{framework}' for lazy loading. "
            f"Provide a custom loader callable."
        )

    def __repr__(self) -> str:
        """String representation."""
        status = "loaded" if self.is_loaded else "not loaded"
        return (
            f"LazyModelLoader("
            f"name={self._config.name!r}, "
            f"framework={self._config.framework!r}, "
            f"status={status})"
        )
