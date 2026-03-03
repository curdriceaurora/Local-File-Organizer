"""Tests for plugin error handling and validation."""

from __future__ import annotations

import pytest

from file_organizer.plugins.base import (
    PluginLoadError,
    validate_manifest,
)
from file_organizer.plugins.errors import (
    HookExecutionError,
    PluginConfigError,
    PluginError,
    PluginNotLoadedError,
    PluginPermissionError,
)


# ============================================================================
# Plugin Error Tests
# ============================================================================


class TestPluginErrors:
    """Test plugin error hierarchy and messages."""

    def test_plugin_error_base(self) -> None:
        """PluginError is base exception for plugin system."""
        error = PluginError("test error")

        assert isinstance(error, Exception)
        assert str(error) == "test error"

    def test_plugin_load_error_inheritance(self) -> None:
        """PluginLoadError inherits from PluginError."""
        error = PluginLoadError("Failed to load plugin")

        assert isinstance(error, PluginError)
        assert isinstance(error, Exception)
        assert "Failed to load plugin" in str(error)

    def test_plugin_permission_error_inheritance(self) -> None:
        """PluginPermissionError inherits from PluginError."""
        error = PluginPermissionError("Access denied to /etc/passwd")

        assert isinstance(error, PluginError)
        assert "Access denied" in str(error)

    def test_plugin_not_loaded_error(self) -> None:
        """PluginNotLoadedError raised when plugin not loaded."""
        error = PluginNotLoadedError("plugin-id", "Cannot execute unloaded plugin")

        assert isinstance(error, PluginError)
        assert "plugin-id" in str(error) or "Cannot execute" in str(error)

    def test_plugin_config_error(self) -> None:
        """PluginConfigError raised for configuration issues."""
        error = PluginConfigError("Invalid config field: api_key")

        assert isinstance(error, PluginError)
        assert "api_key" in str(error)

    def test_hook_execution_error(self) -> None:
        """HookExecutionError raised when hook execution fails."""
        error = HookExecutionError("on_file_organized", "Plugin crashed")

        assert isinstance(error, PluginError)
        assert "on_file_organized" in str(error) or "Plugin crashed" in str(error)


# ============================================================================
# Manifest Validation Error Tests
# ============================================================================


