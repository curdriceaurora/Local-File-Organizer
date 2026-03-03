"""Tests for model registry: ModelInfo dataclass and AVAILABLE_MODELS catalog."""

from __future__ import annotations

import pytest

from file_organizer.models.registry import AVAILABLE_MODELS, ModelInfo


@pytest.mark.unit
class TestModelInfo:
    """Tests for ModelInfo dataclass."""

    def test_create_model_info(self) -> None:
        """Test basic ModelInfo creation."""
        model = ModelInfo(
            name="qwen2.5:3b-instruct-q4_K_M",
            model_type="text",
            size="1.9 GB",
            quantization="q4_K_M",
            description="Fast text model",
        )

        assert model.name == "qwen2.5:3b-instruct-q4_K_M"
        assert model.model_type == "text"
        assert model.size == "1.9 GB"
        assert model.quantization == "q4_K_M"
        assert model.description == "Fast text model"
        assert model.installed is False

    def test_model_info_installed_true(self) -> None:
        """Test ModelInfo with installed=True."""
        model = ModelInfo(
            name="qwen2.5:3b-instruct-q4_K_M",
            model_type="text",
            size="1.9 GB",
            quantization="q4_K_M",
            description="Fast text model",
            installed=True,
        )
        assert model.installed is True

    def test_model_info_with_different_types(self) -> None:
        """Test ModelInfo with different model types."""
        text_model = ModelInfo(
            name="text-model",
            model_type="text",
            size="2 GB",
            quantization="q4",
            description="Text model",
        )
        vision_model = ModelInfo(
            name="vision-model",
            model_type="vision",
            size="6 GB",
            quantization="q4",
            description="Vision model",
        )
        audio_model = ModelInfo(
            name="audio-model",
            model_type="audio",
            size="0.5 GB",
            quantization="fp16",
            description="Audio model",
        )

        assert text_model.model_type == "text"
        assert vision_model.model_type == "vision"
        assert audio_model.model_type == "audio"

    def test_model_info_equality(self) -> None:
        """Test ModelInfo equality."""
        model1 = ModelInfo(
            name="test-model",
            model_type="text",
            size="1 GB",
            quantization="q4",
            description="Test",
        )
        model2 = ModelInfo(
            name="test-model",
            model_type="text",
            size="1 GB",
            quantization="q4",
            description="Test",
        )
        assert model1 == model2

    def test_model_info_inequality(self) -> None:
        """Test ModelInfo inequality."""
        model1 = ModelInfo(
            name="model1",
            model_type="text",
            size="1 GB",
            quantization="q4",
            description="Test",
        )
        model2 = ModelInfo(
            name="model2",
            model_type="text",
            size="1 GB",
            quantization="q4",
            description="Test",
        )
        assert model1 != model2


