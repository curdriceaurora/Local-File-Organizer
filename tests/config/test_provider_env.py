"""Unit tests for config.provider_env — env var to ModelConfig mapping."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.config.provider_env import get_current_provider, get_model_configs_from_env
from file_organizer.models.base import ModelType
from file_organizer.models.text_model import TextModel
from file_organizer.models.vision_model import VisionModel

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# get_current_provider
# ---------------------------------------------------------------------------


class TestGetCurrentProvider:
    def test_defaults_to_ollama_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FO_PROVIDER", raising=False)

        assert get_current_provider() == "ollama"

    def test_returns_openai_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "openai")

        assert get_current_provider() == "openai"

    def test_returns_ollama_when_set_explicitly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "ollama")

        assert get_current_provider() == "ollama"

    def test_returns_mlx_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "mlx")

        assert get_current_provider() == "mlx"

    def test_falls_back_to_ollama_on_unknown_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "anthropic")

        # Should not raise — returns safe default
        assert get_current_provider() == "ollama"

    def test_strips_whitespace(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "  openai  ")

        assert get_current_provider() == "openai"

    def test_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "OPENAI")

        assert get_current_provider() == "openai"


# ---------------------------------------------------------------------------
# get_model_configs_from_env — ollama path
# ---------------------------------------------------------------------------


class TestGetModelConfigsFromEnvOllama:
    def test_returns_ollama_defaults_when_provider_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FO_PROVIDER", raising=False)
        expected_text = TextModel.get_default_config()
        expected_vision = VisionModel.get_default_config()

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.name == expected_text.name
        assert text_cfg.provider == "ollama"
        assert vision_cfg.name == expected_vision.name
        assert vision_cfg.provider == "ollama"

    def test_returned_configs_have_correct_model_types(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FO_PROVIDER", raising=False)

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.model_type == ModelType.TEXT
        assert vision_cfg.model_type == ModelType.VISION


# ---------------------------------------------------------------------------
# get_model_configs_from_env — openai path
# ---------------------------------------------------------------------------


class TestGetModelConfigsFromEnvOpenAI:
    def test_openai_provider_sets_provider_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "openai")
        monkeypatch.setenv("FO_OPENAI_API_KEY", "sk-abc")
        monkeypatch.delenv("FO_OPENAI_BASE_URL", raising=False)
        monkeypatch.delenv("FO_OPENAI_MODEL", raising=False)
        monkeypatch.delenv("FO_OPENAI_VISION_MODEL", raising=False)

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.provider == "openai"
        assert vision_cfg.provider == "openai"

    def test_api_key_propagated_to_both_configs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "openai")
        monkeypatch.setenv("FO_OPENAI_API_KEY", "sk-secret")
        monkeypatch.delenv("FO_OPENAI_BASE_URL", raising=False)

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.api_key == "sk-secret"
        assert vision_cfg.api_key == "sk-secret"

    def test_base_url_propagated_to_both_configs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "openai")
        monkeypatch.setenv("FO_OPENAI_BASE_URL", "http://localhost:1234/v1")
        monkeypatch.delenv("FO_OPENAI_API_KEY", raising=False)

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.api_base_url == "http://localhost:1234/v1"
        assert vision_cfg.api_base_url == "http://localhost:1234/v1"

    def test_custom_text_model_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "openai")
        monkeypatch.setenv("FO_OPENAI_MODEL", "gpt-4o")
        monkeypatch.delenv("FO_OPENAI_VISION_MODEL", raising=False)
        monkeypatch.delenv("FO_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("FO_OPENAI_BASE_URL", raising=False)

        text_cfg, _ = get_model_configs_from_env()

        assert text_cfg.name == "gpt-4o"

    def test_vision_model_falls_back_to_text_model_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FO_PROVIDER", "openai")
        monkeypatch.setenv("FO_OPENAI_MODEL", "gpt-4o")
        monkeypatch.delenv("FO_OPENAI_VISION_MODEL", raising=False)
        monkeypatch.delenv("FO_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("FO_OPENAI_BASE_URL", raising=False)

        _, vision_cfg = get_model_configs_from_env()

        assert vision_cfg.name == "gpt-4o"

    def test_separate_vision_model_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "openai")
        monkeypatch.setenv("FO_OPENAI_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("FO_OPENAI_VISION_MODEL", "gpt-4o")
        monkeypatch.delenv("FO_OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("FO_OPENAI_BASE_URL", raising=False)

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.name == "gpt-4o-mini"
        assert vision_cfg.name == "gpt-4o"

    def test_model_types_correct_for_openai_configs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "openai")
        monkeypatch.setenv("FO_OPENAI_API_KEY", "sk-test")

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.model_type == ModelType.TEXT
        assert vision_cfg.model_type == ModelType.VISION


# ---------------------------------------------------------------------------
# get_model_configs_from_env — mlx path
# ---------------------------------------------------------------------------


class TestGetModelConfigsFromEnvMLX:
    def test_mlx_provider_sets_provider_field(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "mlx")
        monkeypatch.setenv("FO_MLX_MODEL_PATH", "mlx-community/Qwen2.5-3B-Instruct-4bit")

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.provider == "mlx"
        assert vision_cfg.provider == "mlx"

    def test_mlx_model_path_propagates_to_text_and_vision(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FO_PROVIDER", "mlx")
        monkeypatch.setenv("FO_MLX_MODEL_PATH", "/models/mlx")

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.model_path == "/models/mlx"
        assert vision_cfg.model_path == "/models/mlx"

    def test_missing_mlx_model_path_does_not_crash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "mlx")
        monkeypatch.delenv("FO_MLX_MODEL_PATH", raising=False)

        with patch("file_organizer.config.provider_env.logger.warning") as mock_warning:
            text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.provider == "mlx"
        assert vision_cfg.provider == "mlx"
        assert text_cfg.model_path == ""
        assert vision_cfg.model_path == ""
        warning_messages = " ".join(str(call.args[0]) for call in mock_warning.call_args_list)
        assert "FO_MLX_MODEL_PATH" in warning_messages

    def test_model_types_correct_for_mlx_configs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "mlx")
        monkeypatch.setenv("FO_MLX_MODEL_PATH", "mlx-community/Qwen2.5-3B-Instruct-4bit")

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.model_type == ModelType.TEXT
        assert vision_cfg.model_type == ModelType.VISION


# ---------------------------------------------------------------------------
# get_model_configs_from_env — llama_cpp path
# ---------------------------------------------------------------------------


class TestGetModelConfigsFromEnvLlamaCpp:
    def test_llama_cpp_provider_and_model_path_propagate(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FO_PROVIDER", "llama_cpp")
        monkeypatch.setenv("FO_LLAMA_CPP_MODEL_PATH", "/models/qwen.gguf")
        monkeypatch.setenv("FO_LLAMA_CPP_N_GPU_LAYERS", "20")

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.provider == "llama_cpp"
        assert vision_cfg.provider == "llama_cpp"
        assert text_cfg.model_path == "/models/qwen.gguf"
        assert vision_cfg.model_path == "/models/qwen.gguf"
        assert text_cfg.model_type == ModelType.TEXT
        assert vision_cfg.model_type == ModelType.VISION

    def test_llama_cpp_n_gpu_layers_parsed_into_extra_params(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FO_PROVIDER", "llama_cpp")
        monkeypatch.setenv("FO_LLAMA_CPP_MODEL_PATH", "/models/qwen.gguf")
        monkeypatch.setenv("FO_LLAMA_CPP_N_GPU_LAYERS", "35")

        text_cfg, _ = get_model_configs_from_env()

        assert text_cfg.extra_params.get("n_gpu_layers") == 35

    def test_llama_cpp_without_gpu_layers_has_empty_extra_params(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FO_PROVIDER", "llama_cpp")
        monkeypatch.setenv("FO_LLAMA_CPP_MODEL_PATH", "/models/qwen.gguf")
        monkeypatch.delenv("FO_LLAMA_CPP_N_GPU_LAYERS", raising=False)

        text_cfg, _ = get_model_configs_from_env()

        assert "n_gpu_layers" not in text_cfg.extra_params

    def test_llama_cpp_invalid_gpu_layers_is_ignored_with_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FO_PROVIDER", "llama_cpp")
        monkeypatch.setenv("FO_LLAMA_CPP_MODEL_PATH", "/models/qwen.gguf")
        monkeypatch.setenv("FO_LLAMA_CPP_N_GPU_LAYERS", "not-an-int")

        with patch("file_organizer.config.provider_env.logger.warning") as mock_warning:
            text_cfg, _ = get_model_configs_from_env()

        # Bad value is dropped, not fatal.
        assert "n_gpu_layers" not in text_cfg.extra_params
        messages = " ".join(str(call.args[0]) for call in mock_warning.call_args_list)
        assert "FO_LLAMA_CPP_N_GPU_LAYERS" in messages

    def test_llama_cpp_missing_model_path_warns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "llama_cpp")
        monkeypatch.delenv("FO_LLAMA_CPP_MODEL_PATH", raising=False)

        with patch("file_organizer.config.provider_env.logger.warning") as mock_warning:
            text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.provider == "llama_cpp"
        assert text_cfg.model_path == ""
        assert vision_cfg.model_path == ""
        messages = " ".join(str(call.args[0]) for call in mock_warning.call_args_list)
        assert "FO_LLAMA_CPP_MODEL_PATH" in messages


# ---------------------------------------------------------------------------
# get_model_configs_from_env — claude path
# ---------------------------------------------------------------------------


class TestGetModelConfigsFromEnvClaude:
    def test_claude_provider_and_api_key_propagate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "claude")
        monkeypatch.setenv("FO_CLAUDE_API_KEY", "sk-ant-secret")
        monkeypatch.delenv("FO_CLAUDE_MODEL", raising=False)
        monkeypatch.delenv("FO_CLAUDE_VISION_MODEL", raising=False)

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.provider == "claude"
        assert vision_cfg.provider == "claude"
        assert text_cfg.api_key == "sk-ant-secret"
        assert vision_cfg.api_key == "sk-ant-secret"
        assert text_cfg.model_type == ModelType.TEXT
        assert vision_cfg.model_type == ModelType.VISION

    def test_claude_defaults_to_builtin_model_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "claude")
        monkeypatch.setenv("FO_CLAUDE_API_KEY", "sk-ant-secret")
        monkeypatch.delenv("FO_CLAUDE_MODEL", raising=False)
        monkeypatch.delenv("FO_CLAUDE_VISION_MODEL", raising=False)

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.name.startswith("claude-")
        # Vision falls back to the text model name when unset.
        assert vision_cfg.name == text_cfg.name

    def test_claude_custom_text_and_vision_models(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "claude")
        monkeypatch.setenv("FO_CLAUDE_API_KEY", "sk-ant-secret")
        monkeypatch.setenv("FO_CLAUDE_MODEL", "claude-3-5-haiku-20241022")
        monkeypatch.setenv("FO_CLAUDE_VISION_MODEL", "claude-3-5-sonnet-20241022")

        text_cfg, vision_cfg = get_model_configs_from_env()

        assert text_cfg.name == "claude-3-5-haiku-20241022"
        assert vision_cfg.name == "claude-3-5-sonnet-20241022"

    def test_claude_falls_back_to_anthropic_api_key_without_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When ANTHROPIC_API_KEY is present the SDK picks it up, so no warning."""
        monkeypatch.setenv("FO_PROVIDER", "claude")
        monkeypatch.delenv("FO_CLAUDE_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-sdk")

        with patch("file_organizer.config.provider_env.logger.warning") as mock_warning:
            text_cfg, _ = get_model_configs_from_env()

        # FO_CLAUDE_API_KEY is unset, so the config api_key is None (SDK reads ANTHROPIC_API_KEY).
        assert text_cfg.api_key is None
        assert text_cfg.provider == "claude"
        mock_warning.assert_not_called()

    def test_claude_missing_all_keys_warns(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FO_PROVIDER", "claude")
        monkeypatch.delenv("FO_CLAUDE_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        with patch("file_organizer.config.provider_env.logger.warning") as mock_warning:
            text_cfg, _ = get_model_configs_from_env()

        assert text_cfg.api_key is None
        messages = " ".join(str(call.args[0]) for call in mock_warning.call_args_list)
        assert "FO_CLAUDE_API_KEY" in messages
