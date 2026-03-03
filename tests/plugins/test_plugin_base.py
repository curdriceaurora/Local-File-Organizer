"""Tests for plugin base contract and manifest loading."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from file_organizer.plugins.base import (
    Plugin,
    PluginLoadError,
    PluginMetadata,
    load_manifest,
    validate_manifest,
)


class SimplePlugin(Plugin):
    """Minimal test plugin implementation."""

    def get_metadata(self) -> PluginMetadata:
        """Return plugin metadata."""
        return PluginMetadata(
            name="simple-test",
            version="1.0.0",
            author="test",
            description="Simple test plugin",
        )

    def on_load(self) -> None:
        """Handle plugin load."""
        pass

    def on_enable(self) -> None:
        """Handle plugin enable."""
        pass

    def on_disable(self) -> None:
        """Handle plugin disable."""
        pass

    def on_unload(self) -> None:
        """Handle plugin unload."""
        pass


# ============================================================================
# Manifest Loading Tests
# ============================================================================


class TestManifestLoading:
    """Test manifest loading from plugin directories."""

    def test_load_manifest_success(self, plugin_dir: Path) -> None:
        """Successfully load and validate a manifest."""
        manifest = load_manifest(plugin_dir)

        assert manifest["name"] == "test-plugin"
        assert manifest["version"] == "1.0.0"
        assert manifest["author"] == "test author"
        assert manifest["description"] == "Test plugin"
        assert manifest["entry_point"] == "plugin.py"

    def test_load_manifest_applies_defaults(self, tmp_path: Path) -> None:
        """load_manifest applies defaults for optional fields."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()

        # Write only required fields
        manifest_data = {
            "name": "minimal",
            "version": "1.0.0",
            "author": "test",
            "description": "Test",
            "entry_point": "plugin.py",
        }
        (plugin_dir / "plugin.json").write_text(
            json.dumps(manifest_data), encoding="utf-8"
        )

        manifest = load_manifest(plugin_dir)

        # Check that optional fields got defaults
        assert manifest["license"] == "MIT"
        assert manifest["homepage"] is None
        assert manifest["dependencies"] == []
        assert manifest["min_organizer_version"] == "2.0.0"
        assert manifest["max_organizer_version"] is None
        assert manifest["allowed_paths"] == []

    def test_load_manifest_missing_file(self, tmp_path: Path) -> None:
        """Raise PluginLoadError when manifest file is missing."""
        plugin_dir = tmp_path / "no_manifest"
        plugin_dir.mkdir()

        with pytest.raises(PluginLoadError, match="Manifest file not found"):
            load_manifest(plugin_dir)

    def test_load_manifest_malformed_json(self, missing_manifest_dir: Path) -> None:
        """Raise PluginLoadError for malformed JSON."""
        manifest_path = missing_manifest_dir / "plugin.json"
        manifest_path.write_text("{invalid json", encoding="utf-8")

        with pytest.raises(PluginLoadError, match="Invalid JSON"):
            load_manifest(missing_manifest_dir)

    def test_load_manifest_not_dict(self, tmp_path: Path) -> None:
        """Raise PluginLoadError when manifest is not a JSON object."""
        plugin_dir = tmp_path / "array_manifest"
        plugin_dir.mkdir()

        manifest_path = plugin_dir / "plugin.json"
        manifest_path.write_text('["not", "an", "object"]', encoding="utf-8")

        with pytest.raises(PluginLoadError, match="Manifest must be a JSON object"):
            load_manifest(plugin_dir)

    def test_load_manifest_with_optional_fields(
        self, tmp_path: Path, extended_manifest: dict[str, Any]
    ) -> None:
        """Load manifest with all optional fields present."""
        plugin_dir = tmp_path / "extended"
        plugin_dir.mkdir()

        (plugin_dir / "plugin.json").write_text(
            json.dumps(extended_manifest), encoding="utf-8"
        )

        manifest = load_manifest(plugin_dir)

        assert manifest["license"] == "Apache-2.0"
        assert manifest["homepage"] == "https://example.com"
        assert "some-dep>=1.0" in manifest["dependencies"]
        assert manifest["min_organizer_version"] == "2.1.0"
        assert manifest["max_organizer_version"] == "3.0.0"


