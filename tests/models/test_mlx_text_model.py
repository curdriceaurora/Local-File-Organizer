"""Unit tests for MLXTextModel — init, generation, cleanup, and defaults."""

from __future__ import annotations

import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import ModelConfig, ModelType

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _make_config(
    model_path: str = "mlx-community/Qwen2.5-3B-Instruct-4bit",
) -> ModelConfig:
    return ModelConfig(
        name="mlx-lm",
        model_type=ModelType.TEXT,
        provider="mlx",
        model_path=model_path,
    )


class TestImportGuard:
    def test_raises_import_error_if_mlx_lm_missing(self) -> None:
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", False):
            from file_organizer.models.mlx_text_model import MLXTextModel

            with pytest.raises(ImportError, match="mlx-lm"):
                MLXTextModel(_make_config())

    def test_import_error_mentions_install_command(self) -> None:
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", False):
            from file_organizer.models.mlx_text_model import MLXTextModel

            with pytest.raises(ImportError, match=r"local-file-organizer\[mlx\]"):
                MLXTextModel(_make_config())


class TestConstruction:
    def test_raises_if_model_type_is_not_text(self) -> None:
        cfg = ModelConfig(
            name="mlx-lm",
            model_type=ModelType.VISION,
            provider="mlx",
            model_path="mlx-community/Qwen2.5-3B-Instruct-4bit",
        )
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            from file_organizer.models.mlx_text_model import MLXTextModel

            with pytest.raises(ValueError, match=r"ModelType\.TEXT"):
                MLXTextModel(cfg)

    def test_raises_if_model_path_missing(self) -> None:
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            from file_organizer.models.mlx_text_model import MLXTextModel

            with pytest.raises(ValueError, match="model_path"):
                MLXTextModel(_make_config(model_path=""))

    def test_model_and_tokenizer_start_none(self) -> None:
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            from file_organizer.models.mlx_text_model import MLXTextModel

            model = MLXTextModel(_make_config())
        assert model._model is None
        assert model._tokenizer is None
        assert not model.is_initialized


class TestInitialize:
    def test_initialize_loads_model_and_tokenizer(self) -> None:
        mock_model = object()
        mock_tokenizer = object()
        with (
            patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True),
            patch(
                "file_organizer.models.mlx_text_model.mlx_load",
                MagicMock(return_value=(mock_model, mock_tokenizer)),
            ) as mock_load,
        ):
            from file_organizer.models.mlx_text_model import MLXTextModel

            model = MLXTextModel(_make_config())
            model.initialize()

        mock_load.assert_called_once_with("mlx-community/Qwen2.5-3B-Instruct-4bit")
        assert model._model is mock_model
        assert model._tokenizer is mock_tokenizer
        assert model.is_initialized

    def test_initialize_is_idempotent(self) -> None:
        with (
            patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True),
            patch(
                "file_organizer.models.mlx_text_model.mlx_load",
                MagicMock(return_value=(object(), object())),
            ) as mock_load,
        ):
            from file_organizer.models.mlx_text_model import MLXTextModel

            model = MLXTextModel(_make_config())
            model.initialize()
            model.initialize()

        assert mock_load.call_count == 1

    def test_initialize_raises_runtime_error_on_load_failure(self) -> None:
        with (
            patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True),
            patch(
                "file_organizer.models.mlx_text_model.mlx_load",
                MagicMock(side_effect=RuntimeError("load failed")),
            ),
        ):
            from file_organizer.models.mlx_text_model import MLXTextModel

            model = MLXTextModel(_make_config())
            with pytest.raises(RuntimeError, match="Could not load MLX model"):
                model.initialize()

    def test_initialize_raises_runtime_error_on_invalid_load_shape(self) -> None:
        with (
            patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True),
            patch(
                "file_organizer.models.mlx_text_model.mlx_load",
                MagicMock(return_value=object()),
            ),
        ):
            from file_organizer.models.mlx_text_model import MLXTextModel

            model = MLXTextModel(_make_config())
            with pytest.raises(RuntimeError, match=r"expected \(model, tokenizer\)"):
                model.initialize()


