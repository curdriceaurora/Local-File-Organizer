"""Integration tests for TextModel and VisionModel generation.

Covers: TextModel.generate() (normal, token exhaustion retry, retry also
exhausted → TokenExhaustionError), generate_streaming() / _GuardedIterator
close-on-abandon, VisionModel.generate() (image_path, image_data, mutual
exclusivity), VisionModel.analyze_image(), cleanup() / safe_cleanup()
lifecycle, get_default_config() static methods.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType, TokenExhaustionError
from file_organizer.models.text_model import TextModel, _GuardedIterator
from file_organizer.models.vision_model import VisionModel

pytestmark = [pytest.mark.integration]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_text_model() -> TextModel:
    """Return an initialised TextModel with a MagicMock Ollama client."""
    config = TextModel.get_default_config("test-model")
    with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
        model = TextModel(config)
    model._initialized = True
    model.client = MagicMock()
    return model


def _make_vision_model() -> VisionModel:
    """Return an initialised VisionModel with a MagicMock Ollama client."""
    config = VisionModel.get_default_config("test-vision-model")
    with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
        model = VisionModel(config)
    model._initialized = True
    model.client = MagicMock()
    return model


def _ok_response(text: str = "Generated text response") -> dict:
    """Ollama response dict that passes is_token_exhausted check."""
    return {"response": text, "done_reason": "stop", "total_duration": 1_000_000_000}


def _exhausted_response(text: str = "") -> dict:
    """Ollama response dict that triggers is_token_exhausted."""
    return {"response": text, "done_reason": "length", "total_duration": 1_000_000_000}


# ---------------------------------------------------------------------------
# TextModel.generate()
# ---------------------------------------------------------------------------


class TestTextModelGenerate:
    def test_generate_returns_stripped_text(self) -> None:
        model = _make_text_model()
        model.client.generate.return_value = _ok_response("  hello world  ")
        result = model.generate("Say hello")
        assert result == "hello world"

    def test_generate_calls_client_with_model_name(self) -> None:
        model = _make_text_model()
        model.client.generate.return_value = _ok_response("ok")
        model.generate("prompt")
        call_kwargs = model.client.generate.call_args
        assert (
            call_kwargs.kwargs["model"] == "test-model"
            or call_kwargs[1].get("model") == "test-model"
            or call_kwargs[0][0] == "test-model"
        )

    def test_generate_passes_temperature_from_config(self) -> None:
        model = _make_text_model()
        model.client.generate.return_value = _ok_response("ok")
        model.generate("prompt")
        options = model.client.generate.call_args[1].get("options") or {}
        assert options.get("temperature") == model.config.temperature

    def test_generate_kwargs_override_config(self) -> None:
        model = _make_text_model()
        model.client.generate.return_value = _ok_response("ok")
        model.generate("prompt", temperature=0.99)
        options = model.client.generate.call_args[1].get("options") or {}
        assert options.get("temperature") == pytest.approx(0.99)

    def test_generate_token_exhaustion_retries_once(self) -> None:
        model = _make_text_model()
        model.client.generate.side_effect = [
            _exhausted_response(),
            _ok_response("retry succeeded"),
        ]
        result = model.generate("prompt")
        assert result == "retry succeeded"
        assert model.client.generate.call_count == 2

    def test_generate_retry_doubles_num_predict(self) -> None:
        model = _make_text_model()
        original_max_tokens = model.config.max_tokens
        model.client.generate.side_effect = [_exhausted_response(), _ok_response("ok")]
        model.generate("prompt")
        second_call_options = model.client.generate.call_args_list[1][1].get("options") or {}
        # Retry budget must be doubled (capped at 16384)
        expected = min(original_max_tokens * 2, 16384)
        assert second_call_options.get("num_predict") == expected

    def test_generate_raises_token_exhaustion_on_double_exhaustion(self) -> None:
        model = _make_text_model()
        model.client.generate.return_value = _exhausted_response()
        with pytest.raises(TokenExhaustionError):
            model.generate("prompt")
        assert model.client.generate.call_count == 2

    def test_generate_not_initialized_raises_runtime_error(self) -> None:
        model = _make_text_model()
        model.client = None
        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("prompt")

    def test_generate_propagates_client_exceptions(self) -> None:
        model = _make_text_model()
        model.client.generate.side_effect = ConnectionError("Ollama down")
        with pytest.raises(ConnectionError):
            model.generate("prompt")


# ---------------------------------------------------------------------------
# TextModel.generate_streaming() / _GuardedIterator
# ---------------------------------------------------------------------------


class TestTextModelStreaming:
    def test_generate_streaming_yields_chunks(self) -> None:
        model = _make_text_model()
        model.client.generate.return_value = iter(
            [
                {"response": "hello"},
                {"response": " world"},
                {"done_reason": "stop"},
            ]
        )
        chunks = list(model.generate_streaming("prompt"))
        assert chunks == ["hello", " world"]

    def test_generate_streaming_returns_guarded_iterator(self) -> None:
        model = _make_text_model()
        model.client.generate.return_value = iter([])
        it = model.generate_streaming("prompt")
        assert isinstance(it, _GuardedIterator)

    def test_guarded_iterator_close_releases_guard(self) -> None:
        on_close = MagicMock()
        inner = iter(["a", "b"])
        it = _GuardedIterator(inner, on_close)
        next(it)
        it.close()
        on_close.assert_called_once()

    def test_guarded_iterator_close_idempotent(self) -> None:
        on_close = MagicMock()
        it = _GuardedIterator(iter([]), on_close)
        it.close()
        it.close()
        assert on_close.call_count == 1

    def test_guarded_iterator_stopiteration_fires_callback(self) -> None:
        on_close = MagicMock()
        it = _GuardedIterator(iter(["x"]), on_close)
        with pytest.raises(StopIteration):
            next(it)
            next(it)
        on_close.assert_called()


# ---------------------------------------------------------------------------
# TextModel lifecycle
# ---------------------------------------------------------------------------


class TestTextModelLifecycle:
    def test_cleanup_sets_client_none(self) -> None:
        model = _make_text_model()
        model.cleanup()
        assert model.client is None

    def test_cleanup_clears_initialized_flag(self) -> None:
        model = _make_text_model()
        model.cleanup()
        assert model._initialized is False

    def test_safe_cleanup_does_not_raise(self) -> None:
        model = _make_text_model()
        model.safe_cleanup()

    def test_get_default_config_returns_text_type(self) -> None:
        config = TextModel.get_default_config()
        assert config.model_type == ModelType.TEXT

    def test_get_default_config_custom_model_name(self) -> None:
        config = TextModel.get_default_config("llama3:8b")
        assert config.name == "llama3:8b"

    def test_wrong_model_type_raises_value_error(self) -> None:
        config = ModelConfig(name="test", model_type=ModelType.VISION)
        with (
            patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True),
            pytest.raises(ValueError, match="TEXT"),
        ):
            TextModel(config)

    def test_ollama_not_available_raises_import_error(self) -> None:
        config = TextModel.get_default_config()
        with (
            patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", False),
            pytest.raises(ImportError),
        ):
            TextModel(config)


# ---------------------------------------------------------------------------
# VisionModel.generate()
# ---------------------------------------------------------------------------


class TestVisionModelGenerate:
    def test_generate_with_image_path(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 10)
        model.client.generate.return_value = _ok_response("A photo of a cat")
        result = model.generate("Describe this image", image_path=img)
        assert result == "A photo of a cat"
        call_kwargs = model.client.generate.call_args[1]
        assert call_kwargs["images"] == [str(img)]

    def test_generate_with_image_data(self) -> None:
        model = _make_vision_model()
        data = b"\xff\xd8\xff" + b"\x00" * 20
        model.client.generate.return_value = _ok_response("Some image")
        result = model.generate("Describe", image_data=data)
        assert result == "Some image"

    def test_generate_raises_if_neither_provided(self) -> None:
        model = _make_vision_model()
        with pytest.raises(ValueError, match="exactly one"):
            model.generate("Describe")

    def test_generate_raises_if_both_provided(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "img.jpg"
        img.write_bytes(b"data")
        with pytest.raises(ValueError, match="exactly one"):
            model.generate("Describe", image_path=img, image_data=b"bytes")

    def test_generate_raises_if_image_path_missing(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        with pytest.raises(FileNotFoundError):
            model.generate("Describe", image_path=tmp_path / "nonexistent.jpg")

    def test_generate_token_exhaustion_retries(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
        model.client.generate.side_effect = [
            _exhausted_response(),
            _ok_response("retried result"),
        ]
        result = model.generate("Describe", image_path=img)
        assert result == "retried result"
        assert model.client.generate.call_count == 2

    def test_generate_raises_token_exhaustion_on_double_failure(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
        model.client.generate.return_value = _exhausted_response()
        with pytest.raises(TokenExhaustionError):
            model.generate("Describe", image_path=img)

    def test_generate_raises_value_error_on_empty_response(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
        model.client.generate.return_value = {"response": "", "done_reason": "stop"}
        with pytest.raises(ValueError, match="empty response"):
            model.generate("Describe", image_path=img)


# ---------------------------------------------------------------------------
# VisionModel.analyze_image()
# ---------------------------------------------------------------------------


class TestVisionModelAnalyzeImage:
    def test_analyze_image_describe_task(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
        model.client.generate.return_value = _ok_response("A beautiful landscape")
        result = model.analyze_image(img, task="describe")
        assert result == "A beautiful landscape"

    def test_analyze_image_categorize_task(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
        model.client.generate.return_value = _ok_response("Nature")
        result = model.analyze_image(img, task="categorize")
        assert result == "Nature"

    def test_analyze_image_custom_prompt_overrides_task(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
        model.client.generate.return_value = _ok_response("Custom result")
        model.analyze_image(img, task="describe", custom_prompt="My custom prompt")
        call_kwargs = model.client.generate.call_args[1]
        assert call_kwargs["prompt"] == "My custom prompt"

    def test_analyze_image_unknown_task_falls_back_to_describe(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "photo.jpg"
        img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)
        model.client.generate.return_value = _ok_response("Described")
        result = model.analyze_image(img, task="unknown_task_xyz")
        assert result == "Described"


# ---------------------------------------------------------------------------
# VisionModel lifecycle
# ---------------------------------------------------------------------------


class TestVisionModelLifecycle:
    def test_cleanup_sets_client_none(self) -> None:
        model = _make_vision_model()
        model.cleanup()
        assert model.client is None

    def test_cleanup_clears_initialized_flag(self) -> None:
        model = _make_vision_model()
        model.cleanup()
        assert model._initialized is False

    def test_get_default_config_returns_vision_type(self) -> None:
        config = VisionModel.get_default_config()
        assert config.model_type == ModelType.VISION

    def test_get_default_config_custom_model_name(self) -> None:
        config = VisionModel.get_default_config("llava:7b")
        assert config.name == "llava:7b"

    def test_wrong_model_type_raises_value_error(self) -> None:
        config = ModelConfig(name="test", model_type=ModelType.TEXT)
        with (
            patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True),
            pytest.raises(ValueError, match="VISION or VIDEO"),
        ):
            VisionModel(config)

    def test_ollama_not_available_raises_import_error(self) -> None:
        config = VisionModel.get_default_config()
        with (
            patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", False),
            pytest.raises(ImportError),
        ):
            VisionModel(config)
