"""Tests for config profile → FileOrganizer model config integration.

Covers issue #724 — configured model overrides from profile are ignored.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from file_organizer.config.provider_env import (
    _get_model_configs_from_profile,
    get_model_configs,
)
from file_organizer.config.schema import AppConfig, ModelPreset
from file_organizer.models.base import ModelConfig, ModelType

pytestmark = [pytest.mark.unit, pytest.mark.ci, pytest.mark.smoke]


class TestGetModelConfigsFromProfile:
    """Verify _get_model_configs_from_profile reads saved profiles."""

    def test_returns_none_when_no_config_file(self) -> None:
        with patch("file_organizer.config.manager.ConfigManager") as mock_cls:
            mgr = mock_cls.return_value
            mgr.load.return_value = AppConfig()  # all defaults
            result = _get_model_configs_from_profile("default")
        assert result is None

    def test_returns_none_when_models_are_defaults(self) -> None:
        with patch("file_organizer.config.manager.ConfigManager") as mock_cls:
            mgr = mock_cls.return_value
            mgr.load.return_value = AppConfig(
                models=ModelPreset()  # defaults
            )
            result = _get_model_configs_from_profile("default")
        assert result is None

    def test_returns_configs_when_text_model_overridden(self) -> None:
        """Profile with custom text model should be picked up."""
        custom_preset = ModelPreset(text_model="custom-text:latest")
        app_cfg = AppConfig(models=custom_preset)

        text_cfg = ModelConfig(name="custom-text:latest", model_type=ModelType.TEXT)
        vision_cfg = ModelConfig(name="qwen2.5vl:7b-q4_K_M", model_type=ModelType.VISION)

        with patch("file_organizer.config.manager.ConfigManager") as mock_cls:
            mgr = mock_cls.return_value
            mgr.load.return_value = app_cfg
            mgr.to_text_model_config.return_value = text_cfg
            mgr.to_vision_model_config.return_value = vision_cfg

            result = _get_model_configs_from_profile("default")

        assert result is not None
        text, vision = result
        assert text.name == "custom-text:latest"
        assert vision.name == "qwen2.5vl:7b-q4_K_M"

    def test_returns_configs_when_vision_model_overridden(self) -> None:
        custom_preset = ModelPreset(vision_model="custom-vision:latest")
        app_cfg = AppConfig(models=custom_preset)

        text_cfg = ModelConfig(name="qwen2.5:3b-instruct-q4_K_M", model_type=ModelType.TEXT)
        vision_cfg = ModelConfig(name="custom-vision:latest", model_type=ModelType.VISION)

        with patch("file_organizer.config.manager.ConfigManager") as mock_cls:
            mgr = mock_cls.return_value
            mgr.load.return_value = app_cfg
            mgr.to_text_model_config.return_value = text_cfg
            mgr.to_vision_model_config.return_value = vision_cfg

            result = _get_model_configs_from_profile("default")

        assert result is not None
        _, vision = result
        assert vision.name == "custom-vision:latest"

    def test_returns_none_on_exception(self) -> None:
        with patch(
            "file_organizer.config.manager.ConfigManager",
            side_effect=RuntimeError("broken"),
        ):
            result = _get_model_configs_from_profile("default")
        assert result is None


class TestGetModelConfigs:
    """Verify the priority cascade in get_model_configs()."""

    def test_env_provider_takes_precedence_over_profile(self) -> None:
        """When FO_PROVIDER is set, env config wins."""
        env = {
            "FO_PROVIDER": "openai",
            "FO_OPENAI_API_KEY": "sk-test",
            "FO_OPENAI_MODEL": "gpt-4o",
        }
        with patch.dict(os.environ, env, clear=False):
            text, _vision = get_model_configs()
        assert text.provider == "openai"
        assert text.name == "gpt-4o"

    def test_openai_env_vars_without_provider_fall_through(self) -> None:
        """FO_OPENAI_* vars alone (without FO_PROVIDER) don't trigger env-based config."""
        env = {"FO_OPENAI_MODEL": "custom-model"}
        clear_vars = {"FO_PROVIDER": ""}
        with patch.dict(os.environ, {**env, **clear_vars}, clear=False):
            text, _vision = get_model_configs()
        # Without FO_PROVIDER set, falls through to profile/defaults (Ollama)
        assert text.provider == "ollama"

    def test_profile_used_when_no_env_vars(self) -> None:
        """When no env vars are set, profile config is used."""
        profile_text = ModelConfig(name="profile-text:latest", model_type=ModelType.TEXT)
        profile_vision = ModelConfig(name="profile-vision:latest", model_type=ModelType.VISION)

        clean_env = {
            "FO_PROVIDER": "",
            "FO_OPENAI_MODEL": "",
            "FO_OPENAI_VISION_MODEL": "",
            "FO_OPENAI_API_KEY": "",
            "FO_PROFILE": "",
        }
        with (
            patch.dict(os.environ, clean_env, clear=False),
            patch(
                "file_organizer.config.provider_env._get_model_configs_from_profile",
                return_value=(profile_text, profile_vision),
            ),
        ):
            text, vision = get_model_configs()

        assert text.name == "profile-text:latest"
        assert vision.name == "profile-vision:latest"

    def test_defaults_when_no_env_and_no_profile(self) -> None:
        """When nothing is configured, Ollama defaults are used."""
        clean_env = {
            "FO_PROVIDER": "",
            "FO_OPENAI_MODEL": "",
            "FO_OPENAI_VISION_MODEL": "",
            "FO_OPENAI_API_KEY": "",
            "FO_PROFILE": "",
        }
        with (
            patch.dict(os.environ, clean_env, clear=False),
            patch(
                "file_organizer.config.provider_env._get_model_configs_from_profile",
                return_value=None,
            ),
        ):
            text, vision = get_model_configs()

        # Should be Ollama defaults
        assert text.provider == "ollama"
        assert vision.provider == "ollama"

    def test_fo_profile_env_var_selects_profile(self) -> None:
        """FO_PROFILE env var selects which profile to load."""
        profile_text = ModelConfig(name="work-text:latest", model_type=ModelType.TEXT)
        profile_vision = ModelConfig(name="work-vision:latest", model_type=ModelType.VISION)

        clean_env = {
            "FO_PROVIDER": "",
            "FO_OPENAI_MODEL": "",
            "FO_OPENAI_VISION_MODEL": "",
            "FO_OPENAI_API_KEY": "",
            "FO_PROFILE": "work",
        }
        with (
            patch.dict(os.environ, clean_env, clear=False),
            patch(
                "file_organizer.config.provider_env._get_model_configs_from_profile",
                return_value=(profile_text, profile_vision),
            ) as mock_load,
        ):
            text, _vision = get_model_configs()

        mock_load.assert_called_once_with("work")
        assert text.name == "work-text:latest"


