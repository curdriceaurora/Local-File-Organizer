"""
Unit tests for DirectoryPrefs class.

Tests directory-level preference management with hierarchical inheritance.
"""

import pytest
from pathlib import Path
from file_organizer.services.intelligence.directory_prefs import DirectoryPrefs


class TestDirectoryPrefs:
    """Test suite for DirectoryPrefs class."""

    @pytest.fixture
    def dir_prefs(self):
        """Create a fresh DirectoryPrefs instance for each test."""
        return DirectoryPrefs()

    def test_initialization(self, dir_prefs):
        """Test DirectoryPrefs initializes with empty preferences."""
        stats = dir_prefs.get_statistics()
        assert stats["total_directories"] == 0
        assert stats["override_parent_count"] == 0
        assert stats["inheritance_enabled_count"] == 0

    def test_set_and_get_preference(self, dir_prefs):
        """Test setting and getting a single preference."""
        test_path = Path("/home/user/documents")
        pref = {
            "folder_mappings": {"pdf": "PDFs"},
            "confidence": 0.8
        }

        dir_prefs.set_preference(test_path, pref)

        result = dir_prefs.get_preference_with_inheritance(test_path)
        assert result is not None
        assert result["folder_mappings"]["pdf"] == "PDFs"
        assert result["confidence"] == 0.8

    def test_preference_inheritance(self, dir_prefs):
        """Test that child directories inherit parent preferences."""
        parent_path = Path("/home/user")
        child_path = Path("/home/user/documents")

        parent_pref = {"global_setting": "parent_value"}
        child_pref = {"folder_mappings": {"pdf": "PDFs"}}

        dir_prefs.set_preference(parent_path, parent_pref)
        dir_prefs.set_preference(child_path, child_pref)

        result = dir_prefs.get_preference_with_inheritance(child_path)

        # Should have both parent and child preferences
        assert result["global_setting"] == "parent_value"
        assert result["folder_mappings"]["pdf"] == "PDFs"

    def test_deep_inheritance_chain(self, dir_prefs):
        """Test inheritance across multiple directory levels."""
        root = Path("/home/user")
        level1 = Path("/home/user/documents")
        level2 = Path("/home/user/documents/work")
        level3 = Path("/home/user/documents/work/projects")

        dir_prefs.set_preference(root, {"root_setting": "root"})
        dir_prefs.set_preference(level1, {"level1_setting": "l1"})
        dir_prefs.set_preference(level2, {"level2_setting": "l2"})

        result = dir_prefs.get_preference_with_inheritance(level3)

        # Should inherit all levels
        assert result["root_setting"] == "root"
        assert result["level1_setting"] == "l1"
        assert result["level2_setting"] == "l2"

    def test_child_overrides_parent(self, dir_prefs):
        """Test that child preferences override parent for same keys."""
        parent = Path("/home/user")
        child = Path("/home/user/documents")

        parent_pref = {"folder_mappings": {"pdf": "Documents"}}
        child_pref = {"folder_mappings": {"pdf": "PDFs"}}

        dir_prefs.set_preference(parent, parent_pref)
        dir_prefs.set_preference(child, child_pref)

        result = dir_prefs.get_preference_with_inheritance(child)

        # Child should override parent
        assert result["folder_mappings"]["pdf"] == "PDFs"

    def test_override_parent_flag(self, dir_prefs):
        """Test override_parent flag stops inheritance."""
        parent = Path("/home/user")
        child = Path("/home/user/documents")

        parent_pref = {"parent_setting": "should_not_inherit"}
        child_pref = {"child_setting": "only_this"}

        dir_prefs.set_preference(parent, parent_pref)
        dir_prefs.set_preference(child, child_pref, override_parent=True)

        result = dir_prefs.get_preference_with_inheritance(child)

        # Should only have child preference, not parent
        assert "child_setting" in result
        assert "parent_setting" not in result

    def test_deep_merge_nested_dicts(self, dir_prefs):
        """Test that nested dictionaries are merged properly."""
        parent = Path("/home/user")
        child = Path("/home/user/documents")

        parent_pref = {
            "folder_mappings": {
                "pdf": "Documents",
                "txt": "TextFiles"
            }
        }
        child_pref = {
            "folder_mappings": {
                "pdf": "PDFs",  # Override this
                "doc": "WordDocs"  # Add this
            }
        }

        dir_prefs.set_preference(parent, parent_pref)
        dir_prefs.set_preference(child, child_pref)

        result = dir_prefs.get_preference_with_inheritance(child)

        # Should have merged mappings
        assert result["folder_mappings"]["pdf"] == "PDFs"  # Overridden
        assert result["folder_mappings"]["txt"] == "TextFiles"  # Inherited
        assert result["folder_mappings"]["doc"] == "WordDocs"  # Added

    def test_no_preference_returns_none(self, dir_prefs):
        """Test that querying a path with no preferences returns None."""
        result = dir_prefs.get_preference_with_inheritance(Path("/nonexistent"))
        assert result is None

    def test_list_directory_preferences(self, dir_prefs):
        """Test listing all directory preferences."""
        path1 = Path("/home/user")
        path2 = Path("/home/user/documents")

        dir_prefs.set_preference(path1, {"setting1": "value1"})
        dir_prefs.set_preference(path2, {"setting2": "value2"})

        prefs_list = dir_prefs.list_directory_preferences()

        assert len(prefs_list) == 2
        paths = [p[0] for p in prefs_list]
        assert any(str(p).endswith("user") for p in paths)
        assert any(str(p).endswith("documents") for p in paths)

    def test_remove_preference(self, dir_prefs):
        """Test removing a preference."""
        test_path = Path("/home/user/documents")
        dir_prefs.set_preference(test_path, {"setting": "value"})

        # Verify it exists
        assert dir_prefs.get_preference_with_inheritance(test_path) is not None

        # Remove it
        removed = dir_prefs.remove_preference(test_path)
        assert removed is True

        # Verify it's gone
        assert dir_prefs.get_preference_with_inheritance(test_path) is None

    def test_remove_nonexistent_preference(self, dir_prefs):
        """Test removing a preference that doesn't exist."""
        removed = dir_prefs.remove_preference(Path("/nonexistent"))
        assert removed is False

    def test_clear_all(self, dir_prefs):
        """Test clearing all preferences."""
        dir_prefs.set_preference(Path("/path1"), {"setting": "value"})
        dir_prefs.set_preference(Path("/path2"), {"setting": "value"})

        assert len(dir_prefs.list_directory_preferences()) == 2

        dir_prefs.clear_all()

        assert len(dir_prefs.list_directory_preferences()) == 0

    def test_statistics(self, dir_prefs):
        """Test preference statistics."""
        dir_prefs.set_preference(Path("/path1"), {"s": "v"}, override_parent=False)
        dir_prefs.set_preference(Path("/path2"), {"s": "v"}, override_parent=True)
        dir_prefs.set_preference(Path("/path3"), {"s": "v"}, override_parent=False)

        stats = dir_prefs.get_statistics()

        assert stats["total_directories"] == 3
        assert stats["override_parent_count"] == 1
        assert stats["inheritance_enabled_count"] == 2

    def test_path_normalization(self, dir_prefs):
        """Test that paths are normalized (resolved)."""
        # Set preference with relative path
        dir_prefs.set_preference(Path("."), {"setting": "value"})

        # Get with absolute path
        result = dir_prefs.get_preference_with_inheritance(Path.cwd())

        assert result is not None
        assert result["setting"] == "value"

    def test_metadata_not_in_result(self, dir_prefs):
        """Test that internal metadata is not included in results."""
        test_path = Path("/home/user")
        dir_prefs.set_preference(test_path, {"setting": "value"})

        result = dir_prefs.get_preference_with_inheritance(test_path)

        # Internal fields should not be present
        assert "_override_parent" not in result
        assert "_path" not in result

    def test_metadata_not_in_list(self, dir_prefs):
        """Test that internal metadata is not included in list results."""
        dir_prefs.set_preference(Path("/home/user"), {"setting": "value"})

        prefs_list = dir_prefs.list_directory_preferences()
        pref_dict = prefs_list[0][1]

        # Internal fields should not be present
        assert "_override_parent" not in pref_dict
        assert "_path" not in pref_dict

    def test_empty_preference_dict(self, dir_prefs):
        """Test setting an empty preference dictionary."""
        test_path = Path("/home/user")
        dir_prefs.set_preference(test_path, {})

        result = dir_prefs.get_preference_with_inheritance(test_path)

        # Should return empty dict (not None)
        assert result == {}

    def test_complex_inheritance_scenario(self, dir_prefs):
        """Test a complex real-world inheritance scenario."""
        # Setup: root has global settings
        root = Path("/home/user")
        dir_prefs.set_preference(root, {
            "naming_patterns": {"prefix": "user_"},
            "confidence": 0.7
        })

        # Documents overrides naming, adds folder mappings
        docs = Path("/home/user/documents")
        dir_prefs.set_preference(docs, {
            "naming_patterns": {"prefix": "doc_"},
            "folder_mappings": {"pdf": "PDFs"}
        })

        # Work documents adds more mappings
        work = Path("/home/user/documents/work")
        dir_prefs.set_preference(work, {
            "folder_mappings": {"xlsx": "Spreadsheets"},
            "confidence": 0.9
        })

        result = dir_prefs.get_preference_with_inheritance(work)

        # Should have merged everything correctly
        assert result["naming_patterns"]["prefix"] == "doc_"  # From docs
        assert result["folder_mappings"]["pdf"] == "PDFs"  # From docs
        assert result["folder_mappings"]["xlsx"] == "Spreadsheets"  # From work
        assert result["confidence"] == 0.9  # From work (overrides root)

    def test_inheritance_stops_at_override(self, dir_prefs):
        """Test that inheritance chain stops at override_parent=True."""
        grandparent = Path("/home/user")
        parent = Path("/home/user/documents")
        child = Path("/home/user/documents/work")

        dir_prefs.set_preference(grandparent, {"gp": "value"})
        dir_prefs.set_preference(parent, {"p": "value"}, override_parent=True)
        dir_prefs.set_preference(child, {"c": "value"})

        result = dir_prefs.get_preference_with_inheritance(child)

        # Should have parent and child, but not grandparent
        assert "p" in result
        assert "c" in result
        assert "gp" not in result
