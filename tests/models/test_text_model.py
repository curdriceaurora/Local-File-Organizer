"""Tests for TextModel class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.models.text_model import TextModel

pytestmark = [pytest.mark.unit]


@pytest.fixture
def text_model_config() -> ModelConfig:
    return ModelConfig(
        name="qwen2.5:3b-instruct-q4_K_M",
        model_type=ModelType.TEXT,
    )


@pytest.mark.unit
class TestTextModel:
    """Tests for TextModel class."""

    def test_initialization(self, text_model_config: ModelConfig) -> None:
        """Test TextModel initialization."""
        # Mock OLLAMA_AVAILABLE to True for this test
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            assert model.config == text_model_config
            assert model.config.model_type == ModelType.TEXT

    def test_generate_text(self, text_model_config: ModelConfig) -> None:
        """Test text generation."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)

            mock_client = MagicMock()
            mock_client.generate.return_value = {
                "response": "Organized content",
                "done": True,
                "total_duration": 1000000000,
            }

            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                response = model.generate("Process this file")

                assert response == "Organized content"
                mock_client.generate.assert_called_once()
                args, kwargs = mock_client.generate.call_args
                assert kwargs["model"] == text_model_config.name
                assert kwargs["prompt"] == "Process this file"

    def test_generate_text_error(self, text_model_config: ModelConfig) -> None:
        """Test text generation error handling."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)

            mock_client = MagicMock()
            mock_client.generate.side_effect = Exception("Ollama error")

            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                with pytest.raises(Exception) as excinfo:
                    model.generate("Process this file")

                assert "Failed to generate text" in str(excinfo.value) or "Ollama error" in str(
                    excinfo.value
                )

    def test_init_missing_ollama(self, text_model_config: ModelConfig) -> None:
        """Test initialization fails when Ollama is unavailable."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", False):
            with pytest.raises(ImportError, match="Ollama is not installed"):
                TextModel(text_model_config)

    def test_init_wrong_model_type(self) -> None:
        """Test initialization fails when passing non-TEXT model type."""
        config = ModelConfig(name="vision-model", model_type=ModelType.VISION)
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            with pytest.raises(ValueError, match="Expected TEXT model type"):
                TextModel(config)

    @patch("file_organizer.models.text_model.ollama.Client")
    def test_initialize_pulls_model_if_missing(
        self, mock_client_cls: MagicMock, text_model_config: ModelConfig
    ) -> None:
        """Test TextModel pulls model if it's not found locally."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)

            mock_client = MagicMock()
            import ollama

            # Raise an error on show() to simulate missing model
            mock_client.show.side_effect = ollama.ResponseError("model not found")
            mock_client_cls.return_value = mock_client

            model.initialize()

            mock_client.show.assert_called_once_with(text_model_config.name)
            mock_client.pull.assert_called_once_with(text_model_config.name)
            assert model._initialized is True

    @patch("file_organizer.models.text_model.ollama.Client")
    def test_initialize_already_initialized(
        self, mock_client_cls: MagicMock, text_model_config: ModelConfig
    ) -> None:
        """Test initialize is a no-op if already initialized."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            model._initialized = True

            model.initialize()

            mock_client_cls.assert_not_called()

    @patch("file_organizer.models.text_model.ollama.Client")
    def test_initialize_error(
        self, mock_client_cls: MagicMock, text_model_config: ModelConfig
    ) -> None:
        """Test initialization propagating errors."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)

            mock_client_cls.side_effect = Exception("init error")

            with pytest.raises(Exception, match="init error"):
                model.initialize()

    def test_generate_uninitialized(self, text_model_config: ModelConfig) -> None:
        """Test generating before initializing raises error."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            with pytest.raises(RuntimeError, match="Model not initialized"):
                model.generate("test")

    def test_generate_streaming_success(self, text_model_config: ModelConfig) -> None:
        """Test text generation with streaming."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)

            mock_client = MagicMock()
            # Simulate streaming response
            mock_client.generate.return_value = [
                {"response": "Chunk 1", "done": False},
                {"response": " Chunk 2", "done": False},
                {"response": "", "done": True},
            ]

            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                chunks = list(model.generate_streaming("Stream this"))

                assert chunks == ["Chunk 1", " Chunk 2", ""]
                mock_client.generate.assert_called_once()
                args, kwargs = mock_client.generate.call_args
                assert kwargs["stream"] is True

    def test_generate_streaming_uninitialized(self, text_model_config: ModelConfig) -> None:
        """Test streaming generation before initialization raises error."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            with pytest.raises(RuntimeError, match="Model not initialized"):
                # Consuming the generator via list() surfaces the error on first iteration
                list(model.generate_streaming("test"))

    def test_cleanup(self, text_model_config: ModelConfig) -> None:
        """Test cleanup execution resets client and initialized state."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            model.client = MagicMock()
            model._initialized = True

            model.cleanup()

            assert model.client is None
            assert model.is_initialized is False

    @patch("file_organizer.models.text_model.ollama.Client")
    def test_test_connection_success(
        self, mock_client_cls: MagicMock, text_model_config: ModelConfig
    ) -> None:
        """Test connection status lookup succeeds."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)

            mock_client = MagicMock()
            mock_client.show.return_value = {"size": "3GB"}
            mock_client_cls.return_value = mock_client

            model.initialize()
            info = model.test_connection()

            assert info["status"] == "connected"
            assert info["name"] == text_model_config.name
            assert info["size"] == "3GB"
            assert info["quantization"] == text_model_config.quantization

    def test_test_connection_uninitialized(self, text_model_config: ModelConfig) -> None:
        """Test connection check fails when uninitialized."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            with pytest.raises(RuntimeError, match="Model not initialized"):
                model.test_connection()

    @patch("file_organizer.models.text_model.ollama.Client")
    def test_test_connection_error(
        self, mock_client_cls: MagicMock, text_model_config: ModelConfig
    ) -> None:
        """Test connection error handling."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)

            mock_client = MagicMock()
            # First call succeeds during initialize(), second fails during test_connection()
            mock_client.show.side_effect = [{"size": "3GB"}, Exception("connection lost")]
            mock_client_cls.return_value = mock_client

            model.initialize()
            info = model.test_connection()

            assert info["status"] == "error"
            assert "connection lost" in info["error"]

    def test_get_default_config(self) -> None:
        """Test retrieving the default configuration."""
        config = TextModel.get_default_config("custom-model")
        assert config.name == "custom-model"
        assert config.model_type == ModelType.TEXT
        assert config.quantization == "q4_k_m"
