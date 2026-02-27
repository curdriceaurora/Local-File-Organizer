"""Tests for configuration schema dataclasses."""

from __future__ import annotations

import pytest

from file_organizer.config.schema import AppConfig, ModelPreset, UpdateSettings


@pytest.mark.unit
class TestModelPreset:
    """Test suite for ModelPreset dataclass."""

    def test_defaults(self) -> None:
        """All defaults should be sensible out of the box."""
        preset = ModelPreset()
        assert preset.text_model == "qwen2.5:3b-instruct-q4_K_M"
        assert preset.vision_model == "qwen2.5vl:7b-q4_K_M"
        assert preset.temperature == 0.5
        assert preset.max_tokens == 3000
        assert preset.device == "auto"
        assert preset.framework == "ollama"

    def test_custom_values(self) -> None:
        """Custom values should override defaults."""
        preset = ModelPreset(
            text_model="llama3:8b",
            vision_model="llava:13b",
            temperature=0.8,
            max_tokens=4096,
            device="cuda",
            framework="llama_cpp",
        )
        assert preset.text_model == "llama3:8b"
        assert preset.vision_model == "llava:13b"
        assert preset.temperature == 0.8
        assert preset.max_tokens == 4096
        assert preset.device == "cuda"
        assert preset.framework == "llama_cpp"

    def test_partial_override(self) -> None:
        """Partially overriding fields keeps other defaults intact."""
        preset = ModelPreset(temperature=0.9)
        assert preset.temperature == 0.9
        assert preset.text_model == "qwen2.5:3b-instruct-q4_K_M"
        assert preset.device == "auto"


@pytest.mark.unit
class TestUpdateSettings:
    """Test suite for UpdateSettings dataclass."""

    def test_defaults(self) -> None:
        """Default update settings should be sensible."""
        settings = UpdateSettings()
        assert settings.check_on_startup is True
        assert settings.interval_hours == 24
        assert settings.include_prereleases is False
        assert settings.repo == "curdriceaurora/Local-File-Organizer"

    def test_custom_values(self) -> None:
        """Custom update settings should override defaults."""
        settings = UpdateSettings(
            check_on_startup=False,
            interval_hours=12,
            include_prereleases=True,
            repo="myuser/myrepo",
        )
        assert settings.check_on_startup is False
        assert settings.interval_hours == 12
        assert settings.include_prereleases is True
        assert settings.repo == "myuser/myrepo"


@pytest.mark.unit
class TestAppConfig:
    """Test suite for AppConfig dataclass."""

    def test_defaults(self) -> None:
        """AppConfig() with no args should produce a valid default config."""
        config = AppConfig()
        assert config.profile_name == "default"
        assert config.version == "1.0"
        assert config.default_methodology == "none"
        assert isinstance(config.models, ModelPreset)
        assert isinstance(config.updates, UpdateSettings)

    def test_module_overrides_default_to_none(self) -> None:
        """Optional module configs should default to None."""
        config = AppConfig()
        assert config.watcher is None
        assert config.daemon is None
        assert config.parallel is None
        assert config.pipeline is None
        assert config.events is None
        assert config.deploy is None
        assert config.para is None
        assert config.johnny_decimal is None

    def test_custom_profile(self) -> None:
        """Custom profile name and methodology."""
        config = AppConfig(profile_name="work", default_methodology="para")
        assert config.profile_name == "work"
        assert config.default_methodology == "para"

    def test_nested_model_preset(self) -> None:
        """Nested ModelPreset should be accessible."""
        custom_models = ModelPreset(temperature=0.3, device="mps")
        config = AppConfig(models=custom_models)
        assert config.models.temperature == 0.3
        assert config.models.device == "mps"

    def test_nested_update_settings(self) -> None:
        """Nested UpdateSettings should be accessible."""
        custom_updates = UpdateSettings(interval_hours=6)
        config = AppConfig(updates=custom_updates)
        assert config.updates.interval_hours == 6

    def test_module_override_dicts(self) -> None:
        """Module-specific dict overrides should be stored as-is."""
        config = AppConfig(
            watcher={"poll_interval": 5},
            daemon={"auto_start": True},
            parallel={"max_workers": 4},
            pipeline={"batch_size": 10},
            events={"buffer_size": 100},
            deploy={"target": "docker"},
            para={"auto_archive": True},
            johnny_decimal={"root": "10-19"},
        )
        assert config.watcher == {"poll_interval": 5}
        assert config.daemon == {"auto_start": True}
        assert config.parallel == {"max_workers": 4}
        assert config.pipeline == {"batch_size": 10}
        assert config.events == {"buffer_size": 100}
        assert config.deploy == {"target": "docker"}
        assert config.para == {"auto_archive": True}
        assert config.johnny_decimal == {"root": "10-19"}

    def test_models_factory_creates_independent_instances(self) -> None:
        """Each AppConfig should get its own ModelPreset instance."""
        config1 = AppConfig()
        config2 = AppConfig()
        assert config1.models is not config2.models

    def test_updates_factory_creates_independent_instances(self) -> None:
        """Each AppConfig should get its own UpdateSettings instance."""
        config1 = AppConfig()
        config2 = AppConfig()
        assert config1.updates is not config2.updates
