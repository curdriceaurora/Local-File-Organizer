"""Tests for VisionModel class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType
from file_organizer.models.vision_model import VisionModel


@pytest.fixture
def vision_model_config():
    return ModelConfig(
        name="qwen2.5vl:7b-q4_K_M",
        model_type=ModelType.VISION,
    )


class TestVisionModel:
    """Tests for VisionModel class."""

    def test_initialization(self, vision_model_config):
        """Test VisionModel initialization."""
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(vision_model_config)
            assert model.config == vision_model_config
            assert model.config.model_type == ModelType.VISION

    def test_generate_from_image(self, vision_model_config):
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

    def test_generate_from_image_error(self, vision_model_config):
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