class TestGenerate:
    def _initialized_model(self) -> tuple[Any, Any]:
        with (
            patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True),
            patch(
                "file_organizer.models.mlx_text_model.mlx_load",
                MagicMock(return_value=(object(), object())),
            ),
        ):
            from file_organizer.models.mlx_text_model import MLXTextModel

            model = MLXTextModel(_make_config())
            model.initialize()
            return model, MLXTextModel

    def test_generate_returns_stripped_text(self) -> None:
        model, _ = self._initialized_model()
        with patch(
            "file_organizer.models.mlx_text_model.mlx_generate",
            MagicMock(return_value="  result  "),
        ):
            result = model.generate("hello")
        assert result == "result"

    def test_generate_raises_when_not_initialized(self) -> None:
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            from file_organizer.models.mlx_text_model import MLXTextModel

            model = MLXTextModel(_make_config())
            with pytest.raises(RuntimeError, match="initialize"):
                model.generate("prompt")

    def test_generate_passes_prompt_and_max_tokens(self) -> None:
        model, _ = self._initialized_model()
        mock_generate = MagicMock(return_value="ok")
        with patch("file_organizer.models.mlx_text_model.mlx_generate", mock_generate):
            model.generate("prompt", max_tokens=128)

        args, kwargs = mock_generate.call_args
        assert args[2] == "prompt"
        assert kwargs["max_tokens"] == 128

    def test_generate_falls_back_when_signature_rejects_kwargs(self) -> None:
        model, _ = self._initialized_model()

        def _side_effect(*args: Any, **kwargs: Any) -> str:
            if "top_k" in kwargs:
                raise TypeError("unexpected keyword argument 'top_k'")
            if "top_p" in kwargs:
                raise TypeError("unexpected keyword argument 'top_p'")
            if "temp" in kwargs:
                raise TypeError("unexpected keyword argument 'temp'")
            return "ok"

        with patch(
            "file_organizer.models.mlx_text_model.mlx_generate",
            MagicMock(side_effect=_side_effect),
        ):
            assert model.generate("prompt") == "ok"

    def test_working_variant_cached_after_first_successful_fallback(self) -> None:
        model, _ = self._initialized_model()
        call_count = {"n": 0}

        def _side_effect(*args: Any, **kwargs: Any) -> str:
            call_count["n"] += 1
            if "top_k" in kwargs or "top_p" in kwargs or "temp" in kwargs:
                raise TypeError("unexpected keyword argument")
            return "ok"

        with patch(
            "file_organizer.models.mlx_text_model.mlx_generate",
            MagicMock(side_effect=_side_effect),
        ):
            model.generate("prompt")  # probes all variants; caches working index
            call_count["n"] = 0
            model.generate("prompt")  # should use cached variant — exactly 1 call

        assert call_count["n"] == 1, "Second call should use cached variant, not probe all 5"

    def test_generate_does_not_retry_non_signature_type_error(self) -> None:
        model, _ = self._initialized_model()
        calls = {"count": 0}

        def _side_effect(*_args: Any, **_kwargs: Any) -> str:
            calls["count"] += 1
            raise TypeError("bad prompt type")

        with patch(
            "file_organizer.models.mlx_text_model.mlx_generate",
            MagicMock(side_effect=_side_effect),
        ):
            with pytest.raises(TypeError, match="bad prompt type"):
                model.generate("prompt")

        assert calls["count"] == 1

    def test_generate_propagates_non_type_errors(self) -> None:
        model, _ = self._initialized_model()
        with patch(
            "file_organizer.models.mlx_text_model.mlx_generate",
            MagicMock(side_effect=ValueError("boom")),
        ):
            with pytest.raises(ValueError, match="boom"):
                model.generate("prompt")


class TestCleanup:
    def test_cleanup_clears_model_and_tokenizer(self) -> None:
        with (
            patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True),
            patch(
                "file_organizer.models.mlx_text_model.mlx_load",
                MagicMock(return_value=(object(), object())),
            ),
        ):
            from file_organizer.models.mlx_text_model import MLXTextModel

            model = MLXTextModel(_make_config())
            model.initialize()
            model.cleanup()

        assert model._model is None
        assert model._tokenizer is None
        assert model.is_initialized is False

    def test_cleanup_waits_for_in_flight_generations(self) -> None:
        with (
            patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True),
            patch(
                "file_organizer.models.mlx_text_model.mlx_load",
                MagicMock(return_value=(object(), object())),
            ),
        ):
            from file_organizer.models.mlx_text_model import MLXTextModel

            model = MLXTextModel(_make_config())
            model.initialize()

        with model._generation_done:
            model._active_generations = 1

        cleanup_done = threading.Event()

        def _run_cleanup() -> None:
            model.cleanup()
            cleanup_done.set()

        cleanup_thread = threading.Thread(target=_run_cleanup)
        cleanup_thread.start()

        time.sleep(0.05)
        assert cleanup_done.is_set() is False

        with model._generation_done:
            model._active_generations = 0
            model._generation_done.notify_all()

        cleanup_thread.join(timeout=1.0)
        assert cleanup_done.is_set() is True
        assert model._model is None
        assert model._tokenizer is None
        assert model.is_initialized is False


class TestDefaults:
    def test_returns_model_config_with_mlx_provider(self) -> None:
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            from file_organizer.models.mlx_text_model import MLXTextModel

            cfg = MLXTextModel.get_default_config("mlx-community/Qwen2.5-3B-Instruct-4bit")

        assert cfg.provider == "mlx"
        assert cfg.model_type == ModelType.TEXT
        assert cfg.model_path == "mlx-community/Qwen2.5-3B-Instruct-4bit"

    def test_default_config_has_sensible_defaults(self) -> None:
        with patch("file_organizer.models.mlx_text_model.MLX_LM_AVAILABLE", True):
            from file_organizer.models.mlx_text_model import MLXTextModel

            cfg = MLXTextModel.get_default_config()

        assert cfg.temperature == 0.5
        assert cfg.max_tokens == 3000
        assert cfg.context_window == 4096
