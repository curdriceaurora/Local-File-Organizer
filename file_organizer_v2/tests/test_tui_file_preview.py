"""Tests for the TUI file preview and selection widgets."""
from __future__ import annotations

from pathlib import Path


class TestFileSelectionManager:
    """Tests for the FileSelectionManager logic."""

    def test_initial_empty(self) -> None:
        from file_organizer.tui.file_preview import FileSelectionManager

        mgr = FileSelectionManager()
        assert mgr.count == 0
        assert mgr.selected_files == set()

    def test_toggle_select(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FileSelectionManager

        mgr = FileSelectionManager()
        p = tmp_path / "a.txt"
        assert mgr.toggle(p) is True
        assert p in mgr.selected_files
        assert mgr.count == 1

    def test_toggle_deselect(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FileSelectionManager

        mgr = FileSelectionManager()
        p = tmp_path / "a.txt"
        mgr.toggle(p)
        assert mgr.toggle(p) is False
        assert p not in mgr.selected_files
        assert mgr.count == 0

    def test_select_all(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FileSelectionManager

        mgr = FileSelectionManager()
        paths = {tmp_path / "a.txt", tmp_path / "b.txt", tmp_path / "c.txt"}
        mgr.select_all(paths)
        assert mgr.count == 3
        assert mgr.selected_files == paths

    def test_clear(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FileSelectionManager

        mgr = FileSelectionManager()
        mgr.toggle(tmp_path / "a.txt")
        mgr.toggle(tmp_path / "b.txt")
        mgr.clear()
        assert mgr.count == 0

    def test_selected_files_is_copy(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FileSelectionManager

        mgr = FileSelectionManager()
        p = tmp_path / "a.txt"
        mgr.toggle(p)
        # Modifying the returned set shouldn't affect internal state
        files = mgr.selected_files
        files.add(tmp_path / "extra.txt")
        assert mgr.count == 1


class TestFilePreviewPanel:
    """Tests for FilePreviewPanel preview strategies."""

    def test_import(self) -> None:
        from file_organizer.tui.file_preview import FilePreviewPanel

        assert FilePreviewPanel is not None

    def test_preview_text(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FilePreviewPanel

        f = tmp_path / "readme.txt"
        f.write_text("Hello world\nLine 2\n")
        content = FilePreviewPanel._preview_text(f)
        assert "Hello world" in content
        assert "Line 2" in content

    def test_preview_text_truncated(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FilePreviewPanel

        f = tmp_path / "big.txt"
        f.write_text("\n".join(f"line {i}" for i in range(200)))
        content = FilePreviewPanel._preview_text(f, max_lines=50)
        assert "line 0" in content
        assert "line 49" in content
        assert "line 100" not in content

    def test_preview_text_unreadable(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FilePreviewPanel

        content = FilePreviewPanel._preview_text(tmp_path / "nope.txt")
        assert "Cannot read" in content

    def test_preview_image_no_pillow(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FilePreviewPanel

        f = tmp_path / "photo.jpg"
        f.touch()
        # If PIL can't open a 0-byte file, should fall back gracefully
        content = FilePreviewPanel._preview_image(f)
        assert "Image" in content

    def test_preview_generic(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FilePreviewPanel

        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00" * 128)
        content = FilePreviewPanel._preview_generic(f)
        assert "data.bin" in content
        assert "128" in content

    def test_preview_directory(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FilePreviewPanel

        (tmp_path / "child1.txt").touch()
        (tmp_path / "child2.txt").touch()
        content = FilePreviewPanel._preview_directory(tmp_path)
        assert "child1.txt" in content
        assert "child2.txt" in content

    def test_preview_generic_missing(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FilePreviewPanel

        content = FilePreviewPanel._preview_generic(tmp_path / "no_exist.xyz")
        assert "Cannot stat" in content


class TestFilePreviewView:
    """Tests for FilePreviewView."""

    def test_import(self) -> None:
        from file_organizer.tui.file_preview import FilePreviewView

        assert FilePreviewView is not None

    def test_instantiation(self, tmp_path: Path) -> None:
        from file_organizer.tui.file_preview import FilePreviewView

        view = FilePreviewView(tmp_path, id="view")
        assert view._root_path == tmp_path
        assert view.selection.count == 0

    def test_selection_changed_message(self) -> None:
        from file_organizer.tui.file_preview import FilePreviewView

        msg = FilePreviewView.SelectionChanged(5)
        assert msg.count == 5

    def test_has_bindings(self) -> None:
        from file_organizer.tui.file_preview import FilePreviewView

        keys = {b.key for b in FilePreviewView.BINDINGS}
        assert "space" in keys
        assert "ctrl+a" in keys
        assert "ctrl+d" in keys


class TestTuiPreviewExports:
    """Test that the tui __init__ exports are correct."""

    def test_exports(self) -> None:
        from file_organizer.tui import (
            FilePreviewPanel,
            FilePreviewView,
            FileSelectionManager,
        )

        assert all(
            cls is not None
            for cls in (FilePreviewPanel, FilePreviewView, FileSelectionManager)
        )