class TestOrganizerUsesGetModelConfigs:
    """Verify FileOrganizer.__init__ uses get_model_configs (not just env)."""

    def test_organizer_loads_profile_config(self) -> None:
        """FileOrganizer without explicit configs should use get_model_configs."""
        profile_text = ModelConfig(name="profile-text:7b", model_type=ModelType.TEXT)
        profile_vision = ModelConfig(name="profile-vision:7b", model_type=ModelType.VISION)

        with patch(
            "file_organizer.config.provider_env.get_model_configs",
            return_value=(profile_text, profile_vision),
        ):
            from file_organizer.core.organizer import FileOrganizer

            org = FileOrganizer(dry_run=True)

        assert org.text_model_config.name == "profile-text:7b"
        assert org.vision_model_config.name == "profile-vision:7b"

    def test_organizer_explicit_config_overrides_profile(self) -> None:
        """Explicit ModelConfig params should take precedence."""
        explicit_text = ModelConfig(name="explicit-text", model_type=ModelType.TEXT)
        explicit_vision = ModelConfig(name="explicit-vision", model_type=ModelType.VISION)

        from file_organizer.core.organizer import FileOrganizer

        org = FileOrganizer(
            text_model_config=explicit_text,
            vision_model_config=explicit_vision,
            dry_run=True,
        )

        assert org.text_model_config.name == "explicit-text"
        assert org.vision_model_config.name == "explicit-vision"
