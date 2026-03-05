"""Coverage tests for plugins.config module."""

from __future__ import annotations

import json

import pytest

from file_organizer.plugins.config import (
    PluginConfig,
    PluginConfigManager,
    _validate_plugin_name,
)
from file_organizer.plugins.errors import PluginConfigError

pytestmark = pytest.mark.unit


class TestValidatePluginName:
    def test_valid_names(self):
        assert _validate_plugin_name("my-plugin") == "my-plugin"
        assert _validate_plugin_name("Plugin_1.0") == "Plugin_1.0"
        assert _validate_plugin_name("  spaced  ") == "spaced"

    def test_invalid_names(self):
        with pytest.raises(PluginConfigError, match="Invalid plugin name"):
            _validate_plugin_name("")
        with pytest.raises(PluginConfigError, match="Invalid plugin name"):
            _validate_plugin_name("-starts-with-dash")
        with pytest.raises(PluginConfigError, match="Invalid plugin name"):
            _validate_plugin_name("has space")


class TestPluginConfig:
    def test_to_dict(self):
        cfg = PluginConfig(
            name="demo",
            enabled=True,
            settings={"key": "val"},
            permissions=["read"],
        )
        d = cfg.to_dict()
        assert d == {
            "name": "demo",
            "enabled": True,
            "settings": {"key": "val"},
            "permissions": ["read"],
        }

    def test_from_dict_valid(self):
        cfg = PluginConfig.from_dict(
            {
                "name": "demo",
                "enabled": True,
                "settings": {"x": 1},
                "permissions": ["read", "write"],
            }
        )
        assert cfg.name == "demo"
        assert cfg.enabled is True
        assert cfg.settings == {"x": 1}
        assert cfg.permissions == ["read", "write"]

    def test_from_dict_non_mapping_raises(self):
        with pytest.raises(PluginConfigError, match="must be a mapping"):
            PluginConfig.from_dict("not a dict")  # type: ignore[arg-type]

    def test_from_dict_missing_name_raises(self):
        with pytest.raises(PluginConfigError, match="missing a valid 'name'"):
            PluginConfig.from_dict({"enabled": True})

    def test_from_dict_invalid_name_type_raises(self):
        with pytest.raises(PluginConfigError, match="missing a valid 'name'"):
            PluginConfig.from_dict({"name": 123})

    def test_from_dict_bad_settings_uses_empty(self):
        cfg = PluginConfig.from_dict({"name": "demo", "settings": "not-dict"})
        assert cfg.settings == {}

    def test_from_dict_bad_permissions_uses_empty(self):
        cfg = PluginConfig.from_dict({"name": "demo", "permissions": "not-list"})
        assert cfg.permissions == []

    def test_from_dict_defaults(self):
        cfg = PluginConfig.from_dict({"name": "demo"})
        assert cfg.enabled is False
        assert cfg.settings == {}
        assert cfg.permissions == []


class TestPluginConfigManager:
    def test_config_path(self, tmp_path):
        mgr = PluginConfigManager(tmp_path)
        assert mgr.config_path("demo") == tmp_path / "demo.json"
        assert mgr.config_dir == tmp_path

    def test_load_config_missing_returns_default(self, tmp_path):
        mgr = PluginConfigManager(tmp_path)
        cfg = mgr.load_config("demo")
        assert cfg.name == "demo"
        assert cfg.enabled is False

    def test_save_and_load_roundtrip(self, tmp_path):
        mgr = PluginConfigManager(tmp_path)
        cfg = PluginConfig(name="demo", enabled=True, settings={"k": "v"})
        mgr.save_config(cfg)

        loaded = mgr.load_config("demo")
        assert loaded.name == "demo"
        assert loaded.enabled is True
        assert loaded.settings == {"k": "v"}

    def test_load_invalid_json_raises(self, tmp_path):
        mgr = PluginConfigManager(tmp_path)
        path = tmp_path / "demo.json"
        path.write_text("{broken json")

        with pytest.raises(PluginConfigError, match="not valid JSON"):
            mgr.load_config("demo")

    def test_load_non_dict_raises(self, tmp_path):
        mgr = PluginConfigManager(tmp_path)
        path = tmp_path / "demo.json"
        path.write_text(json.dumps([1, 2, 3]))

        with pytest.raises(PluginConfigError, match="must be a JSON object"):
            mgr.load_config("demo")

    def test_load_name_mismatch_raises(self, tmp_path):
        mgr = PluginConfigManager(tmp_path)
        path = tmp_path / "demo.json"
        path.write_text(json.dumps({"name": "other", "enabled": False}))

        with pytest.raises(PluginConfigError, match="name mismatch"):
            mgr.load_config("demo")

    def test_list_configured_plugins_empty(self, tmp_path):
        mgr = PluginConfigManager(tmp_path / "nonexistent")
        assert mgr.list_configured_plugins() == []

    def test_list_configured_plugins(self, tmp_path):
        mgr = PluginConfigManager(tmp_path)
        cfg1 = PluginConfig(name="alpha")
        cfg2 = PluginConfig(name="beta")
        mgr.save_config(cfg1)
        mgr.save_config(cfg2)

        names = mgr.list_configured_plugins()
        assert names == ["alpha", "beta"]

    def test_list_ignores_invalid_names(self, tmp_path):
        mgr = PluginConfigManager(tmp_path)
        # Create a file with an invalid plugin name
        (tmp_path / "-invalid.json").write_text("{}")
        cfg = PluginConfig(name="valid")
        mgr.save_config(cfg)

        names = mgr.list_configured_plugins()
        assert names == ["valid"]
