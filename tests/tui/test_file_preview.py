"""Tests for file_organizer.tui.file_preview module.

Covers FileSelectionManager selection tracking, toggle, select_all, clear,
and FilePreviewPanel widget initialization and text extension tracking.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Static

from file_organizer.tui.file_preview import (
    FilePreviewPanel,
    FileSelectionManager,
)

pytestmark = [pytest.mark.unit]


# -----------------------------------------------------------------------
# FileSelectionManager
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFileSelectionManager:
    """Test FileSelectionManager selection tracking."""

    def test_initialization_empty(self) -> None:
        """Test that selection manager starts empty."""
        manager = FileSelectionManager()
        assert manager.count == 0
        assert manager.selected_files == set()

    def test_toggle_adds_path(self) -> None:
        """Test that toggle adds a new path."""
        manager = FileSelectionManager()
        path = Path("/tmp/file.txt")
        result = manager.toggle(path)
        assert result is True
        assert manager.count == 1
        assert path in manager.selected_files

    def test_toggle_removes_path(self) -> None:
        """Test that toggle removes a selected path."""
        manager = FileSelectionManager()
        path = Path("/tmp/file.txt")
        manager.toggle(path)  # Add
        result = manager.toggle(path)  # Remove
        assert result is False
        assert manager.count == 0
        assert path not in manager.selected_files

    def test_toggle_multiple_paths(self) -> None:
        """Test toggling multiple paths."""
        manager = FileSelectionManager()
        path1 = Path("/tmp/file1.txt")
        path2 = Path("/tmp/file2.txt")
        path3 = Path("/tmp/file3.txt")

        manager.toggle(path1)
        manager.toggle(path2)
        manager.toggle(path3)
        assert manager.count == 3

        manager.toggle(path2)
        assert manager.count == 2
        assert path2 not in manager.selected_files

    def test_toggle_returns_correct_state(self) -> None:
        """Test that toggle returns the new selection state."""
        manager = FileSelectionManager()
        path = Path("/tmp/file.txt")
        assert manager.toggle(path) is True
        assert manager.toggle(path) is False
        assert manager.toggle(path) is True

    def test_select_all_adds_all_paths(self) -> None:
        """Test select_all adds all provided paths."""
        manager = FileSelectionManager()
        paths = {
            Path("/tmp/file1.txt"),
            Path("/tmp/file2.txt"),
            Path("/tmp/file3.txt"),
        }
        manager.select_all(paths)
        assert manager.count == 3
        assert manager.selected_files == paths

    def test_select_all_adds_to_existing(self) -> None:
        """Test that select_all adds to existing selections."""
        manager = FileSelectionManager()
        path1 = Path("/tmp/file1.txt")
        manager.toggle(path1)

        paths = {
            Path("/tmp/file2.txt"),
            Path("/tmp/file3.txt"),
        }
        manager.select_all(paths)
        assert manager.count == 3
        assert path1 in manager.selected_files

    def test_select_all_empty_set(self) -> None:
        """Test select_all with empty set does nothing."""
        manager = FileSelectionManager()
        manager.select_all(set())
        assert manager.count == 0

    def test_clear_removes_all_selections(self) -> None:
        """Test that clear removes all paths."""
        manager = FileSelectionManager()
        manager.toggle(Path("/tmp/file1.txt"))
        manager.toggle(Path("/tmp/file2.txt"))
        manager.toggle(Path("/tmp/file3.txt"))
        assert manager.count == 3

        manager.clear()
        assert manager.count == 0
        assert manager.selected_files == set()

    def test_clear_on_empty_manager(self) -> None:
        """Test that clear on empty manager is safe."""
        manager = FileSelectionManager()
        manager.clear()
        assert manager.count == 0

    def test_count_property(self) -> None:
        """Test that count property reflects selection size."""
        manager = FileSelectionManager()
        assert manager.count == 0

        for i in range(5):
            manager.toggle(Path(f"/tmp/file{i}.txt"))
            assert manager.count == i + 1

        for i in range(5):
            manager.toggle(Path(f"/tmp/file{i}.txt"))
            assert manager.count == 5 - i - 1

    def test_selected_files_returns_copy(self) -> None:
        """Test that selected_files returns a copy, not the internal set."""
        manager = FileSelectionManager()
        path = Path("/tmp/file.txt")
        manager.toggle(path)

        selected = manager.selected_files
        selected.add(Path("/tmp/fake.txt"))  # Modify the returned set

        # Original should not be modified
        assert manager.count == 1
        assert Path("/tmp/fake.txt") not in manager.selected_files

    def test_selected_files_immutability(self) -> None:
        """Test that modifying returned set doesn't affect manager."""
        manager = FileSelectionManager()
        path1 = Path("/tmp/file1.txt")
        path2 = Path("/tmp/file2.txt")
        manager.toggle(path1)

        selected = manager.selected_files
        selected.clear()
        selected.add(path2)

        # Manager should be unchanged
        assert manager.count == 1
        assert path1 in manager.selected_files


