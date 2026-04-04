"""Coverage tests for config.manager module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from file_organizer.config.manager import ConfigManager
from file_organizer.config.schema import AppConfig, ModelPreset, UpdateSettings

pytestmark = pytest.mark.unit


class TestConfigManagerInit:
    def test_default_config_dir(self):
        mgr = ConfigManager()
        assert mgr.config_dir is not None

    def test_custom_config_dir(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.config_dir == tmp_path


class TestConfigManagerLoad:
    def test_load_missing_file_returns_defaults(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("default")
        assert cfg.profile_name == "default"

    def test_load_invalid_yaml_returns_defaults(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("{{invalid yaml")
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("default")
        assert cfg.profile_name == "default"

    def test_load_non_dict_returns_defaults(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump("just a string"))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("default")
        assert cfg.profile_name == "default"

    def test_load_missing_profile_returns_defaults(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"profiles": {"other": {}}}))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("default")
        assert cfg.profile_name == "default"

    def test_load_valid_profile(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        data = {
            "profiles": {
                "custom": {
                    "version": "2.0",
                    "default_methodology": "para",
                    "models": {"temperature": 0.5},
                }
            }
        }
        config_path.write_text(yaml.dump(data))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("custom")
        assert cfg.profile_name == "custom"
        assert cfg.default_methodology == "para"
        assert cfg.models.temperature == 0.5

    def test_load_non_dict_models_uses_default(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        data = {"profiles": {"test": {"models": "not-a-dict"}}}
        config_path.write_text(yaml.dump(data))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("test")
        assert isinstance(cfg.models, ModelPreset)

    def test_load_non_dict_updates_uses_default(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        data = {"profiles": {"test": {"updates": "not-a-dict"}}}
        config_path.write_text(yaml.dump(data))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("test")
        assert isinstance(cfg.updates, UpdateSettings)


class TestConfigManagerSave:
    def test_save_creates_dir_and_file(self, tmp_path):
        config_dir = tmp_path / "subdir"
        mgr = ConfigManager(config_dir=config_dir)
        cfg = AppConfig(profile_name="test")
        mgr.save(cfg)
        assert (config_dir / "config.yaml").exists()

    def test_save_preserves_other_profiles(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        cfg1 = AppConfig(profile_name="p1")
        cfg2 = AppConfig(profile_name="p2")
        mgr.save(cfg1)
        mgr.save(cfg2)

        profiles = mgr.list_profiles()
        assert "p1" in profiles
        assert "p2" in profiles

    def test_save_with_profile_override(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(profile_name="original")
        mgr.save(cfg, profile="overridden")

        profiles = mgr.list_profiles()
        assert "overridden" in profiles

    @pytest.mark.ci
    def test_save_overwrites_invalid_existing(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text("invalid yaml: {{")
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(profile_name="test")
        mgr.save(cfg)

        loaded = mgr.load("test")
        assert loaded.profile_name == "test"


class TestConfigManagerListProfiles:
    def test_empty_when_no_file(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.list_profiles() == []

    def test_empty_on_invalid_yaml(self, tmp_path):
        (tmp_path / "config.yaml").write_text("{{bad")
        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.list_profiles() == []

    def test_empty_on_non_dict(self, tmp_path):
        (tmp_path / "config.yaml").write_text(yaml.dump("string"))
        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.list_profiles() == []

    def test_empty_on_non_dict_profiles(self, tmp_path):
        (tmp_path / "config.yaml").write_text(yaml.dump({"profiles": "not-dict"}))
        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.list_profiles() == []

    def test_returns_sorted_names(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="z"))
        mgr.save(AppConfig(profile_name="a"))
        assert mgr.list_profiles() == ["a", "z"]


class TestConfigManagerDeleteProfile:
    def test_delete_existing(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(profile_name="doomed"))
        assert mgr.delete_profile("doomed") is True
        assert "doomed" not in mgr.list_profiles()

    def test_delete_nonexistent(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.delete_profile("nope") is False

    def test_delete_no_file(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.delete_profile("any") is False

    @pytest.mark.ci
    def test_delete_invalid_yaml(self, tmp_path):
        (tmp_path / "config.yaml").write_text("{{bad")
        mgr = ConfigManager(config_dir=tmp_path)
        assert mgr.delete_profile("any") is False


class TestConfigManagerModuleDelegation:
    def test_to_text_model_config(self):
        mgr = ConfigManager()
        cfg = AppConfig()
        model_cfg = mgr.to_text_model_config(cfg)
        assert model_cfg.name == cfg.models.text_model

    def test_to_vision_model_config(self):
        mgr = ConfigManager()
        cfg = AppConfig()
        model_cfg = mgr.to_vision_model_config(cfg)
        assert model_cfg.name == cfg.models.vision_model

    @patch("file_organizer.config.manager.WatcherConfig", create=True)
    def test_to_watcher_config(self, mock_watcher_cls):
        with patch("file_organizer.watcher.config.WatcherConfig", mock_watcher_cls, create=True):
            mgr = ConfigManager()
            cfg = AppConfig(watcher={"poll_interval": 2})
            mgr.to_watcher_config(cfg)

    def test_to_daemon_config(self):
        mgr = ConfigManager()
        cfg = AppConfig(daemon={"poll_interval": 2})
        result = mgr.to_daemon_config(cfg)
        assert result.poll_interval == 2

    def test_to_daemon_config_with_paths(self):
        mgr = ConfigManager()
        cfg = AppConfig(
            daemon={
                "watch_directories": ["/tmp/a"],
                "output_directory": "/tmp/out",
            }
        )
        result = mgr.to_daemon_config(cfg)
        assert Path("/tmp/a") in result.watch_directories

    def test_config_to_dict_includes_overrides(self):
        mgr = ConfigManager()
        cfg = AppConfig(watcher={"poll": 1}, daemon={"poll_interval": 2})
        d = mgr.config_to_dict(cfg)
        assert "watcher" in d
        assert "daemon" in d

    def test_config_to_dict_excludes_none_overrides(self):
        mgr = ConfigManager()
        cfg = AppConfig()
        d = mgr.config_to_dict(cfg)
        assert "watcher" not in d