# ============================================================================
# Manifest Validation Tests
# ============================================================================


class TestManifestValidation:
    """Test manifest schema validation."""

    def test_validate_manifest_success(self, valid_manifest: dict[str, Any]) -> None:
        """Successfully validate a complete manifest."""
        # Should not raise
        validate_manifest(valid_manifest)

    def test_validate_manifest_missing_required_field(
        self, valid_manifest: dict[str, Any]
    ) -> None:
        """Raise error when required field is missing."""
        del valid_manifest["author"]

        with pytest.raises(
            PluginLoadError, match="missing required field 'author'"
        ):
            validate_manifest(valid_manifest)

    @pytest.mark.parametrize(
        "field,wrong_value",
        [
            ("name", 123),
            ("version", ["1", "0", "0"]),
            ("author", {"name": "test"}),
            ("description", None),
            ("entry_point", 42),
        ],
    )
    def test_validate_manifest_wrong_field_type(
        self, valid_manifest: dict[str, Any], field: str, wrong_value: Any
    ) -> None:
        """Raise error when required field has wrong type."""
        valid_manifest[field] = wrong_value

        with pytest.raises(PluginLoadError, match=f"field '{field}' must be"):
            validate_manifest(valid_manifest)

    def test_validate_manifest_nullable_optional_field(
        self, valid_manifest: dict[str, Any]
    ) -> None:
        """Allow None for nullable optional fields (homepage, max_version)."""
        valid_manifest["homepage"] = None
        valid_manifest["max_organizer_version"] = None

        # Should not raise
        validate_manifest(valid_manifest)

    def test_validate_manifest_non_nullable_optional_field(
        self, valid_manifest: dict[str, Any]
    ) -> None:
        """Reject None for non-nullable optional fields."""
        valid_manifest["license"] = None

        with pytest.raises(PluginLoadError, match="must not be null"):
            validate_manifest(valid_manifest)

    @pytest.mark.parametrize(
        "field,wrong_value",
        [
            ("license", 123),
            ("dependencies", "not-a-list"),
            ("allowed_paths", {"paths": []}),
            ("min_organizer_version", 2.0),
        ],
    )
    def test_validate_manifest_optional_field_wrong_type(
        self, valid_manifest: dict[str, Any], field: str, wrong_value: Any
    ) -> None:
        """Reject optional fields with wrong type."""
        valid_manifest[field] = wrong_value

        with pytest.raises(PluginLoadError, match=f"field '{field}' must be"):
            validate_manifest(valid_manifest)

    def test_validate_manifest_with_custom_source_label(
        self, invalid_manifest_missing_field: dict[str, Any]
    ) -> None:
        """Include source label in error message."""
        with pytest.raises(PluginLoadError, match="custom_source"):
            validate_manifest(invalid_manifest_missing_field, source="custom_source")


# ============================================================================
# Plugin Base Class Tests
# ============================================================================


class TestPluginBase:
    """Test Plugin base class functionality."""

    def test_plugin_init_default_config(self) -> None:
        """Plugin initializes with empty config by default."""
        plugin = SimplePlugin()

        assert plugin.config == {}
        assert plugin.enabled is False

    def test_plugin_init_with_config(self) -> None:
        """Plugin accepts custom configuration."""
        config = {"key1": "value1", "key2": "value2"}
        plugin = SimplePlugin(config=config)

        assert plugin.config == config
        assert plugin.config["key1"] == "value1"

    def test_plugin_enabled_state(self) -> None:
        """Plugin enabled state can be toggled."""
        plugin = SimplePlugin()

        assert not plugin.enabled

        plugin.set_enabled(True)
        assert plugin.enabled

        plugin.set_enabled(False)
        assert not plugin.enabled

    def test_plugin_sandbox_default(self) -> None:
        """Plugin creates default sandbox if not provided."""
        plugin = SimplePlugin()

        assert plugin.sandbox is not None
        assert plugin.sandbox.plugin_name == "SimplePlugin"

    def test_plugin_sandbox_custom(self, plugin_sandbox) -> None:
        """Plugin accepts custom sandbox."""
        plugin = SimplePlugin(sandbox=plugin_sandbox)

        assert plugin.sandbox is plugin_sandbox
        assert plugin.sandbox.plugin_name == "test-plugin"

    def test_plugin_get_metadata(self) -> None:
        """Plugin returns valid metadata."""
        plugin = SimplePlugin()
        metadata = plugin.get_metadata()

        assert isinstance(metadata, PluginMetadata)
        assert metadata.name == "simple-test"
        assert metadata.version == "1.0.0"
        assert metadata.author == "test"
        assert metadata.description == "Simple test plugin"

    def test_plugin_lifecycle_abstract_methods(self) -> None:
        """Plugin abstract methods must be implemented."""
        with pytest.raises(TypeError, match="abstract"):
            Plugin()  # type: ignore[abstract]