class TestValidationErrors:
    """Test validation error messages are descriptive."""

    def test_missing_required_field_error(self) -> None:
        """Missing required field error is clear."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            # Missing author, description, entry_point
        }

        with pytest.raises(PluginLoadError) as exc_info:
            validate_manifest(manifest)

        error_msg = str(exc_info.value)
        assert "author" in error_msg or "required field" in error_msg

    def test_wrong_type_error_message(self) -> None:
        """Wrong field type error mentions expected and actual types."""
        manifest = {
            "name": "test",
            "version": 1.0,  # Should be string
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
        }

        with pytest.raises(PluginLoadError) as exc_info:
            validate_manifest(manifest)

        error_msg = str(exc_info.value)
        assert "version" in error_msg
        assert ("str" in error_msg or "string" in error_msg)

    def test_null_field_error(self) -> None:
        """Null value in non-nullable field has clear error."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
            "license": None,  # Non-nullable
        }

        with pytest.raises(PluginLoadError) as exc_info:
            validate_manifest(manifest)

        error_msg = str(exc_info.value)
        assert "null" in error_msg.lower() or "license" in error_msg

    def test_nullable_field_allows_none(self) -> None:
        """Nullable fields (homepage, max_version) allow None."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
            "homepage": None,  # Nullable
            "max_organizer_version": None,  # Nullable
        }

        # Should not raise
        validate_manifest(manifest)

    def test_error_includes_source_context(self) -> None:
        """Error messages include source file/context information."""
        manifest = {"name": "test"}  # Missing required fields

        with pytest.raises(PluginLoadError) as exc_info:
            validate_manifest(manifest, source="/path/to/plugin.json")

        error_msg = str(exc_info.value)
        # Should reference the source
        assert "plugin.json" in error_msg or "source" in error_msg.lower()


# ============================================================================
# Field Validation Tests
# ============================================================================


class TestFieldValidation:
    """Test individual field validation rules."""

    def test_name_field_must_be_string(self) -> None:
        """Plugin name must be a string."""
        manifest = {
            "name": ["name", "as", "list"],
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
        }

        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)

    def test_version_field_must_be_string(self) -> None:
        """Plugin version must be a string (not numeric)."""
        manifest = {
            "name": "test",
            "version": 1,
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
        }

        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)

    def test_author_field_required_and_non_empty(self) -> None:
        """Author field is required."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            # Missing author
            "description": "test",
            "entry_point": "plugin.py",
        }

        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)

    def test_description_field_required(self) -> None:
        """Description field is required."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            # Missing description
            "entry_point": "plugin.py",
        }

        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)

    def test_entry_point_field_required(self) -> None:
        """Entry point field is required."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            # Missing entry_point
        }

        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)

    def test_dependencies_field_must_be_list(self) -> None:
        """Dependencies field, if present, must be a list."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
            "dependencies": "not-a-list",
        }

        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)

    def test_allowed_paths_field_must_be_list(self) -> None:
        """Allowed paths field, if present, must be a list."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
            "allowed_paths": "/home/user",  # Should be list
        }

        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)

    def test_min_version_field_must_be_string(self) -> None:
        """Minimum version field must be a string."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
            "min_organizer_version": [2, 0, 0],  # Should be string
        }

        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)


# ============================================================================
# Parametrized Error Scenario Tests
# ============================================================================


class TestParametrizedErrorScenarios:
    """Test various error combinations with parametrize."""

    @pytest.mark.parametrize(
        "manifest,expected_error_substring",
        [
            # Missing different required fields
            (
                {
                    "version": "1.0.0",
                    "author": "test",
                    "description": "test",
                    "entry_point": "plugin.py",
                },
                "name",
            ),
            (
                {
                    "name": "test",
                    "author": "test",
                    "description": "test",
                    "entry_point": "plugin.py",
                },
                "version",
            ),
            (
                {
                    "name": "test",
                    "version": "1.0.0",
                    "description": "test",
                    "entry_point": "plugin.py",
                },
                "author",
            ),
            (
                {
                    "name": "test",
                    "version": "1.0.0",
                    "author": "test",
                    "entry_point": "plugin.py",
                },
                "description",
            ),
            (
                {
                    "name": "test",
                    "version": "1.0.0",
                    "author": "test",
                    "description": "test",
                },
                "entry_point",
            ),
        ],
    )
    def test_all_required_fields_missing(
        self, manifest: dict, expected_error_substring: str
    ) -> None:
        """Each required field is properly validated."""
        with pytest.raises(PluginLoadError) as exc_info:
            validate_manifest(manifest)

        error_msg = str(exc_info.value)
        assert expected_error_substring in error_msg

    @pytest.mark.parametrize(
        "field_name,wrong_value",
        [
            ("name", 123),
            ("version", [1, 0, 0]),
            ("author", {"name": "test"}),
            ("description", None),
            ("entry_point", False),
        ],
    )
    def test_all_required_fields_type_validation(
        self, field_name: str, wrong_value
    ) -> None:
        """All required fields validate their types correctly."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
        }

        manifest[field_name] = wrong_value  # type: ignore[assignment]

        with pytest.raises(PluginLoadError) as exc_info:
            validate_manifest(manifest)

        error_msg = str(exc_info.value)
        assert field_name in error_msg


# ============================================================================
# Error Recovery Tests
# ============================================================================


class TestErrorRecovery:
    """Test recovery from validation errors."""

    def test_fix_missing_field_and_retry(self) -> None:
        """Can fix validation error and retry successfully."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            # Missing description
            "entry_point": "plugin.py",
        }

        # First attempt should fail
        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)

        # Fix the error
        manifest["description"] = "Fixed description"

        # Second attempt should succeed
        validate_manifest(manifest)  # Should not raise

    def test_fix_type_error_and_retry(self) -> None:
        """Can fix type error and retry successfully."""
        manifest = {
            "name": "test",
            "version": 1.0,  # Wrong type
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
        }

        # First attempt should fail
        with pytest.raises(PluginLoadError):
            validate_manifest(manifest)

        # Fix the error
        manifest["version"] = "1.0"

        # Second attempt should succeed
        validate_manifest(manifest)  # Should not raise


# ============================================================================
# Error Message Consistency Tests
# ============================================================================


class TestErrorMessageConsistency:
    """Test that error messages are clear and consistent."""

    def test_error_messages_use_field_names(self) -> None:
        """Error messages clearly state which field caused the error."""
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
            "license": 123,  # Wrong type
        }

        with pytest.raises(PluginLoadError) as exc_info:
            validate_manifest(manifest)

        error_msg = str(exc_info.value)
        assert "license" in error_msg

    def test_error_messages_mention_type_info(self) -> None:
        """Error messages mention expected type when possible."""
        manifest = {
            "name": "test",
            "version": {"major": 1, "minor": 0, "patch": 0},
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
        }

        with pytest.raises(PluginLoadError) as exc_info:
            validate_manifest(manifest)

        error_msg = str(exc_info.value)
        # Should mention type information
        assert any(
            word in error_msg.lower()
            for word in ["str", "string", "type", "expected"]
        )
