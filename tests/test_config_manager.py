"""Tests for ConfigManager and AppConfig."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from file_organizer.config.manager import ConfigManager
from file_organizer.config.schema import AppConfig, ModelPreset, UpdateSettings
from file_organizer.models.base import DeviceType, ModelType

# ---------------------------------------------------------------------------
# AppConfig / ModelPreset defaults
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAppConfigDefaults:
    """AppConfig should be constructable with zero arguments."""

    def test_default_construction(self) -> None:
        config = AppConfig()
        assert config.profile_name == "default"
        assert config.version == "1.0"
        assert config.default_methodology == "none"
        assert isinstance(config.models, ModelPreset)
        assert isinstance(config.updates, UpdateSettings)

    def test_model_preset_defaults(self) -> None:
        preset = ModelPreset()
        assert preset.text_model == "qwen2.5:3b-instruct-q4_K_M"
        assert preset.vision_model == "qwen2.5vl:7b-q4_K_M"
        assert preset.temperature == 0.5
        assert preset.max_tokens == 3000
        assert preset.device == "auto"
        assert preset.framework == "ollama"

    def test_module_overrides_default_to_none(self) -> None:
        config = AppConfig()
        assert config.watcher is None
        assert config.daemon is None
        assert config.parallel is None
        assert config.pipeline is None
        assert config.events is None
        assert config.deploy is None
        assert config.para is None
        assert config.johnny_decimal is None


# ---------------------------------------------------------------------------
# ConfigManager — load / save / list / delete
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConfigManagerLoadSave:
    """ConfigManager persistence round-trip."""

    def test_load_missing_file_returns_defaults(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path / "nonexistent")
        config = mgr.load()
        assert config.profile_name == "default"
        assert isinstance(config.models, ModelPreset)

    def test_save_creates_directory_and_file(self, tmp_path: Path) -> None:
        cfg_dir = tmp_path / "new_dir"
        mgr = ConfigManager(cfg_dir)
        mgr.save(AppConfig())

        config_file = cfg_dir / "config.yaml"
        assert config_file.exists()
        raw = yaml.safe_load(config_file.read_text())
        assert "profiles" in raw
        assert "default" in raw["profiles"]

    def test_round_trip(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path)
        original = AppConfig(
            profile_name="test",
            default_methodology="para",
            models=ModelPreset(
                text_model="custom-model:latest",
                temperature=0.8,
            ),
            updates=UpdateSettings(check_on_startup=False, interval_hours=72),
        )
        mgr.save(original, profile="test")
        loaded = mgr.load(profile="test")

        assert loaded.profile_name == "test"
        assert loaded.default_methodology == "para"
        assert loaded.models.text_model == "custom-model:latest"
        assert loaded.models.temperature == 0.8
        # Unset fields keep defaults
        assert loaded.models.vision_model == "qwen2.5vl:7b-q4_K_M"
        assert loaded.updates.check_on_startup is False
        assert loaded.updates.interval_hours == 72

    def test_save_preserves_other_profiles(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path)
        mgr.save(AppConfig(profile_name="a"), profile="a")
        mgr.save(AppConfig(profile_name="b"), profile="b")

        assert "a" in mgr.list_profiles()
        assert "b" in mgr.list_profiles()

    def test_load_invalid_yaml_returns_defaults(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("{{invalid yaml: [", encoding="utf-8")
        mgr = ConfigManager(tmp_path)
        config = mgr.load()
        assert config.profile_name == "default"

    def test_load_nondict_yaml_returns_defaults(self, tmp_path: Path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("42", encoding="utf-8")
        mgr = ConfigManager(tmp_path)
        config = mgr.load()
        assert config.profile_name == "default"


@pytest.mark.unit
class TestConfigManagerProfiles:
    """Profile listing and deletion."""

    def test_list_profiles_empty(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path / "empty")
        assert mgr.list_profiles() == []

    def test_list_profiles(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path)
        mgr.save(AppConfig(), profile="alpha")
        mgr.save(AppConfig(), profile="beta")
        assert mgr.list_profiles() == ["alpha", "beta"]

    def test_delete_profile(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path)
        mgr.save(AppConfig(), profile="doomed")
        assert "doomed" in mgr.list_profiles()
        assert mgr.delete_profile("doomed") is True
        assert "doomed" not in mgr.list_profiles()

    def test_delete_nonexistent_profile(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path)
        assert mgr.delete_profile("ghost") is False


# ---------------------------------------------------------------------------
# Module config delegation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelConfigDelegation:
    """ConfigManager.to_*_model_config() methods."""

    def test_to_text_model_config(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path)
        app_cfg = AppConfig(models=ModelPreset(text_model="my-text:latest", temperature=0.3))
        mc = mgr.to_text_model_config(app_cfg)
        assert mc.name == "my-text:latest"
        assert mc.model_type == ModelType.TEXT
        assert mc.temperature == 0.3
        assert mc.device == DeviceType.AUTO

    def test_to_vision_model_config(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path)
        app_cfg = AppConfig(models=ModelPreset(vision_model="my-vis:7b", device="mps"))
        mc = mgr.to_vision_model_config(app_cfg)
        assert mc.name == "my-vis:7b"
        assert mc.model_type == ModelType.VISION
        assert mc.device == DeviceType.MPS


@pytest.mark.unit
class TestModuleOverridesSerialization:
    """Module override dicts survive save/load."""

    def test_watcher_overrides_round_trip(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path)
        cfg = AppConfig(watcher={"recursive": False, "debounce_seconds": 5.0})
        mgr.save(cfg)
        loaded = mgr.load()
        assert loaded.watcher is not None
        assert loaded.watcher["recursive"] is False
        assert loaded.watcher["debounce_seconds"] == 5.0

    def test_none_overrides_not_serialized(self, tmp_path: Path) -> None:
        mgr = ConfigManager(tmp_path)
        cfg = AppConfig()
        mgr.save(cfg)
        raw = yaml.safe_load((tmp_path / "config.yaml").read_text(encoding="utf-8"))
        profile_data = raw["profiles"]["default"]
        assert "watcher" not in profile_data
        assert "daemon" not in profile_data
        assert "updates" in profile_data
