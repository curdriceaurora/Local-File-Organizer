"""Coverage tests for file_organizer.tui.file_preview module.

Targets uncovered branches in FilePreviewPanel static preview methods,
FilePreviewView actions and _notify_selection.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.tui.file_preview import (
    FilePreviewPanel,
    FilePreviewView,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# FilePreviewPanel - preview strategies (static methods)
# ---------------------------------------------------------------------------


class TestPreviewText:
    """Test FilePreviewPanel._preview_text."""

    def test_reads_text_file(self, tmp_path: Path) -> None:
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3")
        result = FilePreviewPanel._preview_text(f)
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result

    def test_truncates_long_files(self, tmp_path: Path) -> None:
        f = tmp_path / "long.txt"
        f.write_text("\n".join(f"line{i}" for i in range(200)))
        result = FilePreviewPanel._preview_text(f, max_lines=100)
        assert "lines shown" in result  # truncation notice

    def test_short_file_no_truncation(self, tmp_path: Path) -> None:
        f = tmp_path / "short.txt"
        f.write_text("just one line")
        result = FilePreviewPanel._preview_text(f, max_lines=100)
        # No truncation indicator for short files
        assert "lines shown" not in result

    def test_os_error(self) -> None:
        mock_path = MagicMock(spec=Path)
        mock_path.read_text.side_effect = OSError("denied")
        result = FilePreviewPanel._preview_text(mock_path)
        assert "Cannot read" in result


class TestPreviewImage:
    """Test FilePreviewPanel._preview_image."""

    def test_image_preview_no_pillow(self, tmp_path: Path) -> None:
        """Test image preview when PIL is not available."""
        f = tmp_path / "test.jpg"
        f.write_bytes(b"not a real image")
        with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
            result = FilePreviewPanel._preview_image(f)
        assert "Image" in result
        assert "Cannot read image metadata" in result

    def test_image_preview_with_mock_pillow(self, tmp_path: Path) -> None:
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 100)
        mock_img = MagicMock()
        mock_img.format = "PNG"
        mock_img.size = (800, 600)
        mock_img.mode = "RGB"
        mock_img.__enter__ = MagicMock(return_value=mock_img)
        mock_img.__exit__ = MagicMock(return_value=False)

        with patch("PIL.Image.open", return_value=mock_img):
            result = FilePreviewPanel._preview_image(f)
        assert "Image Preview" in result
        assert "PNG" in result
        assert "800" in result
        assert "600" in result

    def test_image_preview_exception(self) -> None:
        mock_path = MagicMock(spec=Path)
        # Make sure this doesn't import PIL, triggering the except
        with patch.dict("sys.modules", {"PIL": None, "PIL.Image": None}):
            result = FilePreviewPanel._preview_image(mock_path)
        assert "Image" in result


class TestPreviewPdf:
    """Test FilePreviewPanel._preview_pdf."""

    def test_pdf_preview_with_mock_fitz(self, tmp_path: Path) -> None:
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4 dummy")

        mock_doc = MagicMock()
        mock_doc.__len__ = MagicMock(return_value=5)
        mock_doc.__enter__ = MagicMock(return_value=mock_doc)
        mock_doc.__exit__ = MagicMock(return_value=False)

        mock_fitz = MagicMock()
        mock_fitz.open.return_value = mock_doc

        with patch.dict("sys.modules", {"fitz": mock_fitz}):
            result = FilePreviewPanel._preview_pdf(f)
        assert "PDF Preview" in result
        assert "5" in result

    def test_pdf_preview_exception(self) -> None:
        mock_path = MagicMock(spec=Path)
        with patch.dict("sys.modules", {"fitz": None}):
            result = FilePreviewPanel._preview_pdf(mock_path)
        assert "PDF" in result
        assert "Cannot read PDF" in result


class TestPreviewArchive:
    """Test FilePreviewPanel._preview_archive."""

    def test_archive_with_single_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.tar.gz"
        f.write_bytes(b"\x1f\x8b" + b"\0" * 50)
        with patch(
            "file_organizer.utils.file_readers.read_file",
            return_value="file1.txt",
        ):
            result = FilePreviewPanel._preview_archive(f)
        assert "Archive Contents" in result
        assert "file1.txt" in result

    def test_archive_empty_content(self, tmp_path: Path) -> None:
        f = tmp_path / "test.zip"
        f.write_bytes(b"not a zip")
        with patch("file_organizer.utils.file_readers.read_file", return_value=""):
            result = FilePreviewPanel._preview_archive(f)
        assert "Empty or unreadable" in result

    def test_archive_with_content(self, tmp_path: Path) -> None:
        f = tmp_path / "test.zip"
        f.write_bytes(b"PK" + b"\0" * 100)
        with patch(
            "file_organizer.utils.file_readers.read_file",
            return_value="file1.txt\nfile2.txt",
        ):
            result = FilePreviewPanel._preview_archive(f)
        assert "Archive Contents" in result

    def test_archive_exception(self) -> None:
        mock_path = MagicMock(spec=Path)
        with patch(
            "file_organizer.utils.file_readers.read_file",
            side_effect=ImportError("no reader"),
        ):
            result = FilePreviewPanel._preview_archive(mock_path)
        assert "Archive" in result
        assert "Cannot" in result


class TestPreviewDirectory:
    """Test FilePreviewPanel._preview_directory."""

    def test_empty_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        result = FilePreviewPanel._preview_directory(d)
        assert "empty/" in result
        assert "0 items" in result

    def test_directory_with_files(self, tmp_path: Path) -> None:
        d = tmp_path / "mydir"
        d.mkdir()
        (d / "a.txt").touch()
        (d / "b.py").touch()
        result = FilePreviewPanel._preview_directory(d)
        assert "mydir/" in result
        assert "a.txt" in result
        assert "b.py" in result

    def test_directory_with_subdirs(self, tmp_path: Path) -> None:
        d = tmp_path / "parent"
        d.mkdir()
        (d / "child").mkdir()
        (d / "file.txt").touch()
        result = FilePreviewPanel._preview_directory(d)
        assert "child" in result
        assert "file.txt" in result
        assert "parent/" in result

    def test_directory_os_error(self) -> None:
        mock_path = MagicMock(spec=Path)
        mock_path.iterdir.side_effect = OSError("denied")
        mock_path.name = "forbidden"
        result = FilePreviewPanel._preview_directory(mock_path)
        assert "Cannot list" in result


class TestPreviewGeneric:
    """Test FilePreviewPanel._preview_generic."""

    def test_generic_preview(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00" * 256)
        result = FilePreviewPanel._preview_generic(f)
        assert "data.bin" in result
        assert ".bin" in result
        assert "256" in result

    def test_generic_no_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "LICENSE"
        f.write_text("MIT License")
        result = FilePreviewPanel._preview_generic(f)
        assert "unknown" in result

    def test_generic_os_error(self) -> None:
        mock_path = MagicMock(spec=Path)
        mock_path.stat.side_effect = OSError("denied")
        result = FilePreviewPanel._preview_generic(mock_path)
        assert "Cannot stat" in result


# ---------------------------------------------------------------------------
# FilePreviewView actions
# ---------------------------------------------------------------------------


class TestFilePreviewViewActions:
    """Test FilePreviewView action methods."""

    def test_action_toggle_select_with_file(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.touch()
        view = FilePreviewView(path=tmp_path)
        view._current_path = f
        view.post_message = MagicMock()
        view._notify_selection = MagicMock()
        view.action_toggle_select()
        view._notify_selection.assert_called_once()
        assert view.selection.count == 1

    def test_action_toggle_select_no_path(self) -> None:
        view = FilePreviewView()
        view._current_path = None
        view._notify_selection = MagicMock()
        view.action_toggle_select()
        view._notify_selection.assert_not_called()

    def test_action_toggle_select_with_directory(self, tmp_path: Path) -> None:
        view = FilePreviewView(path=tmp_path)
        view._current_path = tmp_path  # directory, not a file
        view._notify_selection = MagicMock()
        view.action_toggle_select()
        view._notify_selection.assert_not_called()

    def test_action_deselect_all(self) -> None:
        view = FilePreviewView()
        view.selection._selected.add(Path("tmp/a.txt"))
        view.post_message = MagicMock()
        view._notify_selection = MagicMock()
        view.action_deselect_all()
        assert view.selection.count == 0
        view._notify_selection.assert_called_once()

    def test_selection_changed_message(self) -> None:
        msg = FilePreviewView.SelectionChanged(5)
        assert msg.count == 5

    def test_notify_selection_without_app(self) -> None:
        view = FilePreviewView()
        view.post_message = MagicMock()
        # Should not crash even without mounted app
        view._notify_selection()
        view.post_message.assert_called_once()

    def test_init_custom_path(self) -> None:
        view = FilePreviewView(path="tmp/test")
        assert view._root_path == Path("tmp/test")
        assert view._current_path is None
