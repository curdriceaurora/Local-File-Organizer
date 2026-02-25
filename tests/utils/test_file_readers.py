"""Tests for file_readers.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.utils import file_readers
from file_organizer.utils.file_readers import (
    FileReadError,
    FileTooLargeError,
    _check_file_size,
    read_docx_file,
    read_ebook_file,
    read_file,
    read_pdf_file,
    read_presentation_file,
    read_spreadsheet_file,
    read_text_file,
)

pytestmark = [pytest.mark.unit]


class TestFileReaders:
    """Tests for individual file readers in utils/file_readers.py."""

    def test_check_file_size(self, tmp_path: Path) -> None:
        """Test file size limit checking."""
        test_file = tmp_path / "large_file.txt"
        test_file.write_bytes(b"x" * 1024)  # 1 KB

        # Should pass
        _check_file_size(test_file, max_bytes=2048)

        # Should fail
        with pytest.raises(FileTooLargeError, match="File too large to process"):
            _check_file_size(test_file, max_bytes=512)

    def test_check_file_size_missing_file(self, tmp_path: Path) -> None:
        """Test file size check for missing file."""
        missing = tmp_path / "missing.txt"
        # Should return silently and let the caller handle the missing file
        _check_file_size(missing)

    def test_read_text_file(self, tmp_path: Path) -> None:
        """Test reading a plain text file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World\nLine 2")

        content = read_text_file(test_file)
        assert "Hello World" in content
        assert "Line 2" in content

    def test_read_text_file_max_chars(self, tmp_path: Path) -> None:
        """Test max_chars limit in text reader."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("1234567890")

        content = read_text_file(test_file, max_chars=5)
        assert content == "12345"

    def test_read_text_file_error(self, tmp_path: Path) -> None:
        """Test error handling in text reader."""
        missing = tmp_path / "missing.txt"
        with pytest.raises(FileReadError):
            read_text_file(missing)

    @patch("file_organizer.utils.file_readers.DOCX_AVAILABLE", True)
    @patch("file_organizer.utils.file_readers.docx.Document")
    def test_read_docx_file_success(self, mock_doc_cls: MagicMock, tmp_path: Path) -> None:
        """Test reading DOCX file."""
        # Setup mock doc
        mock_doc = MagicMock()
        mock_para1 = MagicMock()
        mock_para1.text = "Paragraph 1"
        mock_para2 = MagicMock()
        mock_para2.text = "Paragraph 2"
        mock_doc.paragraphs = [mock_para1, mock_para2]
        mock_doc_cls.return_value = mock_doc

        test_file = tmp_path / "test.docx"
        test_file.touch()

        content = read_docx_file(test_file)
        assert "Paragraph 1\nParagraph 2" in content

    @patch("file_organizer.utils.file_readers.DOCX_AVAILABLE", False)
    def test_read_docx_not_installed(self) -> None:
        """Test DOCX reading when library is missing."""
        with pytest.raises(ImportError, match="python-docx is not installed"):
            read_docx_file("test.docx")

    @patch("file_organizer.utils.file_readers.DOCX_AVAILABLE", True)
    @patch("file_organizer.utils.file_readers.docx.Document")
    def test_read_docx_error(self, mock_doc_cls: MagicMock, tmp_path: Path) -> None:
        """Test reading DOCX file with error."""
        mock_doc_cls.side_effect = Exception("Doc error")
        test_file = tmp_path / "test.docx"
        test_file.touch()

        with pytest.raises(FileReadError, match="Failed to read DOCX"):
            read_docx_file(test_file)

    @patch("file_organizer.utils.file_readers.PYMUPDF_AVAILABLE", True)
    @patch("file_organizer.utils.file_readers.fitz.open")
    def test_read_pdf_file_success(self, mock_fitz_open: MagicMock, tmp_path: Path) -> None:
        """Test reading PDF file."""
        mock_doc = MagicMock()
        mock_doc.__len__.return_value = 2
        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = "Page 1 content"
        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = "Page 2 content"
        mock_doc.load_page.side_effect = [mock_page1, mock_page2]
        mock_fitz_open.return_value = mock_doc

        test_file = tmp_path / "test.pdf"
        test_file.touch()

        content = read_pdf_file(test_file)
        assert "Page 1 content" in content
        assert "Page 2 content" in content
        mock_doc.close.assert_called_once()

    @patch("file_organizer.utils.file_readers.PYMUPDF_AVAILABLE", False)
    def test_read_pdf_not_installed(self) -> None:
        """Test PDF reading when missing library."""
        with pytest.raises(ImportError, match="PyMuPDF is not installed"):
            read_pdf_file("test.pdf")

    @patch("file_organizer.utils.file_readers.PYMUPDF_AVAILABLE", True)
    @patch("file_organizer.utils.file_readers.fitz.open")
    def test_read_pdf_error(self, mock_fitz_open: MagicMock, tmp_path: Path) -> None:
        """Test PDF reading error."""
        mock_fitz_open.side_effect = Exception("PDF render error")
        test_file = tmp_path / "test.pdf"
        test_file.touch()

        with pytest.raises(FileReadError):
            read_pdf_file(test_file)

    @patch("file_organizer.utils.file_readers.PANDAS_AVAILABLE", True)
    @patch("file_organizer.utils.file_readers.pd.read_csv")
    def test_read_spreadsheet_csv(self, mock_read_csv: MagicMock, tmp_path: Path) -> None:
        """Test reading CSV spreadsheet."""
        mock_df = MagicMock()
        mock_df.to_string.return_value = "Col1,Col2\nA,B"
        mock_read_csv.return_value = mock_df

        test_file = tmp_path / "test.csv"
        test_file.touch()

        content = read_spreadsheet_file(test_file)
        assert "Col1,Col2" in content
        mock_read_csv.assert_called_once()

    @patch("file_organizer.utils.file_readers.PANDAS_AVAILABLE", True)
    @patch("file_organizer.utils.file_readers.pd.read_excel")
    def test_read_spreadsheet_xlsx(self, mock_read_excel: MagicMock, tmp_path: Path) -> None:
        """Test reading XLSX spreadsheet."""
        mock_df = MagicMock()
        mock_df.to_string.return_value = "Sheet Data"
        mock_read_excel.return_value = mock_df

        test_file = tmp_path / "test.xlsx"
        test_file.touch()

        content = read_spreadsheet_file(test_file)
        assert "Sheet" in content

    @patch("file_organizer.utils.file_readers.PANDAS_AVAILABLE", False)
    def test_read_spreadsheet_not_installed(self) -> None:
        with pytest.raises(ImportError, match="pandas is not installed"):
            read_spreadsheet_file("test.csv")

    @patch("file_organizer.utils.file_readers.PANDAS_AVAILABLE", True)
    def test_read_spreadsheet_bad_format(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.unknown"
        test_file.touch()
        with pytest.raises(FileReadError, match="Unsupported spreadsheet"):
            read_spreadsheet_file(test_file)

    @patch("file_organizer.utils.file_readers.PPTX_AVAILABLE", True)
    @patch("file_organizer.utils.file_readers.Presentation")
    def test_read_presentation_file(self, mock_prs_cls: MagicMock, tmp_path: Path) -> None:
        """Test reading PPTX."""
        mock_prs = MagicMock()
        mock_slide = MagicMock()
        mock_shape = MagicMock()
        mock_shape.text = "Presentation text"
        mock_slide.shapes = [mock_shape]
        mock_prs.slides = [mock_slide]
        mock_prs_cls.return_value = mock_prs

        test_file = tmp_path / "test.pptx"
        test_file.touch()

        content = read_presentation_file(test_file)
        assert "Slide 1" in content
        assert "Presentation text" in content

    @patch("file_organizer.utils.file_readers.PPTX_AVAILABLE", False)
    def test_read_presentation_not_installed(self) -> None:
        with pytest.raises(ImportError, match="python-pptx is not installed"):
            read_presentation_file("test.pptx")

    @patch("file_organizer.utils.file_readers.EBOOKLIB_AVAILABLE", True)
    @patch("file_organizer.utils.file_readers.epub.read_epub")
    def test_read_ebook_file(self, mock_read_epub: MagicMock, tmp_path: Path) -> None:
        """Test reading EPUB."""
        mock_book = MagicMock()
        mock_item = MagicMock()
        mock_item.get_type.return_value = file_readers.ebooklib.ITEM_DOCUMENT
        mock_item.get_content.return_value = b"<html><body>Ebook Content</body></html>"
        mock_book.get_items.return_value = [mock_item]
        mock_read_epub.return_value = mock_book

        test_file = tmp_path / "test.epub"
        test_file.touch()

        content = read_ebook_file(test_file)
        assert "Ebook Content" in content

    @patch("file_organizer.utils.file_readers.EBOOKLIB_AVAILABLE", False)
    def test_read_ebook_not_installed(self) -> None:
        with pytest.raises(ImportError, match="ebooklib is not installed"):
            read_ebook_file("test.epub")

    @patch("file_organizer.utils.file_readers.EBOOKLIB_AVAILABLE", True)
    def test_read_ebook_unsupported_format(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.mobi"
        test_file.touch()
        with pytest.raises(FileReadError, match="Unsupported ebook format"):
            read_ebook_file(test_file)


class TestReadFileGeneric:
    """Test the read_file routing function."""

    @patch("file_organizer.utils.file_readers.read_text_file")
    def test_read_file_text(self, mock_read_text: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "doc.txt"
        test_file.touch()
        mock_read_text.return_value = "text"

        read_file(test_file)
        mock_read_text.assert_called_once_with(test_file)

    @patch("file_organizer.utils.file_readers.read_docx_file")
    def test_read_file_docx(self, mock_read_docx: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "doc.docx"
        test_file.touch()
        read_file(test_file)
        mock_read_docx.assert_called_once()

    @patch("file_organizer.utils.file_readers.read_pdf_file")
    def test_read_file_pdf(self, mock_read_pdf: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "doc.pdf"
        test_file.touch()
        read_file(test_file)
        mock_read_pdf.assert_called_once()

    @patch("file_organizer.utils.file_readers.read_spreadsheet_file")
    def test_read_file_spreadsheet(self, mock_read_csv: MagicMock, tmp_path: Path) -> None:
        test_file = tmp_path / "data.csv"
        test_file.touch()
        read_file(test_file)
        mock_read_csv.assert_called_once()

    def test_read_file_unsupported(self, tmp_path: Path) -> None:
        test_file = tmp_path / "unknown.xyz123"
        test_file.touch()
        assert read_file(test_file) is None
