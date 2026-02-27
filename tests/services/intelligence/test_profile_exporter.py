"""Tests for ProfileExporter.

Covers full export, selective export, validation, preview, size estimation,
and multi-profile export.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.mark.unit
class TestProfileExporter(unittest.TestCase):
    """Test cases for ProfileExporter."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())

        # Create a mock ProfileManager and Profile
        self.mock_manager = MagicMock()
        self.mock_profile = MagicMock()
        self.mock_profile.profile_name = "test_profile"
        self.mock_profile.description = "A test profile"
        self.mock_profile.profile_version = "1.0"
        self.mock_profile.created = "2024-01-01T00:00:00Z"
        self.mock_profile.updated = "2024-01-02T00:00:00Z"
        self.mock_profile.preferences = {
            "global": {
                "naming_patterns": {"doc": "Documents"},
                "folder_mappings": {".pdf": "PDFs"},
            },
            "directory_specific": {},
        }
        self.mock_profile.learned_patterns = {"pattern1": "value1"}
        self.mock_profile.confidence_data = {"conf1": 0.9}
        self.mock_profile.validate.return_value = True
        self.mock_profile.to_dict.return_value = {
            "profile_name": "test_profile",
            "description": "A test profile",
            "profile_version": "1.0",
            "preferences": self.mock_profile.preferences,
            "learned_patterns": self.mock_profile.learned_patterns,
            "confidence_data": self.mock_profile.confidence_data,
        }

        self.mock_manager.get_profile.return_value = self.mock_profile

    def tearDown(self):
        """Clean up."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _make_exporter(self):
        from file_organizer.services.intelligence.profile_exporter import (
            ProfileExporter,
        )

        return ProfileExporter(self.mock_manager)

    def test_export_profile_success(self):
        """Test successful full profile export."""
        exporter = self._make_exporter()
        out_path = self.test_dir / "export.json"

        result = exporter.export_profile("test_profile", out_path)
        self.assertTrue(result)
        self.assertTrue(out_path.exists())

        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["profile_name"], "test_profile")
        self.assertIn("exported_at", data)
        self.assertEqual(data["export_version"], "1.0")

    def test_export_profile_not_found(self):
        """Test export with missing profile."""
        self.mock_manager.get_profile.return_value = None
        exporter = self._make_exporter()

        result = exporter.export_profile(
            "missing", self.test_dir / "out.json"
        )
        self.assertFalse(result)

    def test_export_profile_validation_fails(self):
        """Test export when profile validation fails."""
        self.mock_profile.validate.return_value = False
        exporter = self._make_exporter()

        result = exporter.export_profile(
            "test_profile", self.test_dir / "out.json"
        )
        self.assertFalse(result)

    def test_export_profile_exception(self):
        """Test export handles exceptions gracefully."""
        self.mock_manager.get_profile.side_effect = RuntimeError("db error")
        exporter = self._make_exporter()

        result = exporter.export_profile(
            "test_profile", self.test_dir / "out.json"
        )
        self.assertFalse(result)

    def test_export_selective_global(self):
        """Test selective export with global preferences."""
        exporter = self._make_exporter()
        out_path = self.test_dir / "selective.json"

        result = exporter.export_selective(
            "test_profile", out_path, ["global"]
        )
        self.assertTrue(result)

        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["export_type"], "selective")
        self.assertIn("global", data["preferences"])

    def test_export_selective_naming(self):
        """Test selective export with naming preferences."""
        exporter = self._make_exporter()
        out_path = self.test_dir / "naming.json"

        result = exporter.export_selective(
            "test_profile", out_path, ["naming"]
        )
        self.assertTrue(result)

        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("naming_patterns", data["preferences"].get("global", {}))

    def test_export_selective_folders(self):
        """Test selective export with folder preferences."""
        exporter = self._make_exporter()
        out_path = self.test_dir / "folders.json"

        result = exporter.export_selective(
            "test_profile", out_path, ["folders"]
        )
        self.assertTrue(result)

        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("folder_mappings", data["preferences"].get("global", {}))

    def test_export_selective_directory_specific(self):
        """Test selective export with directory_specific preferences."""
        exporter = self._make_exporter()
        out_path = self.test_dir / "dir_spec.json"

        result = exporter.export_selective(
            "test_profile", out_path, ["directory_specific"]
        )
        self.assertTrue(result)

    def test_export_selective_learned_patterns(self):
        """Test selective export with learned_patterns."""
        exporter = self._make_exporter()
        out_path = self.test_dir / "patterns.json"

        result = exporter.export_selective(
            "test_profile", out_path, ["learned_patterns"]
        )
        self.assertTrue(result)

        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["learned_patterns"], {"pattern1": "value1"})

    def test_export_selective_confidence_data(self):
        """Test selective export with confidence_data."""
        exporter = self._make_exporter()
        out_path = self.test_dir / "confidence.json"

        result = exporter.export_selective(
            "test_profile", out_path, ["confidence_data"]
        )
        self.assertTrue(result)

        with open(out_path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["confidence_data"], {"conf1": 0.9})

    def test_export_selective_not_found(self):
        """Test selective export with missing profile."""
        self.mock_manager.get_profile.return_value = None
        exporter = self._make_exporter()

        result = exporter.export_selective(
            "missing", self.test_dir / "out.json", ["global"]
        )
        self.assertFalse(result)

    def test_export_selective_exception(self):
        """Test selective export handles exceptions."""
        self.mock_manager.get_profile.side_effect = RuntimeError("err")
        exporter = self._make_exporter()

        result = exporter.export_selective(
            "test_profile", self.test_dir / "out.json", ["global"]
        )
        self.assertFalse(result)

    def test_validate_export_valid_full(self):
        """Test validate_export with valid full export."""
        exporter = self._make_exporter()
        file_path = self.test_dir / "valid.json"
        data = {
            "profile_name": "test",
            "profile_version": "1.0",
            "exported_at": "2024-01-01T00:00:00Z",
            "preferences": {"global": {}, "directory_specific": {}},
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        self.assertTrue(exporter.validate_export(file_path))

    def test_validate_export_valid_selective(self):
        """Test validate_export with valid selective export."""
        exporter = self._make_exporter()
        file_path = self.test_dir / "selective.json"
        data = {
            "profile_name": "test",
            "profile_version": "1.0",
            "exported_at": "2024-01-01T00:00:00Z",
            "export_type": "selective",
            "included_preferences": ["global"],
            "preferences": {},
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        self.assertTrue(exporter.validate_export(file_path))

    def test_validate_export_missing_file(self):
        """Test validate_export with non-existent file."""
        exporter = self._make_exporter()
        self.assertFalse(
            exporter.validate_export(self.test_dir / "missing.json")
        )

    def test_validate_export_missing_fields(self):
        """Test validate_export with missing required fields."""
        exporter = self._make_exporter()
        file_path = self.test_dir / "incomplete.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({"profile_name": "x"}, f)

        self.assertFalse(exporter.validate_export(file_path))

    def test_validate_export_invalid_json(self):
        """Test validate_export with invalid JSON."""
        exporter = self._make_exporter()
        file_path = self.test_dir / "bad.json"
        file_path.write_text("not json")

        self.assertFalse(exporter.validate_export(file_path))

    def test_validate_export_missing_preferences_full(self):
        """Test validate_export fails when full export missing preferences."""
        exporter = self._make_exporter()
        file_path = self.test_dir / "no_prefs.json"
        data = {
            "profile_name": "test",
            "profile_version": "1.0",
            "exported_at": "2024-01-01T00:00:00Z",
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        self.assertFalse(exporter.validate_export(file_path))

    def test_validate_export_invalid_preferences_type(self):
        """Test validate_export fails with non-dict preferences."""
        exporter = self._make_exporter()
        file_path = self.test_dir / "bad_prefs.json"
        data = {
            "profile_name": "test",
            "profile_version": "1.0",
            "exported_at": "2024-01-01T00:00:00Z",
            "preferences": "not a dict",
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        self.assertFalse(exporter.validate_export(file_path))

    def test_validate_export_missing_global_in_preferences(self):
        """Test validate_export fails when global key missing."""
        exporter = self._make_exporter()
        file_path = self.test_dir / "no_global.json"
        data = {
            "profile_name": "test",
            "profile_version": "1.0",
            "exported_at": "2024-01-01T00:00:00Z",
            "preferences": {"only_one": {}},
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        self.assertFalse(exporter.validate_export(file_path))

    def test_validate_export_selective_missing_included(self):
        """Test validate_export fails for selective without included_preferences."""
        exporter = self._make_exporter()
        file_path = self.test_dir / "sel_missing.json"
        data = {
            "profile_name": "test",
            "profile_version": "1.0",
            "exported_at": "2024-01-01T00:00:00Z",
            "export_type": "selective",
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        self.assertFalse(exporter.validate_export(file_path))

    def test_validate_export_invalid_timestamp(self):
        """Test validate_export fails with bad timestamp."""
        exporter = self._make_exporter()
        file_path = self.test_dir / "bad_ts.json"
        data = {
            "profile_name": "test",
            "profile_version": "1.0",
            "exported_at": "not-a-date",
            "preferences": {"global": {}, "directory_specific": {}},
        }
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f)

        self.assertFalse(exporter.validate_export(file_path))

    def test_validate_export_general_exception(self):
        """Test validate_export handles unexpected exceptions."""
        exporter = self._make_exporter()
        # Pass an integer instead of Path to trigger exception
        self.assertFalse(exporter.validate_export(12345))

    def test_preview_export_success(self):
        """Test preview_export returns stats."""
        exporter = self._make_exporter()
        preview = exporter.preview_export("test_profile")

        self.assertIsNotNone(preview)
        self.assertEqual(preview["profile_name"], "test_profile")
        self.assertIn("statistics", preview)
        self.assertIn("export_size_estimate", preview)

    def test_preview_export_not_found(self):
        """Test preview_export returns None when profile missing."""
        self.mock_manager.get_profile.return_value = None
        exporter = self._make_exporter()

        result = exporter.preview_export("missing")
        self.assertIsNone(result)

    def test_preview_export_exception(self):
        """Test preview_export returns None on exception."""
        self.mock_manager.get_profile.side_effect = RuntimeError("err")
        exporter = self._make_exporter()

        result = exporter.preview_export("test_profile")
        self.assertIsNone(result)

    def test_estimate_export_size_bytes(self):
        """Test _estimate_export_size for small profile."""
        exporter = self._make_exporter()
        small_profile = MagicMock()
        small_profile.to_dict.return_value = {"a": "b"}

        result = exporter._estimate_export_size(small_profile)
        self.assertTrue(result.endswith("B"))

    def test_estimate_export_size_kb(self):
        """Test _estimate_export_size for medium profile."""
        exporter = self._make_exporter()
        medium_profile = MagicMock()
        medium_profile.to_dict.return_value = {"data": "x" * 2000}

        result = exporter._estimate_export_size(medium_profile)
        self.assertTrue(result.endswith("KB"))

    def test_estimate_export_size_mb(self):
        """Test _estimate_export_size for large profile."""
        exporter = self._make_exporter()
        large_profile = MagicMock()
        large_profile.to_dict.return_value = {"data": "x" * 1500000}

        result = exporter._estimate_export_size(large_profile)
        self.assertTrue(result.endswith("MB"))

    def test_estimate_export_size_exception(self):
        """Test _estimate_export_size returns 'Unknown' on error."""
        exporter = self._make_exporter()
        bad_profile = MagicMock()
        bad_profile.to_dict.side_effect = RuntimeError("err")

        result = exporter._estimate_export_size(bad_profile)
        self.assertEqual(result, "Unknown")

    def test_export_multiple(self):
        """Test exporting multiple profiles."""
        exporter = self._make_exporter()
        out_dir = self.test_dir / "multi"

        results = exporter.export_multiple(
            ["test_profile", "test_profile"], out_dir
        )
        self.assertIn("test_profile", results)
        self.assertTrue(results["test_profile"])

    def test_export_multiple_partial_failure(self):
        """Test export_multiple with some failures."""
        exporter = self._make_exporter()
        # First call succeeds, second returns None for profile
        self.mock_manager.get_profile.side_effect = [
            self.mock_profile,
            None,
        ]
        out_dir = self.test_dir / "multi2"

        results = exporter.export_multiple(["good", "bad"], out_dir)
        self.assertTrue(results["good"])
        self.assertFalse(results["bad"])

    def test_get_current_timestamp(self):
        """Test timestamp format."""
        exporter = self._make_exporter()
        ts = exporter._get_current_timestamp()
        self.assertTrue(ts.endswith("Z"))
        self.assertNotIn("+00:00", ts)


if __name__ == "__main__":
    unittest.main()