# ============================================================================
# PluginMetadata Tests
# ============================================================================


class TestPluginMetadata:
    """Test plugin metadata dataclass."""

    def test_metadata_minimal(self) -> None:
        """Create metadata with minimal fields."""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            author="author",
            description="desc",
        )

        assert metadata.name == "test"
        assert metadata.version == "1.0.0"
        assert metadata.author == "author"
        assert metadata.description == "desc"
        assert metadata.license == "MIT"
        assert metadata.homepage is None
        assert metadata.dependencies == ()

    def test_metadata_with_all_fields(
        self, plugin_metadata_with_deps: PluginMetadata
    ) -> None:
        """Create metadata with all fields specified."""
        metadata = plugin_metadata_with_deps

        assert metadata.name == "dependent-plugin"
        assert metadata.version == "1.0.0"
        assert metadata.dependencies == ("dep1", "dep2>=1.0")
        assert metadata.min_organizer_version == "2.0.0"
        assert metadata.max_organizer_version == "3.0.0"

    def test_metadata_immutable(self) -> None:
        """Metadata is frozen and immutable."""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            author="author",
            description="desc",
        )

        with pytest.raises(AttributeError):
            metadata.name = "modified"  # type: ignore[misc]

    def test_metadata_equality(self) -> None:
        """Metadata instances are equal if fields match."""
        meta1 = PluginMetadata(
            name="test",
            version="1.0.0",
            author="author",
            description="desc",
        )
        meta2 = PluginMetadata(
            name="test",
            version="1.0.0",
            author="author",
            description="desc",
        )

        assert meta1 == meta2

    def test_metadata_repr(self) -> None:
        """Metadata has useful repr."""
        metadata = PluginMetadata(
            name="test",
            version="1.0.0",
            author="author",
            description="desc",
        )

        repr_str = repr(metadata)
        assert "PluginMetadata" in repr_str
        assert "test" in repr_str
        assert "1.0.0" in repr_str


# ============================================================================
# Integration Tests
# ============================================================================


class TestManifestLoadingIntegration:
    """Integration tests for manifest loading with validation."""

    def test_load_and_validate_complete_flow(
        self, plugin_with_source: Path
    ) -> None:
        """Load manifest from disk and validate it."""
        manifest = load_manifest(plugin_with_source)

        # Validation should not raise
        validate_manifest(manifest)

        assert manifest["name"] == "test-plugin"
        assert "license" in manifest  # Defaults applied
        assert "dependencies" in manifest

    def test_manifest_errors_are_descriptive(
        self, tmp_path: Path
    ) -> None:
        """Error messages clearly identify the problem."""
        plugin_dir = tmp_path / "err_test"
        plugin_dir.mkdir()

        # Write manifest with multiple errors
        bad_manifest = {
            "name": 123,  # Wrong type
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(bad_manifest))

        error_caught = False
        try:
            load_manifest(plugin_dir)
        except PluginLoadError as e:
            error_caught = True
            error_msg = str(e)
            # Should mention the field name and type
            assert "name" in error_msg or "str" in error_msg

        assert error_caught
