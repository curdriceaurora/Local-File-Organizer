"""Tests for VisionModel class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.models.vision_model import VisionModel

pytestmark = pytest.mark.unit


@pytest.fixture
def vision_model_config() -> ModelConfig:
    return ModelConfig(
        name="qwen2.5vl:7b-q4_K_M",
        model_type=ModelType.VISION,
    )


def _make_initialized_model(config: ModelConfig) -> tuple[VisionModel, MagicMock]:
    """Helper to create an initialized VisionModel with mocked client."""
    with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
        model = VisionModel(config)
    mock_client = MagicMock()
    model.client = mock_client
    model._initialized = True
    return model, mock_client


@pytest.mark.unit
class TestVisionModel:
    """Tests for VisionModel basic initialization and generation."""

    def test_initialization(self, vision_model_config: ModelConfig) -> None:
        """Test VisionModel initialization."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)
            assert model.config == vision_model_config
            assert model.config.model_type == ModelType.VISION

    def test_generate_from_image(self, vision_model_config: ModelConfig) -> None:
        """Test text generation from image."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)

            mock_client = MagicMock()
            mock_client.generate.return_value = {
                "response": "Description of the image",
                "done": True,
                "total_duration": 1000000000,
            }

            with patch("ollama.Client", return_value=mock_client):
                # Mock Path.exists to return True
                with patch("pathlib.Path.exists", return_value=True):
                    model.initialize()
                    response = model.generate(
                        prompt="Describe this image", image_path="/path/to/image.jpg"
                    )

                    assert response == "Description of the image"
                    mock_client.generate.assert_called_once()
                    args, kwargs = mock_client.generate.call_args
                    assert kwargs["model"] == vision_model_config.name
                    assert kwargs["prompt"] == "Describe this image"
                    # Note: We check if images list contains the path string
                    assert str(kwargs["images"][0]) == "/path/to/image.jpg"

    def test_generate_from_image_error(self, vision_model_config: ModelConfig) -> None:
        """Test image generation error handling."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)

            mock_client = MagicMock()
            mock_client.generate.side_effect = Exception("Ollama error")

            with patch("ollama.Client", return_value=mock_client):
                with patch("pathlib.Path.exists", return_value=True):
                    model.initialize()
                    with pytest.raises(Exception) as excinfo:
                        model.generate(
                            prompt="Describe this image", image_path="/path/to/image.jpg"
                        )

                    assert "Failed to analyze image" in str(excinfo.value) or "Ollama error" in str(
                        excinfo.value
                    )


@pytest.mark.unit
class TestVisionModelInit:
    """Tests for VisionModel constructor validation."""

    def test_init_missing_ollama(self, vision_model_config: ModelConfig) -> None:
        """Test initialization fails when Ollama is unavailable."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", False):
            with pytest.raises(ImportError, match="Ollama is not installed"):
                VisionModel(vision_model_config)

    def test_init_wrong_model_type(self) -> None:
        """Test initialization fails with non-VISION/VIDEO model type."""
        config = ModelConfig(name="text-model", model_type=ModelType.TEXT)
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            with pytest.raises(ValueError, match="Expected VISION or VIDEO"):
                VisionModel(config)

    def test_init_video_model_type_accepted(self) -> None:
        """Test VIDEO model type is accepted."""
        config = ModelConfig(name="video-model", model_type=ModelType.VIDEO)
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(config)
            assert model.config.model_type == ModelType.VIDEO


@pytest.mark.unit
class TestVisionModelInitialize:
    """Tests for VisionModel.initialize() method."""

    @patch("file_organizer.models.vision_model.ollama.Client")
    def test_initialize_pulls_model_if_missing(
        self, mock_client_cls: MagicMock, vision_model_config: ModelConfig
    ) -> None:
        """Test model is pulled when not found locally."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            import ollama

            model = VisionModel(vision_model_config)
            mock_client = MagicMock()
            mock_client.show.side_effect = ollama.ResponseError("model not found")
            mock_client_cls.return_value = mock_client

            model.initialize()

            mock_client.show.assert_called_once_with(vision_model_config.name)
            mock_client.pull.assert_called_once_with(vision_model_config.name)
            assert model._initialized is True

    @patch("file_organizer.models.vision_model.ollama.Client")
    def test_initialize_already_initialized(
        self, mock_client_cls: MagicMock, vision_model_config: ModelConfig
    ) -> None:
        """Test initialize is a no-op when already initialized."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)
            model._initialized = True

            model.initialize()

            mock_client_cls.assert_not_called()

    @patch("file_organizer.models.vision_model.ollama.Client")
    def test_initialize_error_propagates(
        self, mock_client_cls: MagicMock, vision_model_config: ModelConfig
    ) -> None:
        """Test initialization error propagates."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)
            mock_client_cls.side_effect = Exception("connection refused")

            with pytest.raises(Exception, match="connection refused"):
                model.initialize()


