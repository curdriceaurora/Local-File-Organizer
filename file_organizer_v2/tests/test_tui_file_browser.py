"""Tests for the TUI file browser widgets."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


class TestFormatSize:
    """Unit tests for the _format_size helper."""

    def test_bytes(self) -> None:
        from file_organizer.tui.file_browser import _format_size

        assert _format_size(512) == "512 B"

    def test_kilobytes(self) -> None:
        from file_organizer.tui.file_browser import _format_size

        result = _format_size(2048)
        assert "KB" in result

    def test_megabytes(self) -> None:
        from file_organizer.tui.file_browser import _format_size

        result = _format_size(5 * 1024 * 1024)
        assert "MB" in result

    def test_zero(self) -> None:
        from file_organizer.tui.file_browser import _format_size

        assert _format_size(0) == "0 B"


class TestFileBrowserTree:
    """Tests for FileBrowserTree."""

    def test_import(self) -> None:
        from file_organizer.tui.file_browser import FileBrowserTree

        assert FileBrowserTree is not None

    def test_instantiation(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileBrowserTree

        tree = FileBrowserTree(tmp_path)
        assert tree is not None

    def test_extension_filter_set(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileBrowserTree

        tree = FileBrowserTree(tmp_path)
        tree.set_extension_filter({".py", ".txt"})
        assert tree._extension_filter == {".py", ".txt"}

    def test_extension_filter_normalizes_dots(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileBrowserTree

        tree = FileBrowserTree(tmp_path)
        tree.set_extension_filter({"py", "txt"})
        assert tree._extension_filter == {".py", ".txt"}

    def test_extension_filter_clear(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileBrowserTree

        tree = FileBrowserTree(tmp_path)
        tree.set_extension_filter({".py"})
        tree.set_extension_filter(set())
        assert tree._extension_filter == set()

    def test_filter_paths_no_filter(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileBrowserTree

        tree = FileBrowserTree(tmp_path)
        paths = [tmp_path / "a.py", tmp_path / "b.txt"]
        result = list(tree.filter_paths(paths))
        assert result == paths

    def test_filter_paths_with_extension(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileBrowserTree

        # Create real files so is_dir() works
        py_file = tmp_path / "a.py"
        py_file.touch()
        txt_file = tmp_path / "b.txt"
        txt_file.touch()
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        tree = FileBrowserTree(tmp_path)
        tree._extension_filter = {".py"}
        result = list(tree.filter_paths([py_file, txt_file, subdir]))
        # Directories always pass, .py passes, .txt filtered out
        assert py_file in result
        assert subdir in result
        assert txt_file not in result

    def test_vim_bindings_defined(self) -> None:
        from file_organizer.tui.file_browser import FileBrowserTree

        binding_keys = {b.key for b in FileBrowserTree.BINDINGS}
        assert "h" in binding_keys
        assert "j" in binding_keys
        assert "k" in binding_keys
        assert "l" in binding_keys


class TestFileMetadataPanel:
    """Tests for FileMetadataPanel."""

    def test_import(self) -> None:
        from file_organizer.tui.file_browser import FileMetadataPanel

        assert FileMetadataPanel is not None

    def test_show_metadata_file(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileMetadataPanel

        f = tmp_path / "test.txt"
        f.write_text("hello")
        panel = FileMetadataPanel()
        # show_metadata calls update() which requires a live app context,
        # so we mock update to verify it's called with the right content.
        panel.update = MagicMock()
        panel.show_metadata(f)
        panel.update.assert_called_once()
        rendered = panel.update.call_args[0][0]
        assert "test.txt" in rendered
        assert ".txt" in rendered

    def test_show_metadata_missing_path(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileMetadataPanel

        panel = FileMetadataPanel()
        panel.update = MagicMock()
        panel.show_metadata(tmp_path / "nonexistent.dat")
        rendered = panel.update.call_args[0][0]
        assert "not found" in rendered.lower()

    def test_show_metadata_directory(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileMetadataPanel

        panel = FileMetadataPanel()
        panel.update = MagicMock()
        panel.show_metadata(tmp_path)
        rendered = panel.update.call_args[0][0]
        assert "Directory" in rendered


class TestFilterInput:
    """Tests for FilterInput."""

    def test_import(self) -> None:
        from file_organizer.tui.file_browser import FilterInput

        assert FilterInput is not None

    def test_submitted_message(self) -> None:
        from file_organizer.tui.file_browser import FilterInput

        msg = FilterInput.Submitted(".py .txt")
        assert msg.value == ".py .txt"


class TestFileBrowserView:
    """Tests for FileBrowserView."""

    def test_import(self) -> None:
        from file_organizer.tui.file_browser import FileBrowserView

        assert FileBrowserView is not None

    def test_instantiation(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileBrowserView

        view = FileBrowserView(tmp_path, id="view")
        assert view._root_path == tmp_path

    def test_file_highlighted_message(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_browser import FileBrowserView

        msg = FileBrowserView.FileHighlighted(tmp_path / "test.py")
        assert msg.path == tmp_path / "test.py"

    def test_has_filter_binding(self) -> None:
        from file_organizer.tui.file_browser import FileBrowserView

        binding_keys = {b.key for b in FileBrowserView.BINDINGS}
        assert "slash" in binding_keys


class TestTuiExports:
    """Test that the tui __init__ exports are correct."""

    def test_exports(self) -> None:
        from file_organizer.tui import (
            FileBrowserTree,
            FileBrowserView,
            FileMetadataPanel,
            FilterInput,
        )

        assert all(
            cls is not None
            for cls in (FileBrowserTree, FileBrowserView, FileMetadataPanel, FilterInput)
        )
