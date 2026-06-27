"""Integration tests for vision_model, text_model, config manager,
provider_registry, suggestion_types, path_manager, and analytics.

Targets ≥80% line coverage on:
  - src/models/vision_model.py      (was 68%)
  - src/config/manager.py           (was 69%)
  - src/models/provider_registry.py (was 71%)
  - src/models/suggestion_types.py  (was 71%)
  - src/models/text_model.py        (was 74%)
  - src/config/path_manager.py      (was 77%)
  - src/models/analytics.py         (was 79%)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

if TYPE_CHECKING:
    from file_organizer.models.analytics import AnalyticsDashboard, StorageStats
    from file_organizer.models.provider_registry import ProviderRegistry
    from file_organizer.models.text_model import TextModel
    from file_organizer.models.vision_model import VisionModel

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _ok_response(text: str = "Generated text") -> dict:
    return {"response": text, "done_reason": "stop", "total_duration": 1_000_000_000}


def _exhausted_response(text: str = "") -> dict:
    return {"response": text, "done_reason": "length", "total_duration": 1_000_000_000}


def _make_text_model() -> TextModel:
    from file_organizer.models.text_model import TextModel

    config = TextModel.get_default_config("test-text-model")
    with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
        model = TextModel(config)
    model._initialized = True
    model.client = MagicMock()
    return model


def _make_vision_model() -> VisionModel:
    from file_organizer.models.vision_model import VisionModel

    config = VisionModel.get_default_config("test-vision-model")
    with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
        model = VisionModel(config)
    model._initialized = True
    model.client = MagicMock()
    return model


# ===========================================================================
# TextModel
# ===========================================================================


class TestTextModelInit:
    def test_requires_ollama_available(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType
        from file_organizer.models.text_model import TextModel

        config = ModelConfig(name="m", model_type=ModelType.TEXT)
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", False):
            with pytest.raises(ImportError, match="Ollama is not installed"):
                TextModel(config)

    def test_rejects_wrong_model_type(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType
        from file_organizer.models.text_model import TextModel

        config = ModelConfig(name="m", model_type=ModelType.VISION)
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            with pytest.raises(ValueError, match="Expected TEXT"):
                TextModel(config)

    def test_get_default_config_returns_text_type(self) -> None:
        from file_organizer.models.base import ModelType
        from file_organizer.models.text_model import TextModel

        cfg = TextModel.get_default_config()
        assert cfg.model_type == ModelType.TEXT
        assert cfg.temperature == 0.5
        assert cfg.max_tokens == 3000

    def test_get_default_config_custom_name(self) -> None:
        from file_organizer.models.text_model import TextModel

        cfg = TextModel.get_default_config("my-custom-model")
        assert cfg.name == "my-custom-model"

    def test_initialize_skips_when_already_initialized(self) -> None:
        model = _make_text_model()
        model.initialize()  # already marked initialized; should return early
        model.client.show.assert_not_called()

    def test_initialize_pulls_when_show_raises_response_error(self) -> None:
        from file_organizer.models.text_model import TextModel

        config = TextModel.get_default_config("pull-me")
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(config)
        mock_client = MagicMock()

        class FakeResponseError(Exception):
            pass

        mock_client.show.side_effect = FakeResponseError("not found")
        with (
            patch("file_organizer.models.text_model.ollama.Client", return_value=mock_client),
            patch("file_organizer.models.text_model.ollama.ResponseError", FakeResponseError),
        ):
            model.initialize()

        mock_client.show.assert_called_once_with("pull-me")
        mock_client.pull.assert_called_once_with("pull-me")
        assert model._initialized is True

    def test_initialize_raises_on_connection_error(self) -> None:
        from file_organizer.models.text_model import TextModel

        config = TextModel.get_default_config("fail-model")
        with patch("file_organizer.models.text_model.OLLAMA_AVAILABLE", True):
            model = TextModel(config)

        with (
            patch(
                "file_organizer.models.text_model.ollama.Client",
                side_effect=ConnectionError("refused"),
            ),
            pytest.raises(ConnectionError),
        ):
            model.initialize()


class TestTextModelGenerate:
    def test_generate_returns_stripped_text(self) -> None:
        model = _make_text_model()
        model.client.generate.return_value = _ok_response("  hello world  ")
        result = model.generate("prompt")
        assert result == "hello world"

    def test_generate_raises_runtime_when_not_initialized(self) -> None:
        model = _make_text_model()
        model._initialized = False
        model.client = None
        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("prompt")

    def test_generate_retries_on_token_exhaustion(self) -> None:
        model = _make_text_model()
        model.client.generate.side_effect = [
            _exhausted_response(),
            _ok_response("retry success"),
        ]
        result = model.generate("prompt")
        assert result == "retry success"
        assert model.client.generate.call_count == 2

    def test_generate_raises_token_exhaustion_on_double_fail(self) -> None:
        from file_organizer.models.base import TokenExhaustionError

        model = _make_text_model()
        model.client.generate.side_effect = [
            _exhausted_response(),
            _exhausted_response(),
        ]
        with pytest.raises(TokenExhaustionError):
            model.generate("prompt")

    def test_generate_with_temperature_override(self) -> None:
        model = _make_text_model()
        model.client.generate.return_value = _ok_response("ok")
        model.generate("p", temperature=0.9)
        call_kwargs = model.client.generate.call_args
        options = call_kwargs[1].get("options") or call_kwargs[0][2]
        assert options["temperature"] == 0.9

    def test_cleanup_resets_state(self) -> None:
        model = _make_text_model()
        model.cleanup()
        assert model._initialized is False
        assert model.client is None

    def test_test_connection_not_initialized_raises(self) -> None:
        model = _make_text_model()
        model._initialized = False
        model.client = None
        with pytest.raises(RuntimeError, match="not initialized"):
            model.test_connection()

    def test_test_connection_returns_info_dict(self) -> None:
        model = _make_text_model()
        model.client.show.return_value = {"size": "4.7 GB"}
        info = model.test_connection()
        assert info["name"] == "test-text-model"
        assert info["status"] == "connected"

    def test_test_connection_returns_error_on_exception(self) -> None:
        model = _make_text_model()
        model.client.show.side_effect = RuntimeError("server down")
        info = model.test_connection()
        assert info["status"] == "error"
        assert "server down" in info["error"]


class TestTextModelStreaming:
    def test_generate_streaming_yields_chunks(self) -> None:
        model = _make_text_model()
        chunks = [
            {"response": "Hello", "done": False},
            {"response": " world", "done": True, "done_reason": "stop"},
        ]
        model.client.generate.return_value = iter(chunks)
        result = list(model.generate_streaming("prompt"))
        assert result == ["Hello", " world"]

    def test_streaming_guard_iterator_close(self) -> None:
        """_GuardedIterator.close() must fire the on_close callback."""
        from file_organizer.models.text_model import _GuardedIterator

        fired: list[bool] = []

        def gen():
            yield "a"
            yield "b"

        gi = _GuardedIterator(gen(), lambda: fired.append(True))
        next(gi)
        gi.close()
        assert fired == [True]

    def test_streaming_guard_iterator_fires_on_exhaustion(self) -> None:
        from file_organizer.models.text_model import _GuardedIterator

        fired: list[bool] = []

        def gen():
            yield "x"

        gi = _GuardedIterator(gen(), lambda: fired.append(True))
        next(gi)
        with pytest.raises(StopIteration):
            next(gi)
        assert fired == [True]


# ===========================================================================
# VisionModel
# ===========================================================================


class TestVisionModelInit:
    def test_requires_ollama_available(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType
        from file_organizer.models.vision_model import VisionModel

        config = ModelConfig(name="v", model_type=ModelType.VISION)
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", False):
            with pytest.raises(ImportError, match="Ollama is not installed"):
                VisionModel(config)

    def test_rejects_wrong_model_type(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType
        from file_organizer.models.vision_model import VisionModel

        config = ModelConfig(name="v", model_type=ModelType.TEXT)
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            with pytest.raises(ValueError, match="Expected VISION or VIDEO"):
                VisionModel(config)

    def test_accepts_video_model_type(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType
        from file_organizer.models.vision_model import VisionModel

        config = ModelConfig(name="v", model_type=ModelType.VIDEO)
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(config)
        assert model.config.model_type == ModelType.VIDEO

    def test_get_default_config_returns_vision_type(self) -> None:
        from file_organizer.models.base import ModelType
        from file_organizer.models.vision_model import VisionModel

        cfg = VisionModel.get_default_config()
        assert cfg.model_type == ModelType.VISION
        assert cfg.temperature == 0.3

    def test_get_default_config_custom_name(self) -> None:
        from file_organizer.models.vision_model import VisionModel

        cfg = VisionModel.get_default_config("my-vision-model")
        assert cfg.name == "my-vision-model"

    def test_initialize_skips_when_already_initialized(self) -> None:
        model = _make_vision_model()
        model.initialize()
        model.client.show.assert_not_called()

    def test_initialize_pulls_when_show_raises_response_error(self) -> None:
        from file_organizer.models.vision_model import VisionModel

        config = VisionModel.get_default_config("pull-vision")
        with patch("file_organizer.models.vision_model.OLLAMA_AVAILABLE", True):
            model = VisionModel(config)
        mock_client = MagicMock()

        class FakeResponseError(Exception):
            pass

        mock_client.show.side_effect = FakeResponseError("not found")
        with (
            patch("file_organizer.models.vision_model.ollama.Client", return_value=mock_client),
            patch("file_organizer.models.vision_model.ollama.ResponseError", FakeResponseError),
        ):
            model.initialize()

        mock_client.show.assert_called_once_with("pull-vision")
        mock_client.pull.assert_called_once_with("pull-vision")
        assert model._initialized is True


class TestVisionModelGenerate:
    def test_generate_with_image_path(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "img.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n")

        model.client.generate.return_value = _ok_response("A picture of something")
        result = model.generate("describe", image_path=img)
        assert result == "A picture of something"

    def test_generate_with_image_data(self) -> None:
        model = _make_vision_model()
        model.client.generate.return_value = _ok_response("bytes image result")
        result = model.generate("describe", image_data=b"\xff\xd8\xff")
        assert result == "bytes image result"

    def test_generate_raises_when_both_path_and_data(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "img.png"
        img.write_bytes(b"fake")
        with pytest.raises(ValueError, match="exactly one"):
            model.generate("p", image_path=img, image_data=b"data")

    def test_generate_raises_when_neither_path_nor_data(self) -> None:
        model = _make_vision_model()
        with pytest.raises(ValueError, match="exactly one"):
            model.generate("p")

    def test_generate_raises_file_not_found(self) -> None:
        model = _make_vision_model()
        with pytest.raises(FileNotFoundError):
            model.generate("p", image_path=Path("/nonexistent/image.png"))

    def test_generate_raises_on_empty_response(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "img.png"
        img.write_bytes(b"fake")
        model.client.generate.return_value = {"response": "", "done_reason": "stop"}
        with pytest.raises(ValueError, match="empty response"):
            model.generate("p", image_path=img)

    def test_generate_retries_on_token_exhaustion(self, tmp_path: Path) -> None:

        model = _make_vision_model()
        img = tmp_path / "img.png"
        img.write_bytes(b"fake")
        model.client.generate.side_effect = [
            _exhausted_response(),
            _ok_response("retry success"),
        ]
        result = model.generate("p", image_path=img)
        assert result == "retry success"
        assert model.client.generate.call_count == 2

    def test_generate_raises_token_exhaustion_on_double_fail(self, tmp_path: Path) -> None:
        from file_organizer.models.base import TokenExhaustionError

        model = _make_vision_model()
        img = tmp_path / "img.png"
        img.write_bytes(b"fake")
        model.client.generate.side_effect = [
            _exhausted_response(),
            _exhausted_response(),
        ]
        with pytest.raises(TokenExhaustionError):
            model.generate("p", image_path=img)

    def test_generate_raises_runtime_when_not_initialized(self) -> None:
        model = _make_vision_model()
        model._initialized = False
        model.client = None
        with pytest.raises(RuntimeError, match="not initialized"):
            model.generate("p", image_data=b"x")

    def test_cleanup_resets_state(self) -> None:
        model = _make_vision_model()
        model.cleanup()
        assert model._initialized is False
        assert model.client is None

    def test_test_connection_not_initialized_raises(self) -> None:
        model = _make_vision_model()
        model._initialized = False
        model.client = None
        with pytest.raises(RuntimeError, match="not initialized"):
            model.test_connection()

    def test_test_connection_returns_info_dict(self) -> None:
        model = _make_vision_model()
        model.client.show.return_value = {"size": "8.0 GB"}
        info = model.test_connection()
        assert info["name"] == "test-vision-model"
        assert info["type"] == "vision-language"
        assert info["status"] == "connected"

    def test_test_connection_returns_error_on_exception(self) -> None:
        model = _make_vision_model()
        model.client.show.side_effect = RuntimeError("offline")
        info = model.test_connection()
        assert info["status"] == "error"

    def test_analyze_image_uses_default_describe_prompt(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "img.png"
        img.write_bytes(b"fake")
        model.client.generate.return_value = _ok_response("A mountain landscape")
        result = model.analyze_image(img)
        assert result == "A mountain landscape"

    def test_analyze_image_uses_custom_prompt(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "img.png"
        img.write_bytes(b"fake")
        model.client.generate.return_value = _ok_response("custom response")
        result = model.analyze_image(img, task="categorize")
        assert result == "custom response"

    def test_analyze_image_with_custom_prompt_kwarg(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        img = tmp_path / "img.png"
        img.write_bytes(b"fake")
        model.client.generate.return_value = _ok_response("custom prompt result")
        result = model.analyze_image(img, custom_prompt="What color is this?")
        assert result == "custom prompt result"

    def test_analyze_video_frame_with_default_prompt(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        frame = tmp_path / "frame.jpg"
        frame.write_bytes(b"fake")
        model.client.generate.return_value = _ok_response("A car driving")
        result = model.analyze_video_frame(frame)
        assert result == "A car driving"

    def test_analyze_video_frame_with_custom_prompt(self, tmp_path: Path) -> None:
        model = _make_vision_model()
        frame = tmp_path / "frame.jpg"
        frame.write_bytes(b"fake")
        model.client.generate.return_value = _ok_response("scene response")
        result = model.analyze_video_frame(frame, prompt="Describe the scene")
        assert result == "scene response"


# ===========================================================================
# ProviderRegistry
# ===========================================================================


class TestProviderRegistry:
    def _fresh_registry(self) -> ProviderRegistry:
        from file_organizer.models.provider_registry import ProviderRegistry

        r = ProviderRegistry()
        return r

    def test_register_text_factory_only(self) -> None:
        r = self._fresh_registry()
        factory = MagicMock(return_value=MagicMock())
        r.register("my_provider", text_factory=factory)
        assert "my_provider" in r.registered_providers

    def test_register_vision_factory_only(self) -> None:
        r = self._fresh_registry()
        factory = MagicMock(return_value=MagicMock())
        r.register("my_vision", vision_factory=factory)
        assert "my_vision" in r.registered_providers

    def test_register_both_factories(self) -> None:
        r = self._fresh_registry()
        tf = MagicMock(return_value=MagicMock())
        vf = MagicMock(return_value=MagicMock())
        r.register("combo", text_factory=tf, vision_factory=vf)
        assert "combo" in r.registered_providers

    def test_register_raises_when_no_factory_given(self) -> None:
        r = self._fresh_registry()
        with pytest.raises(ValueError, match="At least one"):
            r.register("empty")

    def test_get_text_model_returns_factory_result(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType

        r = self._fresh_registry()
        mock_model = MagicMock()
        r.register("prov", text_factory=lambda cfg: mock_model)
        cfg = ModelConfig(name="m", model_type=ModelType.TEXT, provider="prov")
        result = r.get_text_model(cfg)
        assert result is mock_model

    def test_get_text_model_raises_unknown_provider(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType

        r = self._fresh_registry()
        cfg = ModelConfig(name="m", model_type=ModelType.TEXT, provider="ghost")
        with pytest.raises(ValueError, match="Unknown provider"):
            r.get_text_model(cfg)

    def test_get_vision_model_returns_factory_result(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType

        r = self._fresh_registry()
        mock_model = MagicMock()
        r.register("vprov", vision_factory=lambda cfg: mock_model)
        cfg = ModelConfig(name="m", model_type=ModelType.VISION, provider="vprov")
        result = r.get_vision_model(cfg)
        assert result is mock_model

    def test_get_vision_model_raises_unknown_provider(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType

        r = self._fresh_registry()
        cfg = ModelConfig(name="m", model_type=ModelType.VISION, provider="ghost")
        with pytest.raises(ValueError, match="Unknown provider"):
            r.get_vision_model(cfg)

    def test_get_vision_model_raises_when_only_text_registered(self) -> None:
        from file_organizer.models.base import ModelConfig, ModelType

        r = self._fresh_registry()
        r.register("text_only", text_factory=MagicMock(return_value=MagicMock()))
        cfg = ModelConfig(name="m", model_type=ModelType.VISION, provider="text_only")
        with pytest.raises(ValueError, match="no vision factory"):
            r.get_vision_model(cfg)

    def test_registered_providers_sorted(self) -> None:
        r = self._fresh_registry()
        r.register("z_prov", text_factory=MagicMock(return_value=MagicMock()))
        r.register("a_prov", text_factory=MagicMock(return_value=MagicMock()))
        providers = r.registered_providers
        assert providers == sorted(providers)

    def test_reset_for_testing_clears_registry(self) -> None:
        r = self._fresh_registry()
        r.register("to_clear", text_factory=MagicMock(return_value=MagicMock()))
        r._reset_for_testing()
        assert r.registered_providers == []

    def test_module_singleton_has_builtin_providers(self) -> None:
        from file_organizer.models.provider_registry import _registry

        providers = _registry.registered_providers
        for expected in ("ollama", "openai", "claude"):
            assert expected in providers

    def test_register_provider_module_function(self) -> None:
        from file_organizer.models.provider_registry import _registry, register_provider

        set(_registry.registered_providers)
        register_provider("test_custom_xyz", text_factory=MagicMock(return_value=MagicMock()))
        assert "test_custom_xyz" in _registry.registered_providers
        # Cleanup: remove so we don't pollute other tests
        _registry._reset_for_testing()
        # Re-register builtins (they were cleared by _reset_for_testing)
        from file_organizer.models.provider_registry import _register_builtins

        _register_builtins()


# ===========================================================================
# SuggestionTypes
# ===========================================================================


class TestSuggestionTypes:
    def test_suggestion_type_enum_values(self) -> None:
        from file_organizer.models.suggestion_types import SuggestionType

        assert SuggestionType.MOVE.value == "move"
        assert SuggestionType.RENAME.value == "rename"
        assert SuggestionType.TAG.value == "tag"
        assert SuggestionType.RESTRUCTURE.value == "restructure"
        assert SuggestionType.DELETE.value == "delete"
        assert SuggestionType.MERGE.value == "merge"

    def test_confidence_level_enum_values(self) -> None:
        from file_organizer.models.suggestion_types import ConfidenceLevel

        assert ConfidenceLevel.VERY_HIGH.value == "very_high"
        assert ConfidenceLevel.HIGH.value == "high"
        assert ConfidenceLevel.MEDIUM.value == "medium"
        assert ConfidenceLevel.LOW.value == "low"
        assert ConfidenceLevel.VERY_LOW.value == "very_low"

    def test_suggestion_confidence_level_very_high(self) -> None:
        from file_organizer.models.suggestion_types import (
            ConfidenceLevel,
            Suggestion,
            SuggestionType,
        )

        s = Suggestion(
            suggestion_id="s1",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("/a/b.txt"),
            confidence=85.0,
        )
        assert s.confidence_level == ConfidenceLevel.VERY_HIGH

    def test_suggestion_confidence_level_high(self) -> None:
        from file_organizer.models.suggestion_types import (
            ConfidenceLevel,
            Suggestion,
            SuggestionType,
        )

        s = Suggestion(
            suggestion_id="s2",
            suggestion_type=SuggestionType.RENAME,
            file_path=Path("/a/b.txt"),
            confidence=65.0,
        )
        assert s.confidence_level == ConfidenceLevel.HIGH

    def test_suggestion_confidence_level_medium(self) -> None:
        from file_organizer.models.suggestion_types import (
            ConfidenceLevel,
            Suggestion,
            SuggestionType,
        )

        s = Suggestion(
            suggestion_id="s3",
            suggestion_type=SuggestionType.TAG,
            file_path=Path("/a/b.txt"),
            confidence=45.0,
        )
        assert s.confidence_level == ConfidenceLevel.MEDIUM

    def test_suggestion_confidence_level_low(self) -> None:
        from file_organizer.models.suggestion_types import (
            ConfidenceLevel,
            Suggestion,
            SuggestionType,
        )

        s = Suggestion(
            suggestion_id="s4",
            suggestion_type=SuggestionType.DELETE,
            file_path=Path("/a/b.txt"),
            confidence=25.0,
        )
        assert s.confidence_level == ConfidenceLevel.LOW

    def test_suggestion_confidence_level_very_low(self) -> None:
        from file_organizer.models.suggestion_types import (
            ConfidenceLevel,
            Suggestion,
            SuggestionType,
        )

        s = Suggestion(
            suggestion_id="s5",
            suggestion_type=SuggestionType.MERGE,
            file_path=Path("/a/b.txt"),
            confidence=10.0,
        )
        assert s.confidence_level == ConfidenceLevel.VERY_LOW

    def test_suggestion_to_dict_all_fields(self) -> None:
        from file_organizer.models.suggestion_types import Suggestion, SuggestionType

        s = Suggestion(
            suggestion_id="s-123",
            suggestion_type=SuggestionType.MOVE,
            file_path=Path("/docs/report.pdf"),
            target_path=Path("/archive/report.pdf"),
            confidence=72.0,
            reasoning="Matches archive pattern",
            tags=["archive", "report"],
            new_name="report_2024.pdf",
            related_files=[Path("/docs/appendix.pdf")],
        )
        d = s.to_dict()
        assert d["suggestion_id"] == "s-123"
        assert d["suggestion_type"] == "move"
        assert d["file_path"] == "/docs/report.pdf"
        assert d["target_path"] == "/archive/report.pdf"
        assert d["confidence"] == 72.0
        assert d["confidence_level"] == "high"
        assert d["reasoning"] == "Matches archive pattern"
        assert d["tags"] == ["archive", "report"]
        assert d["new_name"] == "report_2024.pdf"
        assert d["related_files"] == ["/docs/appendix.pdf"]
        assert "created_at" in d

    def test_suggestion_to_dict_no_target_path(self) -> None:
        from file_organizer.models.suggestion_types import Suggestion, SuggestionType

        s = Suggestion(
            suggestion_id="s-no-target",
            suggestion_type=SuggestionType.TAG,
            file_path=Path("/a.txt"),
        )
        d = s.to_dict()
        assert d["target_path"] is None

    def test_suggestion_batch_avg_confidence(self) -> None:
        from file_organizer.models.suggestion_types import (
            Suggestion,
            SuggestionBatch,
            SuggestionType,
        )

        suggestions = [
            Suggestion("s1", SuggestionType.MOVE, Path("/a.txt"), confidence=60.0),
            Suggestion("s2", SuggestionType.MOVE, Path("/b.txt"), confidence=80.0),
        ]
        batch = SuggestionBatch(
            batch_id="b1",
            suggestions=suggestions,
            category="docs",
            description="Move documents",
        )
        assert batch.avg_confidence == pytest.approx(70.0)

    def test_suggestion_batch_avg_confidence_empty(self) -> None:
        from file_organizer.models.suggestion_types import SuggestionBatch

        batch = SuggestionBatch(
            batch_id="b2",
            suggestions=[],
            category="docs",
            description="empty",
        )
        assert batch.avg_confidence == 0.0

    def test_suggestion_batch_total_suggestions(self) -> None:
        from file_organizer.models.suggestion_types import (
            Suggestion,
            SuggestionBatch,
            SuggestionType,
        )

        suggestions = [
            Suggestion("s1", SuggestionType.MOVE, Path("/a.txt")),
            Suggestion("s2", SuggestionType.RENAME, Path("/b.txt")),
            Suggestion("s3", SuggestionType.TAG, Path("/c.txt")),
        ]
        batch = SuggestionBatch(
            batch_id="b3",
            suggestions=suggestions,
            category="mixed",
            description="batch of 3",
        )
        assert batch.total_suggestions == 3

    def test_suggestion_batch_to_dict(self) -> None:
        from file_organizer.models.suggestion_types import (
            Suggestion,
            SuggestionBatch,
            SuggestionType,
        )

        suggestions = [
            Suggestion("s1", SuggestionType.MOVE, Path("/a.txt"), confidence=50.0),
        ]
        batch = SuggestionBatch(
            batch_id="b4",
            suggestions=suggestions,
            category="cat",
            description="desc",
        )
        d = batch.to_dict()
        assert d["batch_id"] == "b4"
        assert d["category"] == "cat"
        assert d["description"] == "desc"
        assert d["total_suggestions"] == 1
        assert len(d["suggestions"]) == 1

    def test_confidence_factors_weighted_score_defaults(self) -> None:
        from file_organizer.models.suggestion_types import ConfidenceFactors

        cf = ConfidenceFactors(
            pattern_strength=80.0,
            content_similarity=60.0,
            user_history=70.0,
            naming_convention=90.0,
            file_type_match=85.0,
            recency=50.0,
            size_appropriateness=40.0,
        )
        score = cf.calculate_weighted_score()
        assert 0.0 <= score <= 100.0

    def test_confidence_factors_clamps_to_100(self) -> None:
        from file_organizer.models.suggestion_types import ConfidenceFactors

        cf = ConfidenceFactors(
            pattern_strength=200.0,
            content_similarity=200.0,
            user_history=200.0,
            naming_convention=200.0,
            file_type_match=200.0,
            recency=200.0,
            size_appropriateness=200.0,
        )
        assert cf.calculate_weighted_score() == 100.0

    def test_confidence_factors_clamps_to_zero(self) -> None:
        from file_organizer.models.suggestion_types import ConfidenceFactors

        cf = ConfidenceFactors(
            pattern_strength=-100.0,
            content_similarity=-100.0,
            user_history=-100.0,
            naming_convention=-100.0,
            file_type_match=-100.0,
            recency=-100.0,
            size_appropriateness=-100.0,
        )
        assert cf.calculate_weighted_score() == 0.0

    def test_confidence_factors_to_dict(self) -> None:
        from file_organizer.models.suggestion_types import ConfidenceFactors

        cf = ConfidenceFactors(pattern_strength=50.0)
        d = cf.to_dict()
        assert d["pattern_strength"] == 50.0
        assert "weighted_score" in d
        assert "weights" in d


# ===========================================================================
# ConfigManager
# ===========================================================================


class TestConfigManager:
    def test_load_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        mgr = ConfigManager(config_dir=tmp_path)
        config = mgr.load()
        assert config.profile_name == "default"

    def test_load_custom_profile_returns_default_when_file_missing(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        mgr = ConfigManager(config_dir=tmp_path)
        config = mgr.load(profile="production")
        assert config.profile_name == "production"

    def test_save_creates_config_file(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="test"))
        config_file = tmp_path / "config.yaml"
        assert config_file.exists()

    def test_save_and_load_roundtrip(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        original = AppConfig(
            profile_name="dev",
            default_methodology="para",
            setup_completed=True,
        )
        mgr.save(original)
        loaded = mgr.load(profile="dev")
        assert loaded.profile_name == "dev"
        assert loaded.default_methodology == "para"
        assert loaded.setup_completed is True

    def test_save_and_load_multiple_profiles(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="alpha", default_methodology="jd"), profile="alpha")
        mgr.save(AppConfig(profile_name="beta", default_methodology="para"), profile="beta")

        alpha = mgr.load(profile="alpha")
        beta = mgr.load(profile="beta")
        assert alpha.default_methodology == "jd"
        assert beta.default_methodology == "para"

    def test_list_profiles_empty_when_no_file(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.list_profiles() == []

    def test_list_profiles_after_save(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="p1"), profile="p1")
        mgr.save(AppConfig(profile_name="p2"), profile="p2")
        profiles = mgr.list_profiles()
        assert "p1" in profiles
        assert "p2" in profiles

    def test_delete_profile_removes_it(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="to_delete"), profile="to_delete")
        assert "to_delete" in mgr.list_profiles()
        result = mgr.delete_profile("to_delete")
        assert result is True
        assert "to_delete" not in mgr.list_profiles()

    def test_delete_profile_returns_false_when_not_found(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="other"), profile="other")
        result = mgr.delete_profile("nonexistent")
        assert result is False

    def test_delete_profile_returns_false_when_no_file(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        mgr = ConfigManager(config_dir=tmp_path)
        result = mgr.delete_profile("ghost")
        assert result is False

    def test_load_returns_defaults_on_corrupt_yaml(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        config_file = tmp_path / "config.yaml"
        config_file.write_text(": invalid: yaml: {{{{", encoding="utf-8")
        mgr = ConfigManager(config_dir=tmp_path)
        config = mgr.load()
        assert config.profile_name == "default"

    def test_load_returns_defaults_when_profile_missing(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="exists"), profile="exists")
        config = mgr.load(profile="does_not_exist")
        assert config.profile_name == "does_not_exist"

    def test_config_dir_property(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.config_dir == tmp_path

    def test_to_text_model_config(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig
        from file_organizer.models.base import ModelType

        mgr = ConfigManager(config_dir=tmp_path)
        app_config = AppConfig()
        mc = mgr.to_text_model_config(app_config)
        assert mc.model_type == ModelType.TEXT
        assert mc.name == app_config.models.text_model

    def test_to_vision_model_config(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig
        from file_organizer.models.base import ModelType

        mgr = ConfigManager(config_dir=tmp_path)
        app_config = AppConfig()
        mc = mgr.to_vision_model_config(app_config)
        assert mc.model_type == ModelType.VISION
        assert mc.name == app_config.models.vision_model

    def test_config_to_dict_includes_expected_keys(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        d = mgr.config_to_dict(AppConfig())
        assert "version" in d
        assert "default_methodology" in d
        assert "models" in d
        assert "updates" in d

    def test_save_preserves_existing_profiles(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="first"), profile="first")
        mgr.save(AppConfig(profile_name="second"), profile="second")

        profiles = mgr.list_profiles()
        assert "first" in profiles
        assert "second" in profiles

    def test_load_with_models_data(self, tmp_path: Path) -> None:
        import yaml

        from file_organizer.config.manager import ConfigManager

        config_file = tmp_path / "config.yaml"
        data = {
            "profiles": {
                "custom": {
                    "version": "1.0",
                    "default_methodology": "none",
                    "setup_completed": False,
                    "models": {
                        "text_model": "llama3:8b",
                        "temperature": 0.7,
                    },
                    "updates": {},
                }
            }
        }
        config_file.write_text(yaml.dump(data), encoding="utf-8")
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load(profile="custom")
        assert cfg.models.text_model == "llama3:8b"
        assert cfg.models.temperature == pytest.approx(0.7)

    def test_to_watcher_config(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        config = mgr.to_watcher_config(AppConfig())
        # WatcherConfig should be returned (any valid instance)
        assert config is not None

    def test_to_watcher_config_with_overrides(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        app = AppConfig(watcher={"debounce_seconds": 2.5})
        config = mgr.to_watcher_config(app)
        assert config is not None
        assert config.debounce_seconds == pytest.approx(2.5)

    def test_to_daemon_config(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        config = mgr.to_daemon_config(AppConfig())
        assert config is not None

    def test_to_parallel_config(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        config = mgr.to_parallel_config(AppConfig())
        assert config is not None

    def test_to_event_config(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        config = mgr.to_event_config(AppConfig())
        assert config is not None

    def test_to_para_config(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        config = mgr.to_para_config(AppConfig())
        assert config is not None

    def test_to_johnny_decimal_config_no_overrides(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager
        from file_organizer.config.schema import AppConfig

        mgr = ConfigManager(config_dir=tmp_path)
        from file_organizer.methodologies.johnny_decimal.config import JohnnyDecimalConfig

        config = mgr.to_johnny_decimal_config(AppConfig())
        assert isinstance(config, JohnnyDecimalConfig)
        assert config.scheme is not None

    def test_list_profiles_returns_empty_when_yaml_not_dict(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        config_file = tmp_path / "config.yaml"
        config_file.write_text("- just\n- a\n- list\n", encoding="utf-8")
        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.list_profiles() == []

    def test_delete_profile_when_yaml_not_dict(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        config_file = tmp_path / "config.yaml"
        config_file.write_text("- just\n- a\n- list\n", encoding="utf-8")
        mgr = ConfigManager(config_dir=tmp_path)
        result = mgr.delete_profile("any")
        assert result is False

    def test_load_when_yaml_not_dict(self, tmp_path: Path) -> None:
        from file_organizer.config.manager import ConfigManager

        config_file = tmp_path / "config.yaml"
        config_file.write_text("just a string\n", encoding="utf-8")
        mgr = ConfigManager(config_dir=tmp_path)
        config = mgr.load()
        assert config.profile_name == "default"


# ===========================================================================
# PathManager
# ===========================================================================


class TestPathManagerFunctions:
    def test_get_config_dir_uses_xdg_config_home(self, tmp_path: Path, monkeypatch) -> None:
        from file_organizer.config.path_manager import get_config_dir

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        result = get_config_dir()
        assert result == tmp_path / "file-organizer"

    def test_get_config_dir_default(self, monkeypatch) -> None:
        from file_organizer.config.path_manager import get_config_dir

        monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
        result = get_config_dir()
        assert result.name == "file-organizer"

    def test_get_data_dir_uses_xdg_data_home(self, tmp_path: Path, monkeypatch) -> None:
        from file_organizer.config.path_manager import get_data_dir

        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        result = get_data_dir()
        assert result == tmp_path / "file-organizer"

    def test_get_data_dir_default(self, monkeypatch) -> None:
        from file_organizer.config.path_manager import get_data_dir

        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        result = get_data_dir()
        assert result.name == "file-organizer"

    def test_get_state_dir_uses_xdg_state_home(self, tmp_path: Path, monkeypatch) -> None:
        from file_organizer.config.path_manager import get_state_dir

        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
        result = get_state_dir()
        assert result == tmp_path / "file-organizer"

    def test_get_state_dir_default(self, monkeypatch) -> None:
        from file_organizer.config.path_manager import get_state_dir

        monkeypatch.delenv("XDG_STATE_HOME", raising=False)
        result = get_state_dir()
        assert result.name == "file-organizer"

    def test_get_cache_dir_returns_path(self) -> None:
        from file_organizer.config.path_manager import get_cache_dir

        result = get_cache_dir()
        assert isinstance(result, Path)
        assert result.name == "file-organizer"

    def test_get_canonical_paths_returns_expected_keys(self) -> None:
        from file_organizer.config.path_manager import get_canonical_paths

        paths = get_canonical_paths()
        for key in ("config", "data", "state", "cache", "history", "metadata", "logs"):
            assert key in paths
            assert isinstance(paths[key], Path)

    def test_get_canonical_paths_history_under_data(self) -> None:
        from file_organizer.config.path_manager import get_canonical_paths

        paths = get_canonical_paths()
        assert paths["history"].parent == paths["data"]

    def test_get_canonical_paths_logs_under_state(self) -> None:
        from file_organizer.config.path_manager import get_canonical_paths

        paths = get_canonical_paths()
        assert paths["logs"].parent == paths["state"]


class TestPathManagerClass:
    def test_path_manager_init_has_all_paths(self) -> None:
        from file_organizer.config.path_manager import PathManager

        pm = PathManager()
        assert pm.config_dir is not None
        assert pm.data_dir is not None
        assert pm.state_dir is not None
        assert pm.cache_dir is not None
        assert pm.metadata_dir is not None

    def test_config_file_is_yaml(self) -> None:
        from file_organizer.config.path_manager import PathManager

        pm = PathManager()
        assert pm.config_file.name == "config.json"
        assert pm.config_file.parent == pm.config_dir

    def test_preferences_file_is_json(self) -> None:
        from file_organizer.config.path_manager import PathManager

        pm = PathManager()
        assert pm.preferences_file.name == "preferences.json"

    def test_history_db_under_history_dir(self) -> None:
        from file_organizer.config.path_manager import PathManager

        pm = PathManager()
        assert pm.history_db.name == "operations.db"

    def test_undo_redo_db_under_state_dir(self) -> None:
        from file_organizer.config.path_manager import PathManager

        pm = PathManager()
        assert pm.undo_redo_db.parent == pm.state_dir

    def test_ensure_directories_creates_dirs(self, tmp_path: Path, monkeypatch) -> None:
        from file_organizer.config.path_manager import PathManager

        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
        monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))

        pm = PathManager()
        pm.ensure_directories()

        assert pm.config_dir.exists()
        assert pm.data_dir.exists()
        assert pm.state_dir.exists()

    def test_get_path_returns_correct_path(self) -> None:
        from file_organizer.config.path_manager import PathManager

        pm = PathManager()
        config_path = pm.get_path("config")
        assert config_path == pm.config_dir

    def test_get_path_raises_on_unknown_category(self) -> None:
        from file_organizer.config.path_manager import PathManager

        pm = PathManager()
        with pytest.raises(ValueError, match="Unknown path category"):
            pm.get_path("nonexistent_category_xyz")

    def test_get_path_all_valid_categories(self) -> None:
        from file_organizer.config.path_manager import PathManager

        pm = PathManager()
        for category in ("config", "data", "state", "cache", "history", "metadata", "logs"):
            result = pm.get_path(category)
            assert isinstance(result, Path)


# ===========================================================================
# Analytics
# ===========================================================================


class TestStorageStats:
    def _make_stats(self, **kwargs) -> StorageStats:
        from file_organizer.models.analytics import StorageStats

        defaults = {
            "total_size": 1024 * 1024 * 100,
            "organized_size": 1024 * 1024 * 50,
            "saved_size": 1024 * 1024 * 10,
            "file_count": 200,
            "directory_count": 20,
        }
        defaults.update(kwargs)
        return StorageStats(**defaults)

    def test_formatted_total_size_gb(self) -> None:
        stats = self._make_stats(total_size=2 * 1024**3)
        assert "GB" in stats.formatted_total_size

    def test_formatted_total_size_mb(self) -> None:
        stats = self._make_stats(total_size=10 * 1024**2)
        assert "MB" in stats.formatted_total_size

    def test_formatted_total_size_kb(self) -> None:
        stats = self._make_stats(total_size=2048)
        assert "KB" in stats.formatted_total_size

    def test_formatted_total_size_bytes(self) -> None:
        stats = self._make_stats(total_size=500)
        assert "B" in stats.formatted_total_size

    def test_savings_percentage_calculation(self) -> None:
        stats = self._make_stats(total_size=100, saved_size=25)
        assert stats.savings_percentage == pytest.approx(25.0)

    def test_savings_percentage_zero_total(self) -> None:
        stats = self._make_stats(total_size=0, saved_size=0)
        assert stats.savings_percentage == 0.0

    def test_formatted_saved_size(self) -> None:
        stats = self._make_stats(saved_size=5 * 1024**2)
        assert "MB" in stats.formatted_saved_size


class TestFileDistribution:
    def test_get_type_percentage_zero_total(self) -> None:
        from file_organizer.models.analytics import FileDistribution

        fd = FileDistribution()
        assert fd.get_type_percentage("pdf") == 0.0

    def test_get_type_percentage_nonzero(self) -> None:
        from file_organizer.models.analytics import FileDistribution

        fd = FileDistribution(by_type={"pdf": 10, "jpg": 10}, total_files=20)
        assert fd.get_type_percentage("pdf") == pytest.approx(50.0)

    def test_get_type_percentage_missing_type(self) -> None:
        from file_organizer.models.analytics import FileDistribution

        fd = FileDistribution(by_type={"pdf": 5}, total_files=10)
        assert fd.get_type_percentage("docx") == 0.0


class TestDuplicateStats:
    def test_formatted_space_wasted(self) -> None:
        from file_organizer.models.analytics import DuplicateStats

        ds = DuplicateStats(
            total_duplicates=5,
            duplicate_groups=2,
            space_wasted=1024**2,
            space_recoverable=512 * 1024,
        )
        assert "MB" in ds.formatted_space_wasted

    def test_formatted_recoverable(self) -> None:
        from file_organizer.models.analytics import DuplicateStats

        ds = DuplicateStats(
            total_duplicates=3,
            duplicate_groups=1,
            space_wasted=1024**2,
            space_recoverable=512 * 1024,
        )
        assert "KB" in ds.formatted_recoverable


class TestQualityMetrics:
    def test_grade_a(self) -> None:
        from file_organizer.models.analytics import QualityMetrics

        qm = QualityMetrics(
            quality_score=95.0,
            naming_compliance=0.9,
            structure_consistency=0.9,
            metadata_completeness=0.9,
            categorization_accuracy=0.9,
        )
        assert qm.grade == "A"

    def test_grade_b(self) -> None:
        from file_organizer.models.analytics import QualityMetrics

        qm = QualityMetrics(
            quality_score=85.0,
            naming_compliance=0.8,
            structure_consistency=0.8,
            metadata_completeness=0.8,
            categorization_accuracy=0.8,
        )
        assert qm.grade == "B"

    def test_grade_c(self) -> None:
        from file_organizer.models.analytics import QualityMetrics

        qm = QualityMetrics(
            quality_score=75.0,
            naming_compliance=0.7,
            structure_consistency=0.7,
            metadata_completeness=0.7,
            categorization_accuracy=0.7,
        )
        assert qm.grade == "C"

    def test_grade_d(self) -> None:
        from file_organizer.models.analytics import QualityMetrics

        qm = QualityMetrics(
            quality_score=65.0,
            naming_compliance=0.6,
            structure_consistency=0.6,
            metadata_completeness=0.6,
            categorization_accuracy=0.6,
        )
        assert qm.grade == "D"

    def test_grade_f(self) -> None:
        from file_organizer.models.analytics import QualityMetrics

        qm = QualityMetrics(
            quality_score=55.0,
            naming_compliance=0.5,
            structure_consistency=0.5,
            metadata_completeness=0.5,
            categorization_accuracy=0.5,
        )
        assert qm.grade == "F"

    def test_formatted_score(self) -> None:
        from file_organizer.models.analytics import QualityMetrics

        qm = QualityMetrics(
            quality_score=92.5,
            naming_compliance=0.9,
            structure_consistency=0.9,
            metadata_completeness=0.9,
            categorization_accuracy=0.9,
        )
        assert qm.formatted_score == "92.5/100 (A)"


class TestTimeSavings:
    def test_automation_percentage_nonzero(self) -> None:
        from file_organizer.models.analytics import TimeSavings

        ts = TimeSavings(
            total_operations=100,
            automated_operations=75,
            manual_time_seconds=3600,
            automated_time_seconds=900,
            estimated_time_saved_seconds=2700,
        )
        assert ts.automation_percentage == pytest.approx(75.0)

    def test_automation_percentage_zero_total(self) -> None:
        from file_organizer.models.analytics import TimeSavings

        ts = TimeSavings(
            total_operations=0,
            automated_operations=0,
            manual_time_seconds=0,
            automated_time_seconds=0,
            estimated_time_saved_seconds=0,
        )
        assert ts.automation_percentage == 0.0

    def test_formatted_time_saved_seconds(self) -> None:
        from file_organizer.models.analytics import TimeSavings

        ts = TimeSavings(
            total_operations=10,
            automated_operations=10,
            manual_time_seconds=100,
            automated_time_seconds=10,
            estimated_time_saved_seconds=45,
        )
        assert ts.formatted_time_saved == "45s"

    def test_formatted_time_saved_minutes(self) -> None:
        from file_organizer.models.analytics import TimeSavings

        ts = TimeSavings(
            total_operations=10,
            automated_operations=10,
            manual_time_seconds=100,
            automated_time_seconds=10,
            estimated_time_saved_seconds=120,
        )
        assert ts.formatted_time_saved.endswith("m")

    def test_formatted_time_saved_hours(self) -> None:
        from file_organizer.models.analytics import TimeSavings

        ts = TimeSavings(
            total_operations=10,
            automated_operations=10,
            manual_time_seconds=0,
            automated_time_seconds=0,
            estimated_time_saved_seconds=7200,
        )
        assert ts.formatted_time_saved.endswith("h")

    def test_formatted_time_saved_days(self) -> None:
        from file_organizer.models.analytics import TimeSavings

        ts = TimeSavings(
            total_operations=10,
            automated_operations=10,
            manual_time_seconds=0,
            automated_time_seconds=0,
            estimated_time_saved_seconds=86400 * 2,
        )
        assert ts.formatted_time_saved.endswith("d")


class TestTrendData:
    def test_add_data_point(self) -> None:
        from file_organizer.models.analytics import TrendData

        td = TrendData(metric_name="quality_score")
        now = datetime.now(tz=UTC)
        td.add_data_point(85.0, now)
        assert len(td.values) == 1
        assert td.values[0] == 85.0

    def test_trend_direction_stable_with_one_point(self) -> None:
        from file_organizer.models.analytics import TrendData

        td = TrendData(metric_name="score")
        td.add_data_point(50.0, datetime.now(tz=UTC))
        assert td.trend_direction == "stable"

    def test_trend_direction_stable_empty(self) -> None:
        from file_organizer.models.analytics import TrendData

        td = TrendData(metric_name="score")
        assert td.trend_direction == "stable"

    def test_trend_direction_up(self) -> None:
        from file_organizer.models.analytics import TrendData

        td = TrendData(metric_name="score")
        now = datetime.now(tz=UTC)
        for v in [10.0, 10.0, 90.0, 90.0, 90.0]:
            td.add_data_point(v, now)
        assert td.trend_direction == "up"

    def test_trend_direction_down(self) -> None:
        from file_organizer.models.analytics import TrendData

        td = TrendData(metric_name="score")
        now = datetime.now(tz=UTC)
        for v in [90.0, 90.0, 10.0, 10.0, 10.0]:
            td.add_data_point(v, now)
        assert td.trend_direction == "down"


class TestAnalyticsDashboard:
    def _make_dashboard(self) -> AnalyticsDashboard:
        from file_organizer.models.analytics import (
            AnalyticsDashboard,
            DuplicateStats,
            FileDistribution,
            QualityMetrics,
            StorageStats,
            TimeSavings,
        )

        return AnalyticsDashboard(
            storage_stats=StorageStats(
                total_size=1024**3,
                organized_size=512 * 1024**2,
                saved_size=100 * 1024**2,
                file_count=500,
                directory_count=50,
            ),
            file_distribution=FileDistribution(
                by_type={"pdf": 100, "jpg": 200},
                by_category={"work": 150, "personal": 150},
                total_files=500,
            ),
            duplicate_stats=DuplicateStats(
                total_duplicates=20,
                duplicate_groups=10,
                space_wasted=50 * 1024**2,
                space_recoverable=40 * 1024**2,
            ),
            quality_metrics=QualityMetrics(
                quality_score=88.0,
                naming_compliance=0.85,
                structure_consistency=0.90,
                metadata_completeness=0.80,
                categorization_accuracy=0.92,
            ),
            time_savings=TimeSavings(
                total_operations=1000,
                automated_operations=900,
                manual_time_seconds=36000,
                automated_time_seconds=3600,
                estimated_time_saved_seconds=32400,
            ),
        )

    def test_to_dict_contains_all_sections(self) -> None:
        dashboard = self._make_dashboard()
        d = dashboard.to_dict()
        assert "storage_stats" in d
        assert "file_distribution" in d
        assert "duplicate_stats" in d
        assert "quality_metrics" in d
        assert "time_savings" in d
        assert "generated_at" in d

    def test_to_dict_storage_stats_values(self) -> None:
        dashboard = self._make_dashboard()
        d = dashboard.to_dict()
        assert d["storage_stats"]["file_count"] == 500
        assert d["storage_stats"]["directory_count"] == 50

    def test_to_dict_quality_grade(self) -> None:
        dashboard = self._make_dashboard()
        d = dashboard.to_dict()
        assert d["quality_metrics"]["grade"] == "B"

    def test_to_dict_automation_percentage(self) -> None:
        dashboard = self._make_dashboard()
        d = dashboard.to_dict()
        assert d["time_savings"]["automation_percentage"] == pytest.approx(90.0)


class TestFileInfo:
    def test_file_info_fields(self) -> None:
        from file_organizer.models.analytics import FileInfo

        now = datetime.now(tz=UTC)
        fi = FileInfo(path=Path("/docs/report.pdf"), size=1024, type="pdf", modified=now)
        assert fi.path == Path("/docs/report.pdf")
        assert fi.size == 1024
        assert fi.type == "pdf"
        assert fi.modified == now
        assert fi.category is None

    def test_file_info_with_category(self) -> None:
        from file_organizer.models.analytics import FileInfo

        now = datetime.now(tz=UTC)
        fi = FileInfo(
            path=Path("/docs/report.pdf"),
            size=2048,
            type="pdf",
            modified=now,
            category="work",
        )
        assert fi.category == "work"


class TestMetricsSnapshot:
    def test_metrics_snapshot_fields(self) -> None:
        from file_organizer.models.analytics import (
            MetricsSnapshot,
            QualityMetrics,
            StorageStats,
        )

        now = datetime.now(tz=UTC)
        ss = StorageStats(
            total_size=100,
            organized_size=50,
            saved_size=10,
            file_count=10,
            directory_count=2,
        )
        qm = QualityMetrics(
            quality_score=80.0,
            naming_compliance=0.8,
            structure_consistency=0.8,
            metadata_completeness=0.8,
            categorization_accuracy=0.8,
        )
        snap = MetricsSnapshot(timestamp=now, storage_stats=ss, quality_metrics=qm)
        assert snap.timestamp == now
        assert snap.duplicate_stats is None
        assert snap.time_savings is None