@pytest.mark.unit
class TestVisionModelGenerate:
    """Tests for VisionModel.generate() edge cases."""

    def test_generate_uninitialized(self, vision_model_config: ModelConfig) -> None:
        """Test generate raises when not initialized."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)
            with pytest.raises(RuntimeError, match="Model not initialized"):
                model.generate("test", image_path="/path/to/img.jpg")

    def test_generate_no_image_provided(self, vision_model_config: ModelConfig) -> None:
        """Test generate raises when no image source is provided."""
        model, _ = _make_initialized_model(vision_model_config)
        with pytest.raises(ValueError, match="Provide exactly one"):
            model.generate("describe")

    def test_generate_both_image_args(self, vision_model_config: ModelConfig) -> None:
        """Test generate raises when both image_path and image_data are provided."""
        model, _ = _make_initialized_model(vision_model_config)
        with pytest.raises(ValueError, match="Provide exactly one"):
            model.generate("describe", image_path="/path/img.jpg", image_data=b"data")

    def test_generate_file_not_found(self, vision_model_config: ModelConfig) -> None:
        """Test generate raises FileNotFoundError for missing image."""
        model, _ = _make_initialized_model(vision_model_config)
        with patch("pathlib.Path.exists", return_value=False):
            with pytest.raises(FileNotFoundError, match="Image not found"):
                model.generate("describe", image_path="/nonexistent/img.jpg")

    def test_generate_with_image_data(self, vision_model_config: ModelConfig) -> None:
        """Test generate works with image_data bytes."""
        model, mock_client = _make_initialized_model(vision_model_config)
        mock_client.generate.return_value = {
            "response": "  bytes image description  ",
            "total_duration": 500000000,
        }

        result = model.generate("describe", image_data=b"\x89PNG\r\n")

        assert result == "bytes image description"
        call_kwargs = mock_client.generate.call_args[1]
        assert call_kwargs["images"] == [b"\x89PNG\r\n"]


@pytest.mark.unit
class TestVisionModelAnalyze:
    """Tests for analyze_image and analyze_video_frame convenience methods."""

    def test_analyze_image_describe(self, vision_model_config: ModelConfig) -> None:
        """Test analyze_image with 'describe' task."""
        model, mock_client = _make_initialized_model(vision_model_config)
        mock_client.generate.return_value = {
            "response": "A landscape",
            "total_duration": 100,
        }

        with patch("pathlib.Path.exists", return_value=True):
            result = model.analyze_image("/img.jpg", task="describe")

        assert result == "A landscape"
        prompt = mock_client.generate.call_args[1]["prompt"]
        assert "detailed description" in prompt

    def test_analyze_image_categorize(self, vision_model_config: ModelConfig) -> None:
        """Test analyze_image with 'categorize' task."""
        model, mock_client = _make_initialized_model(vision_model_config)
        mock_client.generate.return_value = {"response": "nature", "total_duration": 100}

        with patch("pathlib.Path.exists", return_value=True):
            model.analyze_image("/img.jpg", task="categorize")

        prompt = mock_client.generate.call_args[1]["prompt"]
        assert "category" in prompt.lower()

    def test_analyze_image_custom_prompt(self, vision_model_config: ModelConfig) -> None:
        """Test analyze_image with custom prompt overrides default."""
        model, mock_client = _make_initialized_model(vision_model_config)
        mock_client.generate.return_value = {"response": "custom", "total_duration": 100}

        with patch("pathlib.Path.exists", return_value=True):
            model.analyze_image("/img.jpg", custom_prompt="my custom prompt")

        prompt = mock_client.generate.call_args[1]["prompt"]
        assert prompt == "my custom prompt"

    def test_analyze_video_frame_default_prompt(self, vision_model_config: ModelConfig) -> None:
        """Test analyze_video_frame uses default prompt."""
        model, mock_client = _make_initialized_model(vision_model_config)
        mock_client.generate.return_value = {"response": "frame desc", "total_duration": 100}

        with patch("pathlib.Path.exists", return_value=True):
            result = model.analyze_video_frame("/frame.jpg")

        assert result == "frame desc"
        prompt = mock_client.generate.call_args[1]["prompt"]
        assert "video frame" in prompt.lower()

    def test_analyze_video_frame_custom_prompt(self, vision_model_config: ModelConfig) -> None:
        """Test analyze_video_frame with custom prompt."""
        model, mock_client = _make_initialized_model(vision_model_config)
        mock_client.generate.return_value = {"response": "custom", "total_duration": 100}

        with patch("pathlib.Path.exists", return_value=True):
            model.analyze_video_frame("/frame.jpg", prompt="my prompt")

        prompt = mock_client.generate.call_args[1]["prompt"]
        assert prompt == "my prompt"


@pytest.mark.unit
class TestVisionModelMisc:
    """Tests for cleanup, get_default_config, and test_connection."""

    def test_cleanup(self, vision_model_config: ModelConfig) -> None:
        """Test cleanup resets client and initialized state."""
        model, _ = _make_initialized_model(vision_model_config)
        assert model._initialized is True
        assert model.client is not None

        model.cleanup()

        assert model.client is None
        assert model._initialized is False

    def test_get_default_config(self) -> None:
        """Test static default config method."""
        config = VisionModel.get_default_config()
        assert config.name == "qwen2.5vl:7b-q4_K_M"
        assert config.model_type == ModelType.VISION
        assert config.quantization == "q4_k_m"
        assert config.temperature == 0.3

    def test_get_default_config_custom_name(self) -> None:
        """Test static default config with custom model name."""
        config = VisionModel.get_default_config("my-vision-model")
        assert config.name == "my-vision-model"
        assert config.model_type == ModelType.VISION

    @patch("file_organizer.models.vision_model.ollama.Client")
    def test_test_connection_success(
        self, mock_client_cls: MagicMock, vision_model_config: ModelConfig
    ) -> None:
        """Test successful connection returns status dict."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)
            mock_client = MagicMock()
            mock_client.show.return_value = {"size": "6GB"}
            mock_client_cls.return_value = mock_client

            model.initialize()
            info = model.test_connection()

            assert info["status"] == "connected"
            assert info["name"] == vision_model_config.name
            assert info["size"] == "6GB"
            assert info["type"] == "vision-language"

    def test_test_connection_uninitialized(self, vision_model_config: ModelConfig) -> None:
        """Test connection check fails when not initialized."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)
            with pytest.raises(RuntimeError, match="Model not initialized"):
                model.test_connection()

    @patch("file_organizer.models.vision_model.ollama.Client")
    def test_test_connection_error(
        self, mock_client_cls: MagicMock, vision_model_config: ModelConfig
    ) -> None:
        """Test connection error returns error status dict."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)
            mock_client = MagicMock()
            # First show() call succeeds during init, second fails during test_connection
            mock_client.show.side_effect = [{"size": "6GB"}, Exception("connection lost")]
            mock_client_cls.return_value = mock_client

            model.initialize()
            info = model.test_connection()

            assert info["status"] == "error"
            assert "connection lost" in info["error"]
