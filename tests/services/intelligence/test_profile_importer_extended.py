"""Extended tests for ProfileImporter.

Covers validation edge cases (large files, unknown versions, selective export,
invalid names, timestamps), preview_import with conflicts, import_profile with
selective type, _import_selective_profile paths, _backup_profile, import_selective,
ValidationResult.__str__, and exception handling.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.services.intelligence.profile_importer import (
    ProfileImporter,
    ValidationResult,
)
from file_organizer.services.intelligence.profile_manager import ProfileManager

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_storage():
    """Create temporary storage directory for tests."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def profile_manager(temp_storage):
    """Create ProfileManager with temporary storage."""
    return ProfileManager(storage_path=temp_storage / "profiles")


@pytest.fixture
def importer(profile_manager):
    """Create ProfileImporter backed by a temporary ProfileManager."""
    return ProfileImporter(profile_manager)


def _write_json(path: Path, data: dict) -> None:
    """Helper to write a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _make_valid_export(name: str = "test_profile", **overrides) -> dict:
    """Helper to build a valid full-export payload."""
    data = {
        "profile_name": name,
        "profile_version": "1.0",
        "description": "Test profile",
        "export_type": "full",
        "exported_at": "2025-01-15T10:00:00Z",
        "created": "2025-01-01T00:00:00Z",
        "updated": "2025-01-15T10:00:00Z",
        "preferences": {
            "global": {"pref_a": "val_a"},
            "directory_specific": {"/some/path": {"opt": True}},
        },
        "learned_patterns": {"pat1": "val1"},
        "confidence_data": {"conf1": 0.9},
    }
    data.update(overrides)
    return data


# ---------------------------------------------------------------------------
# ValidationResult.__str__
# ---------------------------------------------------------------------------


class TestValidationResultStr:
    """Tests for ValidationResult __str__ method."""

    def test_str_valid_no_errors_no_warnings(self):
        """Test string representation when valid with no issues."""
        result = ValidationResult(valid=True, errors=[], warnings=[])
        text = str(result)
        assert "Valid: True" in text
        assert "Errors" not in text
        assert "Warnings" not in text

    def test_str_with_errors(self):
        """Test string representation with errors."""
        result = ValidationResult(
            valid=False, errors=["bad field", "missing value"], warnings=[]
        )
        text = str(result)
        assert "Valid: False" in text
        assert "Errors: bad field, missing value" in text

    def test_str_with_warnings(self):
        """Test string representation with warnings."""
        result = ValidationResult(
            valid=True, errors=[], warnings=["big file", "old version"]
        )
        text = str(result)
        assert "Warnings: big file, old version" in text

    def test_str_with_errors_and_warnings(self):
        """Test string representation with both errors and warnings."""
        result = ValidationResult(
            valid=False, errors=["err"], warnings=["warn"]
        )
        text = str(result)
        assert "Valid: False" in text
        assert "Errors: err" in text
        assert "Warnings: warn" in text


# ---------------------------------------------------------------------------
# _get_current_timestamp
# ---------------------------------------------------------------------------


class TestGetCurrentTimestamp:
    """Tests for _get_current_timestamp method."""

    def test_returns_utc_iso_string(self, importer):
        """Test that timestamp is a UTC ISO string."""
        ts = importer._get_current_timestamp()
        assert isinstance(ts, str)
        assert ts.endswith("Z")
        assert "T" in ts


# ---------------------------------------------------------------------------
# validate_import_file – edge cases
# ---------------------------------------------------------------------------


class TestValidateImportFileEdgeCases:
    """Edge-case tests for validate_import_file."""

    def test_file_not_found(self, importer, temp_storage):
        """Test validation when file does not exist."""
        result = importer.validate_import_file(temp_storage / "nope.json")
        assert result.valid is False
        assert any("not found" in e.lower() for e in result.errors)

    def test_invalid_json(self, importer, temp_storage):
        """Test validation with invalid JSON."""
        bad_file = temp_storage / "bad.json"
        with open(bad_file, "w") as f:
            f.write("{not valid json")

        result = importer.validate_import_file(bad_file)
        assert result.valid is False
        assert any("json" in e.lower() for e in result.errors)

    def test_large_file_warning(self, importer, temp_storage):
        """Test warning generated for files larger than 10 MB."""
        big_file = temp_storage / "big.json"
        data = _make_valid_export()
        _write_json(big_file, data)

        # Patch stat to report a large file size
        mock_stat_result = MagicMock()
        mock_stat_result.st_size = 15 * 1024 * 1024  # 15 MB

        with patch.object(Path, "stat", return_value=mock_stat_result):
            result = importer.validate_import_file(big_file)

        assert result.warnings, f"Expected warnings, got: {result.warnings}"
        assert any("large file" in w.lower() for w in result.warnings), (
            f"Expected 'large file' in warnings, got: {result.warnings}"
        )

    def test_unknown_version_warning(self, importer, temp_storage):
        """Test warning when profile version is unknown."""
        export_file = temp_storage / "old_ver.json"
        data = _make_valid_export(profile_version="2.5")
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert any("unknown profile version" in w.lower() for w in result.warnings)

    def test_missing_required_fields(self, importer, temp_storage):
        """Test validation when required fields are missing."""
        export_file = temp_storage / "missing.json"
        _write_json(export_file, {"description": "no name or version"})

        result = importer.validate_import_file(export_file)
        assert result.valid is False
        assert any("missing required" in e.lower() for e in result.errors)

    def test_invalid_profile_name_empty(self, importer, temp_storage):
        """Test validation with empty profile name."""
        export_file = temp_storage / "empty_name.json"
        data = _make_valid_export(profile_name="")
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert result.valid is False
        assert any("invalid profile name" in e.lower() for e in result.errors)

    def test_invalid_profile_name_not_string(self, importer, temp_storage):
        """Test validation with non-string profile name."""
        export_file = temp_storage / "int_name.json"
        data = _make_valid_export(profile_name=12345)
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert result.valid is False
        assert any("invalid profile name" in e.lower() for e in result.errors)

    def test_profile_name_too_long(self, importer, temp_storage):
        """Test validation with profile name exceeding 100 characters."""
        export_file = temp_storage / "long_name.json"
        data = _make_valid_export(profile_name="x" * 101)
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert result.valid is False
        assert any("too long" in e.lower() for e in result.errors)

    def test_full_export_missing_preferences(self, importer, temp_storage):
        """Test validation for full export missing preferences field."""
        export_file = temp_storage / "no_prefs.json"
        data = {
            "profile_name": "test",
            "profile_version": "1.0",
            "export_type": "full",
        }
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert result.valid is False
        assert any("preferences" in e.lower() for e in result.errors)

    def test_full_export_invalid_preferences_type(self, importer, temp_storage):
        """Test validation with preferences not a dict."""
        export_file = temp_storage / "bad_prefs.json"
        data = _make_valid_export(preferences="not_a_dict")
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert result.valid is False
        assert any("invalid preferences" in e.lower() for e in result.errors)

    def test_full_export_missing_global_warning(self, importer, temp_storage):
        """Test warning when global preferences are missing."""
        export_file = temp_storage / "no_global.json"
        data = _make_valid_export(preferences={"directory_specific": {}})
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert any("global" in w.lower() for w in result.warnings)

    def test_full_export_missing_directory_specific_warning(self, importer, temp_storage):
        """Test warning when directory_specific preferences are missing."""
        export_file = temp_storage / "no_dir.json"
        data = _make_valid_export(preferences={"global": {}})
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert any("directory_specific" in w.lower() for w in result.warnings)

    def test_selective_export_missing_included_preferences(self, importer, temp_storage):
        """Test validation for selective export missing included_preferences."""
        export_file = temp_storage / "sel_missing.json"
        data = _make_valid_export(export_type="selective")
        del data["preferences"]
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert result.valid is False
        assert any("included_preferences" in e.lower() for e in result.errors)

    def test_selective_export_missing_preferences(self, importer, temp_storage):
        """Test validation for selective export missing preferences."""
        export_file = temp_storage / "sel_no_prefs.json"
        data = {
            "profile_name": "sel_test",
            "profile_version": "1.0",
            "export_type": "selective",
            "included_preferences": ["global"],
        }
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert result.valid is False
        assert any("preferences" in e.lower() for e in result.errors)

    def test_invalid_timestamp_warning(self, importer, temp_storage):
        """Test warning for invalid timestamp format."""
        export_file = temp_storage / "bad_ts.json"
        data = _make_valid_export(exported_at="not-a-timestamp")
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert any("timestamp" in w.lower() for w in result.warnings)

    def test_existing_profile_warning(self, importer, profile_manager, temp_storage):
        """Test warning when profile already exists."""
        profile_manager.create_profile("existing", "Existing profile")

        export_file = temp_storage / "existing.json"
        data = _make_valid_export(profile_name="existing")
        _write_json(export_file, data)

        result = importer.validate_import_file(export_file)
        assert any("already exists" in w.lower() for w in result.warnings)

    def test_outer_exception_caught(self, importer, temp_storage):
        """Test that outer exceptions are caught gracefully."""
        export_file = temp_storage / "exc.json"
        data = _make_valid_export()
        _write_json(export_file, data)

        with patch("builtins.open", side_effect=PermissionError("denied")):
            result = importer.validate_import_file(export_file)

        assert result.valid is False
        assert any("validation error" in e.lower() for e in result.errors)


# ---------------------------------------------------------------------------
# preview_import – additional cases
# ---------------------------------------------------------------------------


class TestPreviewImportExtended:
    """Extended tests for preview_import method."""

    def test_preview_valid_file(self, importer, temp_storage):
        """Test preview with a valid export file."""
        export_file = temp_storage / "prev.json"
        data = _make_valid_export()
        _write_json(export_file, data)

        preview = importer.preview_import(export_file)

        assert preview is not None
        assert preview["profile_name"] == "test_profile"
        assert preview["export_type"] == "full"
        assert "preferences_count" in preview
        assert preview["preferences_count"]["global"] == 1
        assert preview["learned_patterns_count"] == 1
        assert preview["confidence_data_count"] == 1

    def test_preview_with_conflict(self, importer, profile_manager, temp_storage):
        """Test preview flags conflicts when profile exists."""
        profile_manager.create_profile("conflict_me", "Existing profile")

        export_file = temp_storage / "conflict.json"
        data = _make_valid_export(profile_name="conflict_me")
        _write_json(export_file, data)

        preview = importer.preview_import(export_file)

        assert preview is not None
        assert "conflicts" in preview
        assert preview["conflicts"]["existing_profile"] is True

    def test_preview_invalid_file(self, importer, temp_storage):
        """Test preview returns None for invalid file."""
        bad_file = temp_storage / "bad.json"
        with open(bad_file, "w") as f:
            f.write("{bad json")

        preview = importer.preview_import(bad_file)
        assert preview is None

    def test_preview_empty_profile_data(self, importer, temp_storage):
        """Test preview when validation returns no profile_data."""
        export_file = temp_storage / "empty.json"
        _write_json(export_file, _make_valid_export())

        # Force validation to return valid but empty profile_data
        fake_result = ValidationResult(valid=True, errors=[], warnings=[], profile_data=None)
        with patch.object(importer, "validate_import_file", return_value=fake_result):
            preview = importer.preview_import(export_file)

        assert preview is None

    def test_preview_exception(self, importer, temp_storage):
        """Test preview catches exceptions gracefully."""
        export_file = temp_storage / "exc.json"
        _write_json(export_file, _make_valid_export())

        with patch.object(
            importer, "validate_import_file", side_effect=RuntimeError("boom")
        ):
            preview = importer.preview_import(export_file)

        assert preview is None


# ---------------------------------------------------------------------------
# import_profile – additional cases
# ---------------------------------------------------------------------------


class TestImportProfileExtended:
    """Extended tests for import_profile method."""

    def test_import_full_new_profile(self, importer, temp_storage):
        """Test importing a new full profile."""
        export_file = temp_storage / "full.json"
        data = _make_valid_export(profile_name="brand_new")
        _write_json(export_file, data)

        result = importer.import_profile(export_file)

        assert result is not None
        assert result.profile_name == "brand_new"
        assert result.preferences["global"]["pref_a"] == "val_a"

    def test_import_with_new_name(self, importer, temp_storage):
        """Test importing with a different name override."""
        export_file = temp_storage / "rename.json"
        data = _make_valid_export(profile_name="original")
        _write_json(export_file, data)

        result = importer.import_profile(export_file, new_name="renamed")

        assert result is not None
        assert result.profile_name == "renamed"

    def test_import_invalid_file_returns_none(self, importer, temp_storage):
        """Test that importing an invalid file returns None."""
        bad = temp_storage / "bad.json"
        with open(bad, "w") as f:
            f.write("not json")

        result = importer.import_profile(bad)
        assert result is None

    def test_import_empty_profile_data(self, importer, temp_storage):
        """Test import when validation returns empty profile_data."""
        export_file = temp_storage / "empty.json"
        _write_json(export_file, _make_valid_export())

        fake_result = ValidationResult(valid=True, errors=[], warnings=[], profile_data=None)
        with patch.object(importer, "validate_import_file", return_value=fake_result):
            result = importer.import_profile(export_file)

        assert result is None

    def test_import_selective_export_type(self, importer, profile_manager, temp_storage):
        """Test importing a selective export type delegates to _import_selective_profile."""
        export_file = temp_storage / "selective.json"
        data = _make_valid_export(export_type="selective")
        data["included_preferences"] = ["global"]
        _write_json(export_file, data)

        result = importer.import_profile(export_file)

        assert result is not None
        assert result.profile_name == "test_profile"

    def test_import_overwrite_existing_creates_backup(
        self, importer, profile_manager, temp_storage
    ):
        """Test that overwriting an existing profile triggers a backup."""
        profile_manager.create_profile("overwrite_me", "Existing")

        export_file = temp_storage / "over.json"
        data = _make_valid_export(profile_name="overwrite_me")
        _write_json(export_file, data)

        with patch.object(importer, "_backup_profile") as mock_backup:
            result = importer.import_profile(export_file)

        assert result is not None
        mock_backup.assert_called_once()

    def test_import_profile_validation_fails(self, importer, temp_storage):
        """Test import returns None when Profile.validate() fails."""
        export_file = temp_storage / "bad_prof.json"
        # Empty description causes Profile.validate() to fail
        data = _make_valid_export(description="")
        _write_json(export_file, data)

        result = importer.import_profile(export_file)
        assert result is None

    def test_import_update_existing_fails(self, importer, profile_manager, temp_storage):
        """Test import returns None when update of existing profile fails."""
        profile_manager.create_profile("upd_fail", "Test")

        export_file = temp_storage / "upd.json"
        data = _make_valid_export(profile_name="upd_fail")
        _write_json(export_file, data)

        with patch.object(profile_manager, "update_profile", return_value=False):
            result = importer.import_profile(export_file)

        assert result is None

    def test_import_create_new_profile_fails(self, importer, profile_manager, temp_storage):
        """Test import returns None when create_profile fails."""
        export_file = temp_storage / "create_fail.json"
        data = _make_valid_export(profile_name="new_fail")
        _write_json(export_file, data)

        with patch.object(profile_manager, "create_profile", return_value=None):
            result = importer.import_profile(export_file)

        assert result is None

    def test_import_create_then_update_fails(self, importer, profile_manager, temp_storage):
        """Test import returns None when create succeeds but update fails."""
        export_file = temp_storage / "cu_fail.json"
        data = _make_valid_export(profile_name="cu_fail_prof")
        _write_json(export_file, data)

        original_create = profile_manager.create_profile

        def create_then_fail_update(name, desc):
            profile = original_create(name, desc)
            return profile

        with patch.object(profile_manager, "create_profile", side_effect=create_then_fail_update):
            with patch.object(profile_manager, "update_profile", return_value=False):
                result = importer.import_profile(export_file)

        assert result is None

    def test_import_outer_exception(self, importer, temp_storage):
        """Test import handles outer exceptions gracefully."""
        export_file = temp_storage / "exc.json"
        _write_json(export_file, _make_valid_export())

        with patch.object(
            importer, "validate_import_file", side_effect=RuntimeError("kaboom")
        ):
            result = importer.import_profile(export_file)

        assert result is None


# ---------------------------------------------------------------------------
# _import_selective_profile
# ---------------------------------------------------------------------------


class TestImportSelectiveProfile:
    """Tests for _import_selective_profile method."""

    def test_merge_into_existing_profile(self, importer, profile_manager, temp_storage):
        """Test selective import merges into an existing profile."""
        profile_manager.create_profile("sel_exist", "Existing for selective")
        profile_manager.update_profile(
            "sel_exist",
            preferences={
                "global": {"old_key": "old_val"},
                "directory_specific": {"/old": {"x": 1}},
            },
        )

        selective_data = {
            "profile_name": "sel_exist",
            "description": "Selective import",
            "profile_version": "1.0",
            "export_type": "selective",
            "preferences": {
                "global": {"new_key": "new_val"},
                "directory_specific": {"/new": {"y": 2}},
            },
            "learned_patterns": {"new_pat": "val"},
            "confidence_data": {"new_conf": 0.8},
        }

        result = importer._import_selective_profile(selective_data, "sel_exist")

        assert result is not None
        # Old and new global prefs should be merged
        assert "old_key" in result.preferences["global"]
        assert "new_key" in result.preferences["global"]
        # Directory-specific merged
        assert "/old" in result.preferences["directory_specific"]
        assert "/new" in result.preferences["directory_specific"]

    def test_create_new_profile_for_selective(self, importer, temp_storage):
        """Test selective import creates a new profile when none exists."""
        selective_data = {
            "profile_name": "sel_new",
            "description": "New selective",
            "profile_version": "1.0",
            "export_type": "selective",
            "preferences": {"global": {"k": "v"}},
        }

        result = importer._import_selective_profile(selective_data, "sel_new")

        assert result is not None
        assert result.profile_name == "sel_new"
        assert "k" in result.preferences["global"]

    def test_selective_create_fails(self, importer, profile_manager, temp_storage):
        """Test selective import returns None when create_profile fails."""
        selective_data = {
            "profile_name": "fail_create",
            "description": "Fail create",
            "export_type": "selective",
            "preferences": {},
        }

        with patch.object(profile_manager, "create_profile", return_value=None):
            result = importer._import_selective_profile(selective_data, "fail_create")

        assert result is None

    def test_selective_save_fails(self, importer, profile_manager, temp_storage):
        """Test selective import returns None when update_profile fails."""
        profile_manager.create_profile("save_fail", "Test")

        selective_data = {
            "profile_name": "save_fail",
            "description": "Save fail",
            "export_type": "selective",
            "preferences": {"global": {"a": "b"}},
        }

        with patch.object(profile_manager, "update_profile", return_value=False):
            result = importer._import_selective_profile(selective_data, "save_fail")

        assert result is None

    def test_selective_without_optional_sections(self, importer, temp_storage):
        """Test selective import when learned_patterns and confidence_data absent."""
        selective_data = {
            "profile_name": "minimal_sel",
            "description": "Minimal selective",
            "export_type": "selective",
            "preferences": {},
        }

        result = importer._import_selective_profile(selective_data, "minimal_sel")

        assert result is not None
        assert result.profile_name == "minimal_sel"


# ---------------------------------------------------------------------------
# _backup_profile
# ---------------------------------------------------------------------------


class TestBackupProfile:
    """Tests for _backup_profile method."""

    def test_backup_creates_file(self, importer, profile_manager, temp_storage):
        """Test that _backup_profile creates a backup file."""
        profile = profile_manager.create_profile("bk_test", "Backup test profile")

        with patch(
            "file_organizer.services.intelligence.profile_exporter.ProfileExporter"
        ) as MockExporter:
            mock_instance = MockExporter.return_value
            mock_instance.export_profile.return_value = True
            importer._backup_profile(profile)

        # Verify backup directory was created
        backup_dir = profile_manager.storage_path / "backups"
        assert backup_dir.exists()

        # Verify exporter was called
        mock_instance.export_profile.assert_called_once()

    def test_backup_exception_handled(self, importer, profile_manager):
        """Test that _backup_profile handles exceptions gracefully."""
        profile = profile_manager.create_profile("bk_exc", "Backup exception")

        with patch(
            "file_organizer.services.intelligence.profile_exporter.ProfileExporter",
            side_effect=RuntimeError("export error"),
        ):
            # Should not raise
            importer._backup_profile(profile)


# ---------------------------------------------------------------------------
# import_selective
# ---------------------------------------------------------------------------


class TestImportSelective:
    """Tests for import_selective method."""

    def test_import_global_only(self, importer, profile_manager, temp_storage):
        """Test selective import of global preferences only."""
        profile_manager.create_profile("sel_target", "Target profile")

        export_file = temp_storage / "sel.json"
        data = _make_valid_export(profile_name="source")
        _write_json(export_file, data)

        result = importer.import_selective(export_file, ["global"], "sel_target")

        assert result is not None
        assert result.profile_name == "sel_target"
        assert "pref_a" in result.preferences["global"]

    def test_import_directory_specific_only(self, importer, profile_manager, temp_storage):
        """Test selective import of directory_specific preferences only."""
        profile_manager.create_profile("ds_target", "Target profile")

        export_file = temp_storage / "ds.json"
        data = _make_valid_export()
        _write_json(export_file, data)

        result = importer.import_selective(
            export_file, ["directory_specific"], "ds_target"
        )

        assert result is not None
        assert "/some/path" in result.preferences["directory_specific"]

    def test_import_learned_patterns(self, importer, profile_manager, temp_storage):
        """Test selective import of learned_patterns."""
        profile_manager.create_profile("lp_target", "Target")

        export_file = temp_storage / "lp.json"
        data = _make_valid_export()
        _write_json(export_file, data)

        result = importer.import_selective(
            export_file, ["learned_patterns"], "lp_target"
        )

        assert result is not None

    def test_import_confidence_data(self, importer, profile_manager, temp_storage):
        """Test selective import of confidence_data."""
        profile_manager.create_profile("cd_target", "Target")

        export_file = temp_storage / "cd.json"
        data = _make_valid_export()
        _write_json(export_file, data)

        result = importer.import_selective(
            export_file, ["confidence_data"], "cd_target"
        )

        assert result is not None

    def test_import_multiple_preference_types(self, importer, profile_manager, temp_storage):
        """Test selective import of multiple preference types at once."""
        profile_manager.create_profile("multi_target", "Target")

        export_file = temp_storage / "multi.json"
        data = _make_valid_export()
        _write_json(export_file, data)

        result = importer.import_selective(
            export_file,
            ["global", "directory_specific", "learned_patterns", "confidence_data"],
            "multi_target",
        )

        assert result is not None

    def test_import_selective_uses_default_name(self, importer, temp_storage):
        """Test selective import defaults to source profile name when no target."""
        export_file = temp_storage / "default.json"
        data = _make_valid_export(profile_name="source_name")
        _write_json(export_file, data)

        result = importer.import_selective(export_file, ["global"])

        assert result is not None
        assert result.profile_name == "source_name"

    def test_import_selective_invalid_file(self, importer, temp_storage):
        """Test selective import with invalid file returns None."""
        bad = temp_storage / "bad.json"
        with open(bad, "w") as f:
            f.write("not json")

        result = importer.import_selective(bad, ["global"])
        assert result is None

    def test_import_selective_empty_profile_data(self, importer, temp_storage):
        """Test selective import when validation returns empty profile_data."""
        export_file = temp_storage / "empty.json"
        _write_json(export_file, _make_valid_export())

        fake_result = ValidationResult(valid=True, errors=[], warnings=[], profile_data=None)
        with patch.object(importer, "validate_import_file", return_value=fake_result):
            result = importer.import_selective(export_file, ["global"])

        assert result is None

    def test_import_selective_exception(self, importer, temp_storage):
        """Test selective import handles exceptions gracefully."""
        export_file = temp_storage / "exc.json"
        _write_json(export_file, _make_valid_export())

        with patch.object(
            importer, "validate_import_file", side_effect=RuntimeError("boom")
        ):
            result = importer.import_selective(export_file, ["global"])

        assert result is None

    def test_import_selective_unknown_pref_type_ignored(
        self, importer, profile_manager, temp_storage
    ):
        """Test that unknown preference types in list are silently ignored."""
        profile_manager.create_profile("ignore_target", "Target")

        export_file = temp_storage / "ignore.json"
        data = _make_valid_export()
        _write_json(export_file, data)

        result = importer.import_selective(
            export_file, ["unknown_type", "global"], "ignore_target"
        )

        assert result is not None