@pytest.mark.unit
class TestAvailableModels:
    """Tests for AVAILABLE_MODELS catalog."""

    def test_available_models_exists(self) -> None:
        """Test that AVAILABLE_MODELS is a list."""
        assert isinstance(AVAILABLE_MODELS, list)
        assert len(AVAILABLE_MODELS) > 0

    def test_available_models_count(self) -> None:
        """Test the number of available models."""
        assert len(AVAILABLE_MODELS) == 6

    def test_all_models_have_required_fields(self) -> None:
        """Test that all models have required fields."""
        for model in AVAILABLE_MODELS:
            assert hasattr(model, "name")
            assert hasattr(model, "model_type")
            assert hasattr(model, "size")
            assert hasattr(model, "quantization")
            assert hasattr(model, "description")
            assert model.name
            assert model.model_type
            assert model.size
            assert model.quantization
            assert model.description

    def test_text_models_present(self) -> None:
        """Test that text models are in the catalog."""
        text_models = [m for m in AVAILABLE_MODELS if m.model_type == "text"]
        assert len(text_models) >= 2
        assert any(m.name == "qwen2.5:3b-instruct-q4_K_M" for m in text_models)

    def test_vision_models_present(self) -> None:
        """Test that vision models are in the catalog."""
        vision_models = [m for m in AVAILABLE_MODELS if m.model_type == "vision"]
        assert len(vision_models) >= 2
        assert any(m.name == "qwen2.5vl:7b-q4_K_M" for m in vision_models)

    def test_audio_models_present(self) -> None:
        """Test that audio models are in the catalog."""
        audio_models = [m for m in AVAILABLE_MODELS if m.model_type == "audio"]
        assert len(audio_models) >= 2
        assert any(m.name == "whisper:base" for m in audio_models)

    def test_qwen_text_model_3b(self) -> None:
        """Test Qwen 2.5 3B text model details."""
        model = next(
            (m for m in AVAILABLE_MODELS if m.name == "qwen2.5:3b-instruct-q4_K_M"),
            None,
        )
        assert model is not None
        assert model.model_type == "text"
        assert model.size == "1.9 GB"
        assert model.quantization == "q4_K_M"
        assert model.installed is False

    def test_qwen_text_model_7b(self) -> None:
        """Test Qwen 2.5 7B text model details."""
        model = next(
            (m for m in AVAILABLE_MODELS if m.name == "qwen2.5:7b-instruct-q4_K_M"),
            None,
        )
        assert model is not None
        assert model.model_type == "text"
        assert model.size == "4.4 GB"
        assert model.quantization == "q4_K_M"

    def test_qwen_vision_model(self) -> None:
        """Test Qwen 2.5-VL vision model details."""
        model = next(
            (m for m in AVAILABLE_MODELS if m.name == "qwen2.5vl:7b-q4_K_M"),
            None,
        )
        assert model is not None
        assert model.model_type == "vision"
        assert model.size == "6.0 GB"
        assert model.quantization == "q4_K_M"

    def test_llava_vision_model(self) -> None:
        """Test LLaVA vision model details."""
        model = next(
            (m for m in AVAILABLE_MODELS if m.name == "llava:7b-v1.6-q4_K_M"),
            None,
        )
        assert model is not None
        assert model.model_type == "vision"
        assert model.size == "4.7 GB"

    def test_whisper_base_model(self) -> None:
        """Test Whisper base audio model details."""
        model = next(
            (m for m in AVAILABLE_MODELS if m.name == "whisper:base"),
            None,
        )
        assert model is not None
        assert model.model_type == "audio"
        assert model.size == "0.1 GB"
        assert model.quantization == "fp16"

    def test_whisper_small_model(self) -> None:
        """Test Whisper small audio model details."""
        model = next(
            (m for m in AVAILABLE_MODELS if m.name == "whisper:small"),
            None,
        )
        assert model is not None
        assert model.model_type == "audio"
        assert model.size == "0.5 GB"
        assert model.quantization == "fp16"

    def test_find_by_type(self) -> None:
        """Test finding models by type."""
        text_models = [m for m in AVAILABLE_MODELS if m.model_type == "text"]
        vision_models = [m for m in AVAILABLE_MODELS if m.model_type == "vision"]
        audio_models = [m for m in AVAILABLE_MODELS if m.model_type == "audio"]

        assert len(text_models) > 0
        assert len(vision_models) > 0
        assert len(audio_models) > 0

    def test_find_by_name(self) -> None:
        """Test finding a model by name."""
        model = next(
            (m for m in AVAILABLE_MODELS if m.name == "qwen2.5:3b-instruct-q4_K_M"),
            None,
        )
        assert model is not None

    def test_find_nonexistent_model(self) -> None:
        """Test finding a nonexistent model returns None."""
        model = next(
            (m for m in AVAILABLE_MODELS if m.name == "nonexistent-model"),
            None,
        )
        assert model is None

    def test_model_descriptions_not_empty(self) -> None:
        """Test that all model descriptions are meaningful."""
        for model in AVAILABLE_MODELS:
            assert len(model.description) > 5

    def test_model_sizes_format(self) -> None:
        """Test that all model sizes are in reasonable format."""
        for model in AVAILABLE_MODELS:
            # Check format like "1.9 GB", "0.1 GB", etc.
            assert "GB" in model.size or "MB" in model.size

    def test_unique_model_names(self) -> None:
        """Test that all model names are unique."""
        names = [m.name for m in AVAILABLE_MODELS]
        assert len(names) == len(set(names))

    def test_quantization_values(self) -> None:
        """Test that quantization values are valid."""
        valid_quantizations = {"q4_K_M", "fp16"}
        for model in AVAILABLE_MODELS:
            assert model.quantization in valid_quantizations

    def test_model_types_valid(self) -> None:
        """Test that model types are valid."""
        valid_types = {"text", "vision", "audio"}
        for model in AVAILABLE_MODELS:
            assert model.model_type in valid_types
