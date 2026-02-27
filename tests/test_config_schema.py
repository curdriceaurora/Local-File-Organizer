"""Tests for AppConfig/ModelPreset schema validation and round-trips."""

from __future__ import annotations

import pytest

from file_organizer.config.schema import AppConfig, ModelPreset, UpdateSettings

# ---------------------------------------------------------------------------
# ModelPreset
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelPreset:
    """Tests for the ModelPreset dataclass."""

    def test_default_values(self) -> None:
        preset = ModelPreset()
        assert preset.text_model == "qwen2.5:3b-instruct-q4_K_M"
        assert preset.vision_model == "qwen2.5vl:7b-q4_K_M"
        assert preset.temperature == 0.5
        assert preset.max_tokens == 3000
        assert preset.device == "auto"
        assert preset.framework == "ollama"

    def test_custom_values(self) -> None:
        preset = ModelPreset(
            text_model="custom:3b",
            vision_model="vis:7b",
            temperature=0.8,
            max_tokens=4096,
            device="cuda",
            framework="llama_cpp",
        )
        assert preset.text_model == "custom:3b"
        assert preset.temperature == 0.8
        assert preset.device == "cuda"

    def test_equality(self) -> None:
        a = ModelPreset(text_model="m1", temperature=0.5)
        b = ModelPreset(text_model="m1", temperature=0.5)
        assert a == b

    def test_inequality(self) -> None:
        a = ModelPreset(temperature=0.5)
        b = ModelPreset(temperature=0.9)
        assert a != b


# ---------------------------------------------------------------------------
# AppConfig
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAppConfig:
    """Tests for the AppConfig dataclass."""

    def test_default_values(self) -> None:
        cfg = AppConfig()
        assert cfg.profile_name == "default"
        assert cfg.version == "1.0"
        assert cfg.default_methodology == "none"
        assert isinstance(cfg.models, ModelPreset)
        assert isinstance(cfg.updates, UpdateSettings)

    def test_custom_profile(self) -> None:
        cfg = AppConfig(profile_name="work", default_methodology="para")
        assert cfg.profile_name == "work"
        assert cfg.default_methodology == "para"

    def test_with_custom_models(self) -> None:
        models = ModelPreset(text_model="fast:1b", temperature=0.3)
        cfg = AppConfig(models=models)
        assert cfg.models.text_model == "fast:1b"
        assert cfg.models.temperature == 0.3

    def test_with_custom_updates(self) -> None:
        updates = UpdateSettings(check_on_startup=False, interval_hours=48)
        cfg = AppConfig(updates=updates)
        assert cfg.updates.check_on_startup is False
        assert cfg.updates.interval_hours == 48

    def test_optional_module_configs_default_none(self) -> None:
        cfg = AppConfig()
        assert cfg.watcher is None
        assert cfg.daemon is None
        assert cfg.parallel is None
        assert cfg.pipeline is None
        assert cfg.events is None
        assert cfg.deploy is None
        assert cfg.para is None
        assert cfg.johnny_decimal is None

    def test_module_config_override(self) -> None:
        cfg = AppConfig(
            daemon={"auto_start": True, "port": 8080},
            para={"auto_categorize": True},
        )
        assert cfg.daemon is not None
        assert cfg.daemon["auto_start"] is True
        assert cfg.para is not None
        assert cfg.para["auto_categorize"] is True

    def test_equality(self) -> None:
        a = AppConfig(profile_name="x")
        b = AppConfig(profile_name="x")
        assert a == b

    def test_inequality(self) -> None:
        a = AppConfig(profile_name="x")
        b = AppConfig(profile_name="y")
        assert a != b


# ---------------------------------------------------------------------------
# Schema validation edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSchemaEdgeCases:
    """Edge cases and boundary conditions."""

    def test_temperature_boundary_zero(self) -> None:
        preset = ModelPreset(temperature=0.0)
        assert preset.temperature == 0.0

    def test_temperature_boundary_one(self) -> None:
        preset = ModelPreset(temperature=1.0)
        assert preset.temperature == 1.0

    def test_max_tokens_boundary(self) -> None:
        preset = ModelPreset(max_tokens=1)
        assert preset.max_tokens == 1

    def test_empty_model_name(self) -> None:
        """Empty model name should be storable (validation is at runtime)."""
        preset = ModelPreset(text_model="")
        assert preset.text_model == ""

    def test_nested_config_independence(self) -> None:
        """Modifying one AppConfig's models should not affect another."""
        cfg1 = AppConfig()
        cfg2 = AppConfig()
        cfg1.models.temperature = 0.99
        assert cfg2.models.temperature == 0.5


# ---------------------------------------------------------------------------
# Update settings
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestUpdateSettings:
    def test_defaults(self) -> None:
        updates = UpdateSettings()
        assert updates.check_on_startup is True
        assert updates.interval_hours == 24
        assert updates.include_prereleases is False
        assert updates.repo == "curdriceaurora/Local-File-Organizer"
