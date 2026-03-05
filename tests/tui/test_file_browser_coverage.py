"""Coverage tests for file_organizer.tui.file_browser module.

Targets uncovered branches in _format_size, FileBrowserTree filtering,
FileMetadataPanel.show_metadata, FilterInput, and FileBrowserView.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from file_organizer.tui.file_browser import (
    FileBrowserTree,
    FileBrowserView,
    FileMetadataPanel,
    FilterInput,
    _format_size,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# _format_size helper
# ---------------------------------------------------------------------------


class TestFormatSize:
    """Test the _format_size utility function."""

    def test_zero_bytes(self) -> None:
        assert _format_size(0) == "0 B"

    def test_one_byte(self) -> None:
        assert _format_size(1) == "1 B"

    def test_bytes_below_1024(self) -> None:
        assert _format_size(500) == "500 B"

    def test_exactly_1024_is_kb(self) -> None:
        result = _format_size(1024)
        assert "KB" in result
        assert "1.0" in result

    def test_megabytes(self) -> None:
        result = _format_size(1024 * 1024)
        assert "MB" in result

    def test_gigabytes(self) -> None:
        result = _format_size(1024**3)
        assert "GB" in result

    def test_terabytes(self) -> None:
        result = _format_size(1024**4)
        assert "TB" in result

    def test_petabytes(self) -> None:
        result = _format_size(1024**5)
        assert "PB" in result

    def test_decimal_formatting(self) -> None:
        result = _format_size(1536)
        assert "KB" in result
        assert "1.5" in result


# ---------------------------------------------------------------------------
# FileBrowserTree
# ---------------------------------------------------------------------------


class TestFileBrowserTree:
    """Test FileBrowserTree filtering and actions."""

    def test_init_default_path(self) -> None:
        tree = FileBrowserTree()
        assert tree._extension_filter == set()

    def test_set_extension_filter_normalizes(self) -> None:
        tree = FileBrowserTree()
        tree.set_extension_filter({"py", ".txt", "json"})
        assert ".py" in tree._extension_filter
        assert ".txt" in tree._extension_filter
        assert ".json" in tree._extension_filter

    def test_set_extension_filter_empty_clears(self) -> None:
        tree = FileBrowserTree()
        tree.set_extension_filter({".py"})
        assert len(tree._extension_filter) == 1
        tree.set_extension_filter(set())
        assert tree._extension_filter == set()

    def test_filter_paths_no_filter_returns_all(self) -> None:
        tree = FileBrowserTree()
        paths = [Path("a.py"), Path("b.txt"), Path("c.jpg")]
        result = list(tree.filter_paths(paths))
        assert len(result) == 3

    def test_filter_paths_with_filter(self, tmp_path: Path) -> None:
        tree = FileBrowserTree()
        tree._extension_filter = {".py"}
        # Create actual files/dirs so is_dir() works
        py_file = tmp_path / "a.py"
        py_file.touch()
        txt_file = tmp_path / "b.txt"
        txt_file.touch()
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        paths = [py_file, txt_file, subdir]
        result = list(tree.filter_paths(paths))
        # Should include .py file and directory, but not .txt
        assert py_file in result
        assert subdir in result
        assert txt_file not in result

    def test_action_cursor_parent_with_no_node(self) -> None:
        tree = FileBrowserTree()
        with patch.object(type(tree), "cursor_node", new_callable=PropertyMock, return_value=None):
            tree.action_cursor_parent()  # Should not crash

    def test_action_cursor_parent_with_no_parent(self) -> None:
        tree = FileBrowserTree()
        mock_node = MagicMock()
        mock_node.parent = None
        with patch.object(
            type(tree), "cursor_node", new_callable=PropertyMock, return_value=mock_node
        ):
            tree.action_cursor_parent()  # Should not crash

    def test_action_cursor_toggle_expandable_node(self) -> None:
        tree = FileBrowserTree()
        mock_node = MagicMock()
        mock_node.allow_expand = True
        with patch.object(
            type(tree), "cursor_node", new_callable=PropertyMock, return_value=mock_node
        ):
            tree.action_cursor_toggle()
        mock_node.toggle.assert_called_once()

    def test_action_cursor_toggle_file_node(self) -> None:
        tree = FileBrowserTree()
        mock_node = MagicMock()
        mock_node.allow_expand = False
        # Patch FileSelected to avoid constructor issues
        mock_fs = MagicMock()
        with (
            patch.object(
                type(tree), "cursor_node", new_callable=PropertyMock, return_value=mock_node
            ),
            patch.object(tree, "post_message") as mock_post,
            patch.object(type(tree), "FileSelected", mock_fs),
        ):
            tree.action_cursor_toggle()
        mock_post.assert_called_once()
        mock_fs.assert_called_once_with(mock_node)

    def test_action_cursor_toggle_none_node(self) -> None:
        tree = FileBrowserTree()
        with patch.object(type(tree), "cursor_node", new_callable=PropertyMock, return_value=None):
            tree.action_cursor_toggle()  # Should not crash


# ---------------------------------------------------------------------------
# FileMetadataPanel
# ---------------------------------------------------------------------------


class TestFileMetadataPanel:
    """Test FileMetadataPanel.show_metadata branches."""

    def test_path_not_found(self, tmp_path: Path) -> None:
        panel = FileMetadataPanel()
        panel.update = MagicMock()
        panel.show_metadata(tmp_path / "nonexistent.txt")
        rendered = panel.update.call_args[0][0]
        assert "not found" in rendered.lower()

    def test_file_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "test.py"
        f.write_text("hello")
        panel = FileMetadataPanel()
        panel.update = MagicMock()
        panel.show_metadata(f)
        rendered = panel.update.call_args[0][0]
        assert "test.py" in rendered
        assert ".py" in rendered
        assert "UTC" in rendered

    def test_directory_metadata(self, tmp_path: Path) -> None:
        d = tmp_path / "mydir"
        d.mkdir()
        panel = FileMetadataPanel()
        panel.update = MagicMock()
        panel.show_metadata(d)
        rendered = panel.update.call_args[0][0]
        assert "Directory" in rendered

    def test_file_no_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "Makefile"
        f.write_text("all:")
        panel = FileMetadataPanel()
        panel.update = MagicMock()
        panel.show_metadata(f)
        rendered = panel.update.call_args[0][0]
        assert "File" in rendered

    def test_os_error_handling(self, tmp_path: Path) -> None:
        panel = FileMetadataPanel()
        panel.update = MagicMock()
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.stat.side_effect = OSError("permission denied")
        mock_path.name = "forbidden.txt"
        panel.show_metadata(mock_path)
        rendered = panel.update.call_args[0][0]
        assert "Cannot read" in rendered


# ---------------------------------------------------------------------------
# FilterInput
# ---------------------------------------------------------------------------


class TestFilterInput:
    """Test FilterInput toggle and submit behavior."""

    def test_toggle_visibility_shows_and_focuses(self) -> None:
        fi = FilterInput()
        fi.toggle_class = MagicMock()
        fi.has_class = MagicMock(return_value=True)
        fi.focus = MagicMock()
        fi.toggle_visibility()
        fi.toggle_class.assert_called_with("-visible")
        fi.focus.assert_called_once()

    def test_toggle_visibility_hides_and_clears(self) -> None:
        fi = FilterInput()
        fi.toggle_class = MagicMock()
        fi.has_class = MagicMock(return_value=False)
        fi.toggle_visibility()
        assert fi.value == ""

    def test_submitted_message_has_value(self) -> None:
        msg = FilterInput.Submitted("test value")
        assert msg.value == "test value"


# ---------------------------------------------------------------------------
# FileBrowserView
# ---------------------------------------------------------------------------


class TestFileBrowserView:
    """Test FileBrowserView init and bindings."""

    def test_default_init(self) -> None:
        view = FileBrowserView()
        assert view._root_path == Path(".")

    def test_custom_path_init(self) -> None:
        view = FileBrowserView(path="tmp/test")
        assert view._root_path == Path("tmp/test")

    def test_file_highlighted_message(self) -> None:
        msg = FileBrowserView.FileHighlighted(Path("tmp/file.txt"))
        assert msg.path == Path("tmp/file.txt")

    def test_bindings(self) -> None:
        keys = [b.key for b in FileBrowserView.BINDINGS]
        assert "slash" in keys

    def test_action_toggle_filter(self) -> None:
        view = FileBrowserView()
        mock_fi = MagicMock()
        view.query_one = MagicMock(return_value=mock_fi)
        view.action_toggle_filter()
        mock_fi.toggle_visibility.assert_called_once()
