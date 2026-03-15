"""Coverage tests for plugins.base module."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from file_organizer.plugins.base import (
    Plugin,
    PluginLoadError,
    PluginMetadata,
    load_manifest,
    validate_manifest,
)

pytestmark = pytest.mark.unit


def _write_manifest(plugin_dir: Path, manifest: dict) -> Path:
    plugin_dir.mkdir(parents=True, exist_ok=True)
    path = plugin_dir / "plugin.json"
    path.write_text(json.dumps(manifest))
    return path


VALID_MANIFEST = {
    "name": "test",
    "version": "1.0.0",
    "author": "tester",
    "description": "A test plugin",
    "entry_point": "plugin.py",
}


class TestLoadManifest:
    def test_missing_manifest_raises(self, tmp_path):
        with pytest.raises(PluginLoadError, match="Manifest file not found"):
            load_manifest(tmp_path / "nonexistent")

    def test_invalid_json_raises(self, tmp_path):
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{invalid json")

        with pytest.raises(PluginLoadError, match="Invalid JSON"):
            load_manifest(plugin_dir)

    def test_non_dict_raises(self, tmp_path):
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text(json.dumps([1, 2, 3]))

        with pytest.raises(PluginLoadError, match="must be a JSON object"):
            load_manifest(plugin_dir)

    def test_valid_manifest_applies_defaults(self, tmp_path):
        plugin_dir = tmp_path / "plugin"
        _write_manifest(plugin_dir, VALID_MANIFEST)

        result = load_manifest(plugin_dir)
        assert result["license"] == "MIT"
        assert result["dependencies"] == []
        assert result["allowed_paths"] == []
        assert result["min_organizer_version"] == "2.0.0"
        assert result["homepage"] is None

    def test_manifest_preserves_existing_optional_fields(self, tmp_path):
        plugin_dir = tmp_path / "plugin"
        m = {**VALID_MANIFEST, "license": "Apache-2.0", "homepage": "https://example.com"}
        _write_manifest(plugin_dir, m)

        result = load_manifest(plugin_dir)
        assert result["license"] == "Apache-2.0"
        assert result["homepage"] == "https://example.com"

    @pytest.mark.skipif(sys.platform == "win32", reason="chmod does not restrict reads on Windows")
    def test_unreadable_manifest_raises(self, tmp_path):
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest_path = plugin_dir / "plugin.json"
        manifest_path.write_text(json.dumps(VALID_MANIFEST))
        manifest_path.chmod(0o000)

        try:
            with pytest.raises(PluginLoadError, match="Cannot read manifest"):
                load_manifest(plugin_dir)
        finally:
            manifest_path.chmod(0o644)


class TestValidateManifest:
    def test_missing_required_field(self):
        m = {k: v for k, v in VALID_MANIFEST.items() if k != "author"}
        with pytest.raises(PluginLoadError, match="missing required field 'author'"):
            validate_manifest(m)

    def test_wrong_type_required_field(self):
        m = {**VALID_MANIFEST, "name": 123}
        with pytest.raises(PluginLoadError, match="must be str"):
            validate_manifest(m)

    def test_optional_field_wrong_type(self):
        m = {**VALID_MANIFEST, "dependencies": "not-a-list"}
        with pytest.raises(PluginLoadError, match="must be list"):
            validate_manifest(m)

    def test_optional_nullable_allows_none(self):
        m = {**VALID_MANIFEST, "homepage": None}
        validate_manifest(m)  # Should not raise

    def test_optional_non_nullable_rejects_none(self):
        m = {**VALID_MANIFEST, "license": None}
        with pytest.raises(PluginLoadError, match="must not be null"):
            validate_manifest(m)


class TestPluginMetadata:
    def test_creation(self):
        meta = PluginMetadata(
            name="x",
            version="1.0",
            author="a",
            description="d",
        )
        assert meta.name == "x"
        assert meta.license == "MIT"
        assert meta.dependencies == ()
        assert meta.min_organizer_version == "2.0.0"


class TestPluginBase:
    def test_default_config_and_sandbox(self):
        class DummyPlugin(Plugin):
            def get_metadata(self):
                return PluginMetadata(name="d", version="1", author="a", description="d")

            def on_load(self):
                pass

            def on_enable(self):
                pass

            def on_disable(self):
                pass

            def on_unload(self):
                pass

        plugin = DummyPlugin()
        assert plugin.config == {}
        assert plugin.sandbox is not None
        assert plugin.enabled is False

        plugin.set_enabled(True)
        assert plugin.enabled is True

    def test_custom_config(self):
        class DummyPlugin(Plugin):
            def get_metadata(self):
                return PluginMetadata(name="d", version="1", author="a", description="d")

            def on_load(self):
                pass

            def on_enable(self):
                pass

            def on_disable(self):
                pass

            def on_unload(self):
                pass

        plugin = DummyPlugin(config={"key": "val"})
        assert plugin.config == {"key": "val"}
