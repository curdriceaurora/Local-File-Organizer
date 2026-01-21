"""Base model interface for all AI models."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class ModelType(Enum):
    """Types of AI models supported."""
    TEXT = "text"
    VISION = "vision"
    AUDIO = "audio"
    VIDEO = "video"


class DeviceType(Enum):
    """Types of devices for inference."""
    AUTO = "auto"
    CPU = "cpu"
    CUDA = "cuda"
    MPS = "mps"  # Apple Silicon
    METAL = "metal"  # Apple Silicon (MLX)


@dataclass
class ModelConfig:
    """Configuration for AI models."""

    name: str
    model_type: ModelType
    quantization: str = "q4_k_m"
    device: DeviceType = DeviceType.AUTO
    temperature: float = 0.5
    max_tokens: int = 3000
    top_k: int = 3
    top_p: float = 0.3
    context_window: int = 4096
    batch_size: int = 1

    # Framework specific
    framework: str = "ollama"  # ollama, llama_cpp, mlx

    # Model paths
    model_path: Optional[str] = None
    local_path: Optional[str] = None

    # Additional parameters
    extra_params: Dict[str, Any] = None

    def __post_init__(self) -> None:
        """Initialize extra params if None."""
        if self.extra_params is None:
            self.extra_params = {}


class BaseModel(ABC):
    """Abstract base class for all AI models."""

    def __init__(self, config: ModelConfig):
        """Initialize the model with configuration.

        Args:
            config: Model configuration
        """
        self.config = config
        self.model: Optional[Any] = None
        self._initialized = False

    @abstractmethod
    def initialize(self) -> None:
        """Initialize the model. Must be called before inference."""
        pass

    @abstractmethod
    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate response from the model.

        Args:
            prompt: Input prompt
            **kwargs: Additional generation parameters

        Returns:
            Generated text response
        """
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Cleanup model resources."""
        pass

    @property
    def is_initialized(self) -> bool:
        """Check if model is initialized."""
        return self._initialized

    def __enter__(self) -> "BaseModel":
        """Context manager entry."""
        if not self._initialized:
            self.initialize()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.cleanup()

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"{self.__class__.__name__}("
            f"name={self.config.name}, "
            f"framework={self.config.framework}, "
            f"initialized={self._initialized})"
        )
