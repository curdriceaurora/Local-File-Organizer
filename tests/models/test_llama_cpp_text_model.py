"""Unit tests for LlamaCppTextModel — initialization, generation, cleanup, and device mapping."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.models.base import DeviceType, ModelConfig, ModelType, TokenExhaustionError

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    model_path: str = "/fake/model.gguf",
    device: DeviceType = DeviceType.AUTO,
    extra_params: dict[str, Any] | None = None,
) -> ModelConfig:
    return ModelConfig(
        name="llama-cpp",
        model_type=ModelType.TEXT,
        provider="llama_cpp",
        model_path=model_path,
        device=device,
        extra_params=extra_params,
    )


def _make_response(text: str = "hello world", finish_reason: str = "stop") -> dict[str, Any]:
    """Build a minimal llama.cpp response dict."""
    return {"choices": [{"text": text, "finish_reason": finish_reason}]}


# ---------------------------------------------------------------------------
# Import / availability guard
# ---------------------------------------------------------------------------


class TestImportGuard:
    def test_raises_import_error_if_not_available(self) -> None:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", False):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            with pytest.raises(ImportError, match="llama-cpp-python"):
                LlamaCppTextModel(_make_config())

    def test_import_error_mentions_install_command(self) -> None:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", False):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            with pytest.raises(ImportError, match="local-file-organizer\\[llama\\]"):
                LlamaCppTextModel(_make_config())


# ---------------------------------------------------------------------------
# Construction validation
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_raises_if_model_type_is_not_text(self) -> None:
        cfg = ModelConfig(
            name="llama-cpp",
            model_type=ModelType.VISION,
            provider="llama_cpp",
            model_path="/fake/model.gguf",
        )
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            with pytest.raises(ValueError, match=r"ModelType\.TEXT"):
                LlamaCppTextModel(cfg)

    def test_raises_if_model_path_is_empty_string(self) -> None:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            with pytest.raises(ValueError, match="model_path"):
                LlamaCppTextModel(_make_config(model_path=""))

    def test_raises_if_model_path_is_none(self) -> None:
        cfg = _make_config()
        cfg.model_path = None
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            with pytest.raises(ValueError, match="model_path"):
                LlamaCppTextModel(cfg)

    def test_client_is_none_before_initialize(self) -> None:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            model = LlamaCppTextModel(_make_config())
        assert model.client is None
        assert not model.is_initialized


# ---------------------------------------------------------------------------
# initialize()
# ---------------------------------------------------------------------------


class TestInitialize:
    def test_creates_llama_client_with_model_path(self) -> None:
        mock_llama = MagicMock()
        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            model = LlamaCppTextModel(_make_config("/path/model.gguf"))
            model.initialize()

        mock_llama.assert_called_once_with(
            model_path="/path/model.gguf",
            n_ctx=4096,
            n_gpu_layers=0,
            verbose=False,
        )
        assert model.client is mock_llama.return_value
        assert model.is_initialized

    def test_initialize_is_idempotent(self) -> None:
        mock_llama = MagicMock()
        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            model = LlamaCppTextModel(_make_config())
            model.initialize()
            model.initialize()  # second call is a no-op

        assert mock_llama.call_count == 1

    def test_initialize_raises_runtime_error_on_load_failure(self) -> None:
        mock_llama = MagicMock(side_effect=RuntimeError("GGUF load failed"))
        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            model = LlamaCppTextModel(_make_config())
            with pytest.raises(RuntimeError, match="Could not load"):
                model.initialize()

        assert not model.is_initialized


# ---------------------------------------------------------------------------
# generate()
# ---------------------------------------------------------------------------


class TestGenerate:
    def _initialized_model(self, mock_llama_cls: MagicMock, cfg: ModelConfig | None = None) -> Any:
        from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

        model = LlamaCppTextModel(cfg or _make_config())
        model.client = mock_llama_cls.return_value
        model._initialized = True
        model._shutting_down = False
        return model

    def test_generate_returns_stripped_text(self) -> None:
        mock_llama = MagicMock()
        mock_llama.return_value.return_value = _make_response("  result text  ")
        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            model = self._initialized_model(mock_llama)
            result = model.generate("hello")

        assert result == "result text"

    def test_generate_passes_config_defaults(self) -> None:
        mock_llama = MagicMock()
        mock_llama.return_value.return_value = _make_response("ok")
        cfg = _make_config()
        cfg.temperature = 0.7
        cfg.max_tokens = 500
        cfg.top_k = 5
        cfg.top_p = 0.9

        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            model = self._initialized_model(mock_llama, cfg)
            model.generate("prompt")

        mock_llama.return_value.assert_called_once_with(
            "prompt",
            temperature=0.7,
            max_tokens=500,
            top_k=5,
            top_p=0.9,
        )

    def test_generate_kwargs_override_config(self) -> None:
        mock_llama = MagicMock()
        mock_llama.return_value.return_value = _make_response("ok")
        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            model = self._initialized_model(mock_llama)
            model.generate("p", temperature=0.1, max_tokens=100)

        _, kwargs = mock_llama.return_value.call_args
        assert kwargs["temperature"] == 0.1
        assert kwargs["max_tokens"] == 100

    def test_generate_raises_runtime_error_if_not_initialized(self) -> None:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            model = LlamaCppTextModel(_make_config())
            # client is None, _initialized is False
            with pytest.raises(RuntimeError):
                model.generate("prompt")

    def test_generate_retries_on_token_exhaustion(self) -> None:
        exhausted = _make_response("", finish_reason="length")
        success = _make_response("full response")
        mock_llama = MagicMock()
        mock_llama.return_value.side_effect = [exhausted, success]

        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            model = self._initialized_model(mock_llama)
            result = model.generate("prompt", max_tokens=100)

        assert result == "full response"
        assert mock_llama.return_value.call_count == 2
        # Second call uses doubled max_tokens
        second_call_kwargs = mock_llama.return_value.call_args_list[1][1]
        assert second_call_kwargs["max_tokens"] == 200

    def test_generate_raises_token_exhaustion_error_after_failed_retry(self) -> None:
        exhausted = _make_response("", finish_reason="length")
        mock_llama = MagicMock()
        mock_llama.return_value.side_effect = [exhausted, exhausted]

        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            model = self._initialized_model(mock_llama)
            with pytest.raises(TokenExhaustionError, match="exhausted token budget"):
                model.generate("prompt", max_tokens=100)

    def test_generate_propagates_unexpected_exceptions(self) -> None:
        mock_llama = MagicMock()
        mock_llama.return_value.side_effect = OSError("disk error")

        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            model = self._initialized_model(mock_llama)
            with pytest.raises(OSError, match="disk error"):
                model.generate("prompt")


# ---------------------------------------------------------------------------
# cleanup()
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_cleanup_sets_client_to_none(self) -> None:
        mock_llama = MagicMock()
        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            model = LlamaCppTextModel(_make_config())
            model.initialize()
            model.cleanup()

        assert model.client is None

    def test_cleanup_sets_initialized_to_false(self) -> None:
        mock_llama = MagicMock()
        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            model = LlamaCppTextModel(_make_config())
            model.initialize()
            assert model.is_initialized
            model.cleanup()

        assert not model.is_initialized

    def test_cleanup_calls_close_on_client(self) -> None:
        """cleanup() must call client.close() to deterministically free native resources."""
        mock_llama = MagicMock()
        with (
            patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True),
            patch("file_organizer.models.llama_cpp_text_model.Llama", mock_llama),
        ):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            model = LlamaCppTextModel(_make_config())
            model.initialize()
            client = model.client  # capture before cleanup nulls it
            model.cleanup()

        client.close.assert_called_once()


# ---------------------------------------------------------------------------
# _device_to_gpu_layers()
# ---------------------------------------------------------------------------


class TestDeviceToGpuLayers:
    def _model(self, device: DeviceType, extra_params: dict[str, Any] | None = None) -> Any:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            return LlamaCppTextModel(_make_config(device=device, extra_params=extra_params))

    def test_cuda_maps_to_minus_one(self) -> None:
        assert self._model(DeviceType.CUDA)._device_to_gpu_layers() == -1

    def test_mps_maps_to_minus_one(self) -> None:
        assert self._model(DeviceType.MPS)._device_to_gpu_layers() == -1

    def test_metal_maps_to_minus_one(self) -> None:
        assert self._model(DeviceType.METAL)._device_to_gpu_layers() == -1

    def test_cpu_maps_to_zero(self) -> None:
        assert self._model(DeviceType.CPU)._device_to_gpu_layers() == 0

    def test_auto_maps_to_zero(self) -> None:
        assert self._model(DeviceType.AUTO)._device_to_gpu_layers() == 0

    def test_extra_params_n_gpu_layers_overrides_device(self) -> None:
        model = self._model(DeviceType.CUDA, extra_params={"n_gpu_layers": 4})
        assert model._device_to_gpu_layers() == 4

    def test_extra_params_zero_overrides_gpu_device(self) -> None:
        model = self._model(DeviceType.CUDA, extra_params={"n_gpu_layers": 0})
        assert model._device_to_gpu_layers() == 0


# ---------------------------------------------------------------------------
# get_default_config()
# ---------------------------------------------------------------------------


class TestGetDefaultConfig:
    def test_returns_model_config_with_llama_cpp_provider(self) -> None:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            cfg = LlamaCppTextModel.get_default_config("/model.gguf")

        assert cfg.provider == "llama_cpp"
        assert cfg.model_type == ModelType.TEXT
        assert cfg.model_path == "/model.gguf"

    def test_default_config_has_sensible_defaults(self) -> None:
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            cfg = LlamaCppTextModel.get_default_config()

        assert cfg.temperature == 0.5
        assert cfg.max_tokens == 3000
        assert cfg.context_window == 4096

    def test_default_config_empty_model_path_is_allowed(self) -> None:
        """Empty path is valid at config construction; validated at LlamaCppTextModel() call."""
        with patch("file_organizer.models.llama_cpp_text_model.LLAMA_CPP_AVAILABLE", True):
            from file_organizer.models.llama_cpp_text_model import LlamaCppTextModel

            cfg = LlamaCppTextModel.get_default_config()

        assert cfg.model_path == ""
