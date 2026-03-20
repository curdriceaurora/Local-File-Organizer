"""Tests for plugin base contracts: validate_manifest, PluginMetadata, Plugin ABC."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from file_organizer.plugins.base import (
    MANIFEST_REQUIRED_FIELDS,
    Plugin,
    PluginMetadata,
    load_manifest,
    validate_manifest,
)
from file_organizer.plugins.errors import PluginLoadError

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_manifest(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid manifest dict, with optional overrides."""
    base: dict[str, Any] = {
        "name": "test-plugin",
        "version": "1.0.0",
        "author": "Test Author",
        "description": "A test plugin",
        "entry_point": "main.py",
    }
    base.update(overrides)
    return base


class ConcretePlugin(Plugin):
    """Minimal concrete implementation of the abstract Plugin base."""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="concrete",
            version="0.1.0",
            author="tester",
            description="test plugin",
        )

    def on_load(self) -> None:
        pass

    def on_enable(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        pass


# ---------------------------------------------------------------------------
# validate_manifest — required fields
# ---------------------------------------------------------------------------


class TestValidateManifestRequired:
    """Tests for required field validation in validate_manifest."""

    def test_valid_manifest_passes(self) -> None:
        validate_manifest(_valid_manifest())

    @pytest.mark.parametrize("field_name", list(MANIFEST_REQUIRED_FIELDS))
    def test_missing_required_field_raises(self, field_name: str) -> None:
        manifest = _valid_manifest()
        del manifest[field_name]
        with pytest.raises(PluginLoadError, match=f"missing required field '{field_name}'"):
            validate_manifest(manifest)

    @pytest.mark.parametrize("field_name", list(MANIFEST_REQUIRED_FIELDS))
    def test_wrong_type_required_field_raises(self, field_name: str) -> None:
        manifest = _valid_manifest(**{field_name: 12345})
        with pytest.raises(PluginLoadError, match=f"field '{field_name}' must be"):
            validate_manifest(manifest)


# ---------------------------------------------------------------------------
# validate_manifest — optional fields
# ---------------------------------------------------------------------------


class TestValidateManifestOptional:
    """Tests for optional field validation in validate_manifest."""

    def test_optional_fields_absent_is_ok(self) -> None:
        """Missing optional fields should not raise."""
        validate_manifest(_valid_manifest())

    def test_license_string_accepted(self) -> None:
        validate_manifest(_valid_manifest(license="Apache-2.0"))

    def test_license_wrong_type_raises(self) -> None:
        with pytest.raises(PluginLoadError, match="field 'license' must be"):
            validate_manifest(_valid_manifest(license=42))

    def test_homepage_none_accepted(self) -> None:
        """homepage has a None default, so None value is allowed."""
        validate_manifest(_valid_manifest(homepage=None))

    def test_homepage_string_accepted(self) -> None:
        validate_manifest(_valid_manifest(homepage="https://example.com"))

    def test_dependencies_list_accepted(self) -> None:
        validate_manifest(_valid_manifest(dependencies=["dep-a", "dep-b"]))

    def test_dependencies_wrong_type_raises(self) -> None:
        with pytest.raises(PluginLoadError, match="field 'dependencies' must be"):
            validate_manifest(_valid_manifest(dependencies="not-a-list"))

    def test_dependencies_null_raises_because_default_is_not_none(self) -> None:
        """dependencies default is (), not None, so null is not allowed."""
        with pytest.raises(PluginLoadError, match="field 'dependencies' must not be null"):
            validate_manifest(_valid_manifest(dependencies=None))

    def test_min_organizer_version_string_accepted(self) -> None:
        validate_manifest(_valid_manifest(min_organizer_version="3.0.0"))

    def test_max_organizer_version_none_accepted(self) -> None:
        validate_manifest(_valid_manifest(max_organizer_version=None))

    def test_allowed_paths_list_accepted(self) -> None:
        validate_manifest(_valid_manifest(allowed_paths=["./data"]))

    def test_allowed_paths_null_raises(self) -> None:
        with pytest.raises(PluginLoadError, match="field 'allowed_paths' must not be null"):
            validate_manifest(_valid_manifest(allowed_paths=None))


# ---------------------------------------------------------------------------
# load_manifest
# ---------------------------------------------------------------------------


class TestLoadManifest:
    """Tests for load_manifest reading and validating plugin.json."""

    def test_load_valid_manifest(self, tmp_path: Path) -> None:
        manifest_data = _valid_manifest()
        (tmp_path / "plugin.json").write_text(json.dumps(manifest_data))
        result = load_manifest(tmp_path)
        assert result["name"] == "test-plugin"
        # Defaults applied for missing optional fields
        assert result["license"] == "MIT"
        assert result["dependencies"] == []
        assert result["min_organizer_version"] == "2.0.0"

    def test_missing_manifest_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(PluginLoadError, match="Manifest file not found"):
            load_manifest(tmp_path)

    def test_invalid_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "plugin.json").write_text("{invalid json")
        with pytest.raises(PluginLoadError, match="Invalid JSON"):
            load_manifest(tmp_path)

    def test_non_dict_json_raises(self, tmp_path: Path) -> None:
        (tmp_path / "plugin.json").write_text(json.dumps([1, 2, 3]))
        with pytest.raises(PluginLoadError, match="must be a JSON object"):
            load_manifest(tmp_path)

    def test_optional_defaults_are_mutable_lists(self, tmp_path: Path) -> None:
        """Sequence defaults (dependencies, allowed_paths) should become lists."""
        manifest_data = _valid_manifest()
        (tmp_path / "plugin.json").write_text(json.dumps(manifest_data))
        result = load_manifest(tmp_path)
        assert isinstance(result["dependencies"], list) and isinstance(
            result["allowed_paths"], list
        )
        # Both should be mutable (can append)
        result["dependencies"].append("test-dep")
        assert result["dependencies"][-1] == "test-dep"

    def test_existing_optional_fields_preserved(self, tmp_path: Path) -> None:
        manifest_data = _valid_manifest(license="GPL-3.0", homepage="https://x.com")
        (tmp_path / "plugin.json").write_text(json.dumps(manifest_data))
        result = load_manifest(tmp_path)
        assert result["license"] == "GPL-3.0"
        assert result["homepage"] == "https://x.com"