# -----------------------------------------------------------------------
# FilePreviewPanel
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFilePreviewPanel:
    """Test FilePreviewPanel widget."""

    def test_inherits_from_static(self) -> None:
        """Test that FilePreviewPanel extends Static."""
        assert issubclass(FilePreviewPanel, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "FilePreviewPanel" in FilePreviewPanel.DEFAULT_CSS

    def test_text_extensions_defined(self) -> None:
        """Test that text extension set is defined."""
        assert hasattr(FilePreviewPanel, "_TEXT_EXTENSIONS")
        extensions = FilePreviewPanel._TEXT_EXTENSIONS
        assert isinstance(extensions, set)
        assert ".txt" in extensions
        assert ".md" in extensions
        assert ".py" in extensions
        assert ".json" in extensions

    def test_text_extensions_contain_common_formats(self) -> None:
        """Test that common text formats are included."""
        extensions = FilePreviewPanel._TEXT_EXTENSIONS
        common = {".txt", ".md", ".py", ".js", ".json", ".yaml", ".csv"}
        for ext in common:
            assert ext in extensions

    def test_panel_initialization(self) -> None:
        """Test FilePreviewPanel can be instantiated."""
        panel = FilePreviewPanel()
        assert panel is not None
        assert isinstance(panel, Static)

    def test_panel_with_custom_attributes(self) -> None:
        """Test FilePreviewPanel with custom attributes."""
        panel = FilePreviewPanel(name="preview", id="file-preview")
        assert panel.name == "preview"
        assert panel.id == "file-preview"


# -----------------------------------------------------------------------
# FileSelectionManager edge cases
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFileSelectionManagerEdgeCases:
    """Test edge cases and special scenarios."""

    def test_same_path_object_vs_equal_paths(self) -> None:
        """Test that different Path objects to same file work correctly."""
        manager = FileSelectionManager()
        path1 = Path("/tmp/file.txt")
        path2 = Path("/tmp/file.txt")

        manager.toggle(path1)
        # Both should refer to the same file
        assert manager.toggle(path2) is False

    def test_path_with_special_characters(self) -> None:
        """Test paths with special characters."""
        manager = FileSelectionManager()
        path = Path("/tmp/file with spaces (1).txt")
        manager.toggle(path)
        assert manager.count == 1
        assert path in manager.selected_files

    def test_absolute_vs_relative_paths(self) -> None:
        """Test that absolute and relative paths are distinct."""
        manager = FileSelectionManager()
        abs_path = Path("/tmp/file.txt")
        rel_path = Path("file.txt")

        manager.toggle(abs_path)
        manager.toggle(rel_path)
        assert manager.count == 2

    def test_large_selection(self) -> None:
        """Test managing large number of selections."""
        manager = FileSelectionManager()
        paths = {Path(f"/tmp/file{i}.txt") for i in range(1000)}
        manager.select_all(paths)
        assert manager.count == 1000

    def test_clear_after_large_selection(self) -> None:
        """Test clearing large selection."""
        manager = FileSelectionManager()
        paths = {Path(f"/tmp/file{i}.txt") for i in range(100)}
        manager.select_all(paths)
        manager.clear()
        assert manager.count == 0

    def test_toggle_repeatedly_same_path(self) -> None:
        """Test toggling same path multiple times."""
        manager = FileSelectionManager()
        path = Path("/tmp/file.txt")

        for i in range(100):
            manager.toggle(path)
            expected_count = 1 if i % 2 == 0 else 0
            assert manager.count == expected_count
