"""Unit tests for config.provider_env — env var to ModelConfig mapping."""

from __future__ import annotations

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
