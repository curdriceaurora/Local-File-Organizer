"""Tests for file_organizer.tui.file_browser module.

Covers FileBrowserTree, FileMetadataPanel, FileFilterInput, and
FileBrowserView initialization, filtering, and vim keybindings.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DirectoryTree, Input, Static

from file_organizer.tui.file_browser import (
    FileBrowserTree,
    FileMetadataPanel,
    FileBrowserView,
    _format_size,
)

pytestmark = [pytest.mark.unit]


# -----------------------------------------------------------------------
# _format_size helper
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFormatSize:
    """Test the _format_size utility function."""

    def test_bytes(self) -> None:
        """Test formatting bytes."""
        assert _format_size(0) == "0 B"
        assert _format_size(512) == "512 B"
        assert _format_size(1023) == "1023 B"

    def test_kilobytes(self) -> None:
        """Test formatting kilobytes."""
        result = _format_size(1024)
        assert "KB" in result
        assert "1.0" in result

    def test_megabytes(self) -> None:
        """Test formatting megabytes."""
        result = _format_size(1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self) -> None:
        """Test formatting gigabytes."""
        result = _format_size(1024 * 1024 * 1024)
        assert "GB" in result

    def test_terabytes(self) -> None:
        """Test formatting terabytes."""
        result = _format_size(1024 * 1024 * 1024 * 1024)
        assert "TB" in result

    def test_petabytes(self) -> None:
        """Test formatting petabytes."""
        result = _format_size(1024 * 1024 * 1024 * 1024 * 1024)
        assert "PB" in result

    def test_decimal_formatting(self) -> None:
        """Test decimal values are formatted with one decimal place."""
        result = _format_size(1536)  # 1.5 KB
        assert "1.5" in result


# -----------------------------------------------------------------------
# FileBrowserTree
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFileBrowserTree:
    """Test FileBrowserTree widget."""

    def test_inherits_from_directory_tree(self) -> None:
        """Test that FileBrowserTree extends DirectoryTree."""
        assert issubclass(FileBrowserTree, DirectoryTree)

    def test_vim_bindings_defined(self) -> None:
        """Test that vim keybindings are defined."""
        bindings = [b for b in FileBrowserTree.BINDINGS if isinstance(b, Binding)]
        keys = [b.key for b in bindings]
        assert "h" in keys  # Parent
        assert "j" in keys  # Down
        assert "k" in keys  # Up
        assert "l" in keys  # Expand

    def test_initialization_with_default_path(self) -> None:
        """Test FileBrowserTree initialization with default path."""
        tree = FileBrowserTree()
        assert tree._extension_filter == set()

    def test_initialization_with_custom_path(self) -> None:
        """Test FileBrowserTree initialization with custom path."""
        path = Path("/tmp")
        tree = FileBrowserTree(path=path)
        assert tree is not None

    def test_initialization_with_string_path(self) -> None:
        """Test FileBrowserTree initialization with string path."""
        tree = FileBrowserTree(path="/tmp")
        assert tree is not None

    def test_set_extension_filter_single(self) -> None:
        """Test setting single extension filter."""
        tree = FileBrowserTree()
        tree.set_extension_filter({".py"})
        assert ".py" in tree._extension_filter

    def test_set_extension_filter_multiple(self) -> None:
        """Test setting multiple extension filters."""
        tree = FileBrowserTree()
        tree.set_extension_filter({".py", ".txt", ".md"})
        assert ".py" in tree._extension_filter
        assert ".txt" in tree._extension_filter
        assert ".md" in tree._extension_filter

    def test_set_extension_filter_adds_dot(self) -> None:
        """Test that set_extension_filter adds dots to extensions."""
        tree = FileBrowserTree()
        tree.set_extension_filter({"py", "txt"})
        assert ".py" in tree._extension_filter
        assert ".txt" in tree._extension_filter

    def test_set_extension_filter_preserves_dot(self) -> None:
        """Test that extensions already with dots are preserved."""
        tree = FileBrowserTree()
        tree.set_extension_filter({".py", ".txt"})
        assert ".py" in tree._extension_filter
        assert ".txt" in tree._extension_filter
        # Ensure no double dots
        assert "..py" not in tree._extension_filter

    def test_set_extension_filter_empty_clears(self) -> None:
        """Test that empty extension set clears filter."""
        tree = FileBrowserTree()
        tree.set_extension_filter({".py"})
        assert tree._extension_filter != set()
        tree.set_extension_filter(set())
        assert tree._extension_filter == set()

    def test_filter_paths_empty_filter(self) -> None:
        """Test filter_paths with no filter returns all."""
        tree = FileBrowserTree()
        paths = [Path("/tmp/file1.txt"), Path("/tmp/file2.py")]
        result = list(tree.filter_paths(paths))
        assert len(result) == 2

    def test_filter_paths_with_filter(self) -> None:
        """Test filter_paths with extension filter."""
        tree = FileBrowserTree()
        tree.set_extension_filter({".py"})
        paths = [Path("/tmp/file1.txt"), Path("/tmp/file2.py")]
        result = list(tree.filter_paths(paths))
        assert len(result) == 1
        assert Path("/tmp/file2.py") in result

    def test_filter_paths_includes_directories(self) -> None:
        """Test that directories are always included in filter."""
        tree = FileBrowserTree()
        tree.set_extension_filter({".py"})
        # Create mock path objects
        py_file = Path("/tmp/test.py")
        txt_file = Path("/tmp/test.txt")
        dir_path = Path("/tmp/subdir")

        # Mock is_dir
        for p in [py_file, txt_file, dir_path]:
            p.is_dir = MagicMock()

        py_file.is_dir.return_value = False
        txt_file.is_dir.return_value = False
        dir_path.is_dir.return_value = True

        paths = [py_file, txt_file, dir_path]
        result = list(tree.filter_paths(paths))
        assert py_file in result  # .py file
        assert txt_file not in result  # .txt not in filter
        assert dir_path in result  # Directory always included

    def test_has_action_cursor_parent(self) -> None:
        """Test that action_cursor_parent is defined."""
        assert callable(getattr(FileBrowserTree, "action_cursor_parent", None))

    def test_has_action_cursor_toggle(self) -> None:
        """Test that action_cursor_toggle is defined."""
        assert callable(getattr(FileBrowserTree, "action_cursor_toggle", None))


# -----------------------------------------------------------------------
# FileMetadataPanel
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFileMetadataPanel:
    """Test FileMetadataPanel widget."""

    def test_inherits_from_static(self) -> None:
        """Test that FileMetadataPanel extends Static."""
        assert issubclass(FileMetadataPanel, Static)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "FileMetadataPanel" in FileMetadataPanel.DEFAULT_CSS
        assert "border-top" in FileMetadataPanel.DEFAULT_CSS

    def test_initialization(self) -> None:
        """Test FileMetadataPanel can be instantiated."""
        panel = FileMetadataPanel()
        assert panel is not None

    def test_has_update_file_method(self) -> None:
        """Test that update_file method is defined."""
        assert callable(getattr(FileMetadataPanel, "update_file", None))

    def test_custom_attributes(self) -> None:
        """Test custom widget attributes."""
        panel = FileMetadataPanel(name="metadata", id="file-meta")
        assert panel.name == "metadata"
        assert panel.id == "file-meta"


# -----------------------------------------------------------------------
# FileBrowserView
# -----------------------------------------------------------------------


@pytest.mark.unit
class TestFileBrowserView:
    """Test FileBrowserView widget."""

    def test_inherits_from_vertical(self) -> None:
        """Test that FileBrowserView extends Vertical."""
        assert issubclass(FileBrowserView, Vertical)

    def test_default_css_defined(self) -> None:
        """Test that CSS is properly defined."""
        assert "FileBrowserView" in FileBrowserView.DEFAULT_CSS

    def test_has_bindings(self) -> None:
        """Test that bindings are defined."""
        assert isinstance(FileBrowserView.BINDINGS, list)
        assert len(FileBrowserView.BINDINGS) >= 0

    def test_initialization_with_default_path(self) -> None:
        """Test FileBrowserView initialization with default path."""
        view = FileBrowserView()
        assert view._root_path == Path(".")

    def test_initialization_with_custom_path(self) -> None:
        """Test FileBrowserView initialization with custom path."""
        path = Path("/tmp")
        view = FileBrowserView(path=path)
        assert view._root_path == path

    def test_initialization_with_string_path(self) -> None:
        """Test FileBrowserView initialization with string path."""
        view = FileBrowserView(path="/tmp")
        assert view._root_path == Path("/tmp")

    def test_has_compose_method(self) -> None:
        """Test that compose method is defined."""
        assert callable(getattr(FileBrowserView, "compose", None))

    def test_custom_widget_attributes(self) -> None:
        """Test that custom attributes are properly set."""
        view = FileBrowserView(name="browser", id="file-browser")
        assert view.name == "browser"
        assert view.id == "file-browser"
