"""Tests for TextModel class."""

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
        # Mock OLLAMA_AVAILABLE to True for this test
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(text_model_config)
            assert model.config == text_model_config
            assert model.config.model_type == ModelType.TEXT

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
