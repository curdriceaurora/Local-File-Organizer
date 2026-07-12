"""Coverage tests for config.manager module."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from file_organizer.config.manager import ConfigManager
from file_organizer.config.schema import (
    CURRENT_SCHEMA_VERSION,
    AppConfig,
    ModelPreset,
    UpdateSettings,
)

pytestmark = pytest.mark.unit

_MODULE_OVERRIDE_FIELD_NAMES = (
    "watcher",
    "daemon",
    "parallel",
    "pipeline",
    "events",
    "deploy",
    "para",
    "johnny_decimal",
)


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
                    "version": "1.0",
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
                "watch_directories": ["/tmp/a"],  # noqa: test-hardcoded-paths
                "output_directory": "/tmp/out",  # noqa: test-hardcoded-paths
            }
        )
        result = mgr.to_daemon_config(cfg)
        assert Path("/") / "tmp" / "a" in result.watch_directories  # noqa: test-hardcoded-paths

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


# ---------------------------------------------------------------------------
# Dynamic field-iteration serialization (see #1542):
# ``_config_to_dict`` walks ``dataclasses.fields(AppConfig)`` instead of
# listing every field by hand, so these tests pin down the per-field
# dispatch behaviour (excluded / version stamp / nested dataclass /
# module-override / plain passthrough) directly.
# ---------------------------------------------------------------------------


class TestConfigToDictFieldIteration:
    def test_excludes_profile_name(self):
        mgr = ConfigManager()
        cfg = AppConfig(profile_name="should-not-appear")
        d = mgr.config_to_dict(cfg)
        assert "profile_name" not in d

    def test_stamps_current_version_regardless_of_config_version(self):
        mgr = ConfigManager()
        cfg = AppConfig(version="0.1")
        d = mgr.config_to_dict(cfg)
        assert d["version"] == CURRENT_SCHEMA_VERSION

    def test_includes_plain_fields_verbatim(self):
        mgr = ConfigManager()
        cfg = AppConfig(
            default_methodology="para",
            default_input_dir="/tmp/in",  # noqa: test-hardcoded-paths
            default_output_dir="/tmp/out",  # noqa: test-hardcoded-paths
            setup_completed=True,
            setup_deferred=True,
        )
        d = mgr.config_to_dict(cfg)
        assert d["default_methodology"] == "para"
        assert d["default_input_dir"] == "/tmp/in"  # noqa: test-hardcoded-paths
        assert d["default_output_dir"] == "/tmp/out"  # noqa: test-hardcoded-paths
        assert d["setup_completed"] is True
        assert d["setup_deferred"] is True

    def test_nested_dataclasses_serialized_via_asdict(self):
        mgr = ConfigManager()
        models = ModelPreset(text_model="m", temperature=0.9)
        updates = UpdateSettings(check_on_startup=False)
        cfg = AppConfig(models=models, updates=updates)
        d = mgr.config_to_dict(cfg)
        assert d["models"] == asdict(models)
        assert d["updates"] == asdict(updates)

    @pytest.mark.parametrize("field_name", _MODULE_OVERRIDE_FIELD_NAMES)
    def test_all_module_overrides_excluded_when_none(self, field_name):
        mgr = ConfigManager()
        d = mgr.config_to_dict(AppConfig())
        assert field_name not in d

    @pytest.mark.parametrize("field_name", _MODULE_OVERRIDE_FIELD_NAMES)
    def test_all_module_overrides_included_when_set(self, field_name):
        mgr = ConfigManager()
        cfg = AppConfig(**{field_name: {"key": "value"}})
        d = mgr.config_to_dict(cfg)
        assert d[field_name] == {"key": "value"}


# ---------------------------------------------------------------------------
# Dynamic field-iteration deserialization (see #1542):
# ``_dict_to_config`` mirrors the serializer by walking
# ``dataclasses.fields(AppConfig)``, falling back to the dataclass default
# for any plain field absent from the on-disk data. Exercised through
# ``ConfigManager.load`` since ``_dict_to_config`` is a private staticmethod.
# ---------------------------------------------------------------------------


class TestDictToConfigFieldIteration:
    def test_missing_version_defaults_to_current(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"profiles": {"p": {}}}))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert cfg.version == CURRENT_SCHEMA_VERSION

    def test_float_version_normalized_to_str(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"profiles": {"p": {"version": 1.0}}}))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert cfg.version == "1.0"
        assert isinstance(cfg.version, str)

    def test_profile_name_comes_from_argument_not_data(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"profiles": {"p": {"profile_name": "wrong"}}}))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert cfg.profile_name == "p"

    def test_legacy_methodology_alias_normalized(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"profiles": {"p": {"default_methodology": "content_based"}}})
        )
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert cfg.default_methodology == "none"

    def test_invalid_methodology_falls_back_to_default(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"profiles": {"p": {"default_methodology": "bogus"}}}))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert cfg.default_methodology == "none"

    def test_missing_plain_fields_use_dataclass_defaults(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"profiles": {"p": {}}}))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert cfg.default_input_dir == ""
        assert cfg.default_output_dir == ""
        assert cfg.setup_completed is False
        assert cfg.setup_deferred is False

    def test_present_plain_fields_are_used(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "profiles": {
                        "p": {
                            "default_input_dir": "/tmp/in",  # noqa: test-hardcoded-paths
                            "default_output_dir": "/tmp/out",  # noqa: test-hardcoded-paths
                            "setup_completed": True,
                            "setup_deferred": True,
                        }
                    }
                }
            )
        )
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert cfg.default_input_dir == "/tmp/in"  # noqa: test-hardcoded-paths
        assert cfg.default_output_dir == "/tmp/out"  # noqa: test-hardcoded-paths
        assert cfg.setup_completed is True
        assert cfg.setup_deferred is True

    def test_models_filters_unknown_keys(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"profiles": {"p": {"models": {"temperature": 0.7, "bogus_field": "x"}}}})
        )
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert cfg.models.temperature == 0.7
        assert not hasattr(cfg.models, "bogus_field")

    def test_updates_filters_unknown_keys(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            yaml.dump({"profiles": {"p": {"updates": {"interval_hours": 5, "bogus": "y"}}}})
        )
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert cfg.updates.interval_hours == 5

    @pytest.mark.parametrize("field_name", _MODULE_OVERRIDE_FIELD_NAMES)
    def test_all_module_overrides_round_trip(self, tmp_path, field_name):
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = AppConfig(**{field_name: {"key": "value"}})
        mgr.save(cfg, profile="p")
        loaded = mgr.load("p")
        assert getattr(loaded, field_name) == {"key": "value"}

    @pytest.mark.parametrize("field_name", _MODULE_OVERRIDE_FIELD_NAMES)
    def test_all_module_overrides_missing_defaults_to_none(self, tmp_path, field_name):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"profiles": {"p": {}}}))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert getattr(cfg, field_name) is None

    def test_unknown_extra_keys_in_data_are_ignored(self, tmp_path):
        config_path = tmp_path / "config.yaml"
        config_path.write_text(yaml.dump({"profiles": {"p": {"totally_unknown_field": "surprise"}}}))
        mgr = ConfigManager(config_dir=tmp_path)
        cfg = mgr.load("p")
        assert not hasattr(cfg, "totally_unknown_field")


class TestConfigRoundTripAllFields:
    """Round-trips every AppConfig field through the dynamic field-iteration
    machinery introduced in #1542, guarding against a future field being
    silently dropped by either serializer or deserializer."""

    def test_full_round_trip(self, tmp_path):
        mgr = ConfigManager(config_dir=tmp_path)
        original = AppConfig(
            profile_name="rt",
            default_methodology="para",
            default_input_dir="/tmp/in",  # noqa: test-hardcoded-paths
            default_output_dir="/tmp/out",  # noqa: test-hardcoded-paths
            setup_completed=True,
            setup_deferred=True,
            models=ModelPreset(
                text_model="m",
                temperature=0.9,
                max_tokens=100,
                device="cpu",
                framework="llama_cpp",
            ),
            updates=UpdateSettings(
                check_on_startup=False,
                interval_hours=1,
                include_prereleases=True,
                repo="foo/bar",
            ),
            watcher={"a": 1},
            daemon={"b": 2},
            parallel={"c": 3},
            pipeline={"d": 4},
            events={"e": 5},
            deploy={"f": 6},
            para={"g": 7},
            johnny_decimal={"h": 8},
        )
        mgr.save(original, profile="rt")
        loaded = mgr.load("rt")

        assert loaded.profile_name == "rt"
        assert loaded.version == CURRENT_SCHEMA_VERSION
        assert loaded.default_methodology == "para"
        assert loaded.default_input_dir == "/tmp/in"  # noqa: test-hardcoded-paths
        assert loaded.default_output_dir == "/tmp/out"  # noqa: test-hardcoded-paths
        assert loaded.setup_completed is True
        assert loaded.setup_deferred is True
        assert loaded.models == original.models
        assert loaded.updates == original.updates
        assert loaded.watcher == {"a": 1}
        assert loaded.daemon == {"b": 2}
        assert loaded.parallel == {"c": 3}
        assert loaded.pipeline == {"d": 4}
        assert loaded.events == {"e": 5}
        assert loaded.deploy == {"f": 6}
        assert loaded.para == {"g": 7}
        assert loaded.johnny_decimal == {"h": 8}

    def test_defaults_round_trip_without_module_overrides(self, tmp_path):
        """A bare ``AppConfig()`` round-trips without any module-override
        keys appearing on disk (they stay excluded end-to-end)."""
        mgr = ConfigManager(config_dir=tmp_path)
        mgr.save(AppConfig(), profile="defaults")
        loaded = mgr.load("defaults")

        assert loaded == AppConfig(profile_name="defaults")