# ---------------------------------------------------------------------------
# PluginMetadata
# ---------------------------------------------------------------------------


class TestPluginMetadata:
    """Tests for PluginMetadata dataclass defaults and immutability."""

    def test_required_fields_only(self) -> None:
        meta = PluginMetadata(name="p", version="1.0", author="a", description="d")
        assert meta.name == "p"
        assert meta.license == "MIT"
        assert meta.dependencies == ()
        assert meta.min_organizer_version == "2.0.0"
        assert meta.max_organizer_version is None
        assert meta.homepage is None

    def test_frozen_raises_on_assignment(self) -> None:
        meta = PluginMetadata(name="p", version="1.0", author="a", description="d")
        with pytest.raises(AttributeError):
            meta.name = "changed"  # type: ignore[misc]

    def test_all_fields_set(self) -> None:
        meta = PluginMetadata(
            name="p",
            version="2.0",
            author="a",
            description="d",
            homepage="https://example.com",
            license="Apache-2.0",
            dependencies=("dep1",),
            min_organizer_version="1.0.0",
            max_organizer_version="3.0.0",
        )
        assert meta.homepage == "https://example.com"
        assert meta.dependencies == ("dep1",)
        assert meta.max_organizer_version == "3.0.0"


# ---------------------------------------------------------------------------
# Plugin ABC
# ---------------------------------------------------------------------------


class TestPluginBase:
    """Tests for Plugin abstract base class interface."""

    def test_concrete_plugin_instantiation(self) -> None:
        plugin = ConcretePlugin()
        assert plugin.enabled is False
        assert plugin.config == {}

    def test_config_dict_from_mapping(self) -> None:
        plugin = ConcretePlugin(config={"key": "value"})
        assert plugin.config == {"key": "value"}

    def test_set_enabled(self) -> None:
        plugin = ConcretePlugin()
        assert plugin.enabled is False
        plugin.set_enabled(True)
        assert plugin.enabled is True
        plugin.set_enabled(False)
        assert plugin.enabled is False

    def test_abstract_methods_enforced(self) -> None:
        """Cannot instantiate Plugin directly — abstract methods must exist."""
        with pytest.raises(TypeError):
            Plugin()  # type: ignore[abstract]

    def test_sandbox_default_created(self) -> None:
        plugin = ConcretePlugin()
        assert plugin.sandbox is not None
        assert plugin.sandbox.plugin_name == "ConcretePlugin"

    def test_custom_sandbox(self) -> None:
        from file_organizer.plugins.security import PluginSandbox

        sandbox = PluginSandbox(plugin_name="custom")
        plugin = ConcretePlugin(sandbox=sandbox)
        assert plugin.sandbox is sandbox

    def test_get_metadata_returns_metadata(self) -> None:
        plugin = ConcretePlugin()
        meta = plugin.get_metadata()
        assert isinstance(meta, PluginMetadata)
        assert meta.name == "concrete"
