"""Tests for TextModel class.

Covers initialization, generation, streaming, cleanup, error handling,
and configuration edge cases.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.models.text_model import TextModel


@pytest.fixture
def text_model_config():
    return ModelConfig(
        name="qwen2.5:3b-instruct-q4_K_M",
        model_type=ModelType.TEXT,
    )


class TestTextModel:
    """Tests for TextModel class."""

    def test_initialization(self, text_model_config):
        """Test TextModel initialization."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            assert model.config == text_model_config
            assert model.config.model_type == ModelType.TEXT

    def test_wrong_model_type_raises(self):
        """Test that non-TEXT model type raises ValueError."""
        config = ModelConfig(name="vision-model", model_type=ModelType.VISION)
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            with pytest.raises(ValueError, match="Expected TEXT"):
                TextModel(config)

    def test_ollama_unavailable_raises(self, text_model_config):
        """Test that missing Ollama raises ImportError."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", False):
            with pytest.raises(ImportError):
                TextModel(text_model_config)

    def test_generate_text(self, text_model_config):
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

    def test_generate_not_initialized_raises(self, text_model_config):
        """Test that generate raises if model not initialized."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            with pytest.raises(RuntimeError, match="not initialized"):
                model.generate("test prompt")

    def test_generate_text_error(self, text_model_config):
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

    def test_generate_strips_whitespace(self, text_model_config):
        """Test that generate strips whitespace from response."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            mock_client = MagicMock()
            mock_client.generate.return_value = {
                "response": "  trimmed response  \n",
                "total_duration": 100,
            }
            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                result = model.generate("test")
                assert result == "trimmed response"

    def test_generate_custom_kwargs(self, text_model_config):
        """Test that custom kwargs override config values."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            mock_client = MagicMock()
            mock_client.generate.return_value = {
                "response": "result",
                "total_duration": 100,
            }
            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                model.generate("test", temperature=0.9, max_tokens=500)
                _, kwargs = mock_client.generate.call_args
                assert kwargs["options"]["temperature"] == 0.9
                assert kwargs["options"]["num_predict"] == 500


class TestTextModelStreaming:
    """Tests for TextModel.generate_streaming."""

    def test_streaming_yields_chunks(self, text_model_config):
        """Test that streaming yields response chunks."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            mock_client = MagicMock()
            mock_client.generate.return_value = iter(
                [{"response": "Hello "}, {"response": "World"}]
            )
            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                chunks = list(model.generate_streaming("test"))
                assert chunks == ["Hello ", "World"]

    def test_streaming_not_initialized_raises(self, text_model_config):
        """Test that streaming raises if not initialized."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            with pytest.raises(RuntimeError, match="not initialized"):
                list(model.generate_streaming("test"))

    def test_streaming_error(self, text_model_config):
        """Test streaming error propagation."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            mock_client = MagicMock()
            mock_client.generate.side_effect = Exception("Stream error")
            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                with pytest.raises(Exception):
                    list(model.generate_streaming("test"))


class TestTextModelCleanup:
    """Tests for TextModel.cleanup."""

    def test_cleanup_resets_state(self, text_model_config):
        """Test that cleanup resets client and initialization state."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            mock_client = MagicMock()
            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                assert model._initialized is True
                assert model.client is not None

                model.cleanup()
                assert model._initialized is False
                assert model.client is None

    def test_cleanup_allows_reinitialize(self, text_model_config):
        """Test that model can be re-initialized after cleanup."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            mock_client = MagicMock()
            mock_client.generate.return_value = {
                "response": "ok",
                "total_duration": 100,
            }
            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                model.cleanup()
                model.initialize()
                result = model.generate("test")
                assert result == "ok"


class TestTextModelConfig:
    """Tests for TextModel configuration."""

    def test_get_default_config(self):
        """Test default config has expected values."""
        config = TextModel.get_default_config()
        assert config.model_type == ModelType.TEXT
        assert config.framework == "ollama"
        assert config.temperature == 0.5

    def test_get_default_config_custom_name(self):
        """Test default config with custom model name."""
        config = TextModel.get_default_config("custom:model")
        assert config.name == "custom:model"
        assert config.model_type == ModelType.TEXT

    def test_test_connection(self, text_model_config):
        """Test connection test returns model info."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            mock_client = MagicMock()
            mock_client.show.return_value = {"size": "1.9 GB"}
            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                info = model.test_connection()
                assert info["status"] == "connected"
                assert info["name"] == text_model_config.name

    def test_test_connection_not_initialized(self, text_model_config):
        """Test connection test raises when not initialized."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            with pytest.raises(RuntimeError, match="not initialized"):
                model.test_connection()

    def test_test_connection_error(self, text_model_config):
        """Test connection test handles errors gracefully."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            mock_client = MagicMock()
            # show() succeeds during initialize, but fails during test_connection
            mock_client.show.side_effect = [
                {"name": "test"},  # initialize call
                Exception("Connection refused"),  # test_connection call
            ]
            with patch("ollama.Client", return_value=mock_client):
                model.initialize()
                info = model.test_connection()
                assert info["status"] == "error"

    def test_already_initialized_skips(self, text_model_config):
        """Test that calling initialize twice doesn't re-create client."""
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            mock_client = MagicMock()
            with patch("ollama.Client", return_value=mock_client) as mock_cls:
                model.initialize()
                model.initialize()  # second call should be a no-op
                assert mock_cls.call_count == 1
