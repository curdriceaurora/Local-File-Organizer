"""Tests for file_readers.py."""

from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.utils import file_readers
from file_organizer.utils.file_readers import (
    FileReadError,
    FileTooLargeError,
    _check_file_size,
    read_cad_file,
    read_docx_file,
    read_ebook_file,
    read_file,
    read_iges_file,
    read_pdf_file,
    read_presentation_file,
    read_spreadsheet_file,
    read_step_file,
    read_tar_file,
    read_text_file,
    read_zip_file,
)

pytestmark = [pytest.mark.unit]


@pytest.mark.unit
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


@pytest.mark.unit
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


# ────────────────────────────────────────────────────────────────────────────
# New tests below: archive, scientific (optional-dep), CAD, and read_file dispatch
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestArchiveReaders:
    """Tests for ZIP and TAR archive readers."""

    def test_read_zip_file(self, tmp_path):
        """Create a real zip with temp files and verify metadata extraction."""
        # Create files to zip
        (tmp_path / "hello.txt").write_text("Hello, world!")
        (tmp_path / "data.csv").write_text("a,b,c\n1,2,3")

        zip_path = tmp_path / "archive.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(tmp_path / "hello.txt", "hello.txt")
            zf.write(tmp_path / "data.csv", "data.csv")

        content = read_zip_file(zip_path)
        assert "ZIP Archive: archive.zip" in content
        assert "Total files: 2" in content
        assert "hello.txt" in content
        assert "data.csv" in content
        assert "Encrypted: No" in content

    def test_read_zip_empty_archive(self, tmp_path):
        """Test reading an empty zip archive."""
        zip_path = tmp_path / "empty.zip"
        with zipfile.ZipFile(zip_path, "w"):
            pass  # empty archive

        content = read_zip_file(zip_path)
        assert "Total files: 0" in content
        assert "ZIP Archive: empty.zip" in content

    def test_read_tar_file(self, tmp_path):
        """Create a real tar.gz with temp files and verify metadata."""
        (tmp_path / "readme.md").write_text("# README")
        (tmp_path / "notes.txt").write_text("some notes")

        tar_path = tmp_path / "archive.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(tmp_path / "readme.md", arcname="readme.md")
            tf.add(tmp_path / "notes.txt", arcname="notes.txt")

        content = read_tar_file(tar_path)
        assert "TAR Archive: archive.tar.gz" in content
        assert "Compression: GZ" in content
        assert "Total files: 2" in content
        assert "readme.md" in content
        assert "notes.txt" in content

    def test_read_tar_bz2(self, tmp_path):
        """Test reading a tar.bz2 archive."""
        (tmp_path / "file.txt").write_text("bz2 content")

        tar_path = tmp_path / "archive.tar.bz2"
        with tarfile.open(tar_path, "w:bz2") as tf:
            tf.add(tmp_path / "file.txt", arcname="file.txt")

        content = read_tar_file(tar_path)
        assert "TAR Archive: archive.tar.bz2" in content
        assert "Total files: 1" in content
        assert "file.txt" in content

    def test_read_tar_plain(self, tmp_path):
        """Test reading a plain .tar archive (no compression)."""
        (tmp_path / "plain.txt").write_text("plain tar content")

        tar_path = tmp_path / "archive.tar"
        with tarfile.open(tar_path, "w") as tf:
            tf.add(tmp_path / "plain.txt", arcname="plain.txt")

        content = read_tar_file(tar_path)
        assert "TAR Archive: archive.tar" in content
        assert "Compression: None" in content
        assert "Total files: 1" in content
        assert "plain.txt" in content

    def test_read_zip_error(self, tmp_path):
        """Corrupt zip raises FileReadError."""
        corrupt_zip = tmp_path / "corrupt.zip"
        corrupt_zip.write_bytes(b"this is not a zip file at all")

        with pytest.raises(FileReadError, match="Failed to read ZIP file"):
            read_zip_file(corrupt_zip)

    def test_read_tar_error(self, tmp_path):
        """Corrupt tar raises FileReadError."""
        corrupt_tar = tmp_path / "corrupt.tar.gz"
        corrupt_tar.write_bytes(b"this is not a tar file at all")

        with pytest.raises(FileReadError, match="Failed to read TAR file"):
            read_tar_file(corrupt_tar)


@pytest.mark.unit
class TestScientificReaders:
    """Tests for optional-dependency scientific format readers (unavailable paths)."""

    @patch("file_organizer.utils.file_readers.PY7ZR_AVAILABLE", False)
    def test_read_7z_not_installed(self):
        """py7zr not installed raises ImportError."""
        from file_organizer.utils.file_readers import read_7z_file

        with pytest.raises(ImportError, match="py7zr is not installed"):
            read_7z_file("test.7z")

    @patch("file_organizer.utils.file_readers.RARFILE_AVAILABLE", False)
    def test_read_rar_not_installed(self):
        """rarfile not installed raises ImportError."""
        from file_organizer.utils.file_readers import read_rar_file

        with pytest.raises(ImportError, match="rarfile is not installed"):
            read_rar_file("test.rar")

    @patch("file_organizer.utils.file_readers.H5PY_AVAILABLE", False)
    def test_read_hdf5_not_installed(self):
        """h5py not installed raises ImportError."""
        from file_organizer.utils.file_readers import read_hdf5_file

        with pytest.raises(ImportError, match="h5py is not installed"):
            read_hdf5_file("test.hdf5")

    @patch("file_organizer.utils.file_readers.NETCDF4_AVAILABLE", False)
    def test_read_netcdf_not_installed(self):
        """netCDF4 not installed raises ImportError."""
        from file_organizer.utils.file_readers import read_netcdf_file

        with pytest.raises(ImportError, match="netCDF4 is not installed"):
            read_netcdf_file("test.nc")

    @patch("file_organizer.utils.file_readers.SCIPY_AVAILABLE", False)
    def test_read_mat_not_installed(self):
        """scipy not installed raises ImportError."""
        from file_organizer.utils.file_readers import read_mat_file

        with pytest.raises(ImportError, match="scipy is not installed"):
            read_mat_file("test.mat")

    @patch("file_organizer.utils.file_readers.EZDXF_AVAILABLE", False)
    def test_read_dxf_not_installed(self):
        """ezdxf not installed raises ImportError for DXF."""
        from file_organizer.utils.file_readers import read_dxf_file

        with pytest.raises(ImportError, match="ezdxf is not installed"):
            read_dxf_file("test.dxf")

    @patch("file_organizer.utils.file_readers.EZDXF_AVAILABLE", False)
    def test_read_dwg_not_installed(self):
        """ezdxf not installed raises ImportError for DWG."""
        from file_organizer.utils.file_readers import read_dwg_file

        with pytest.raises(ImportError, match="ezdxf is not installed"):
            read_dwg_file("test.dwg")


@pytest.mark.unit
class TestCADReaders:
    """Tests for text-based CAD readers (STEP, IGES) and CAD dispatch."""

    def test_read_step_file(self, tmp_path):
        """Create a minimal STEP file and verify header extraction."""
        step_content = (
            "ISO-10303-21;\n"
            "HEADER;\n"
            "FILE_DESCRIPTION(('Test'),'2;1');\n"
            "FILE_NAME('test.step','2024-01-01',('Author'),('Org'),'','','');\n"
            "FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));\n"
            "ENDSEC;\n"
            "DATA;\n"
            "#1=SHAPE_REPRESENTATION('test',(#2),#3);\n"
            "ENDSEC;\n"
            "END-ISO-10303-21;\n"
        )
        step_path = tmp_path / "model.step"
        step_path.write_text(step_content)

        content = read_step_file(step_path)
        assert "STEP File Information" in content
        assert "model.step" in content
        assert "FILE_DESCRIPTION" in content
        assert "FILE_NAME" in content
        assert "FILE_SCHEMA" in content
        assert "AUTOMOTIVE_DESIGN" in content

    def test_read_step_file_no_header(self, tmp_path):
        """STEP file without proper header returns basic info only."""
        step_path = tmp_path / "noheader.step"
        step_path.write_text("ISO-10303-21;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")

        content = read_step_file(step_path)
        assert "STEP File Information" in content
        assert "noheader.step" in content
        # Should not crash, but no header fields extracted
        assert "FILE_DESCRIPTION" not in content

    def test_read_iges_file(self, tmp_path):
        """Create a minimal IGES file with proper column structure."""
        # IGES format: 80-char lines with section type at column 73
        start_line = "{:<72}S{:>7d}\n".format("Test IGES file", 1)
        global_line = "{:<72}G{:>7d}\n".format(
            "1H,,1H;,4Htest,8Htest.igs,8Htest.igs", 1
        )
        term_line = "{:<72}T{:>7d}\n".format(
            "S      1G      1D      0P      0", 1
        )

        iges_path = tmp_path / "model.igs"
        iges_path.write_text(start_line + global_line + term_line)

        content = read_iges_file(iges_path)
        assert "IGES File Information" in content
        assert "model.igs" in content
        assert "Start Section" in content
        assert "Test IGES file" in content

    def test_read_iges_file_empty(self, tmp_path):
        """IGES file with no valid sections returns basic info."""
        iges_path = tmp_path / "empty.igs"
        iges_path.write_text("Short line\nAnother short line\n")

        content = read_iges_file(iges_path)
        assert "IGES File Information" in content
        assert "empty.igs" in content
        # No sections parsed
        assert "Start Section" not in content

    def test_read_cad_file_unsupported(self, tmp_path):
        """Unsupported CAD extension raises ValueError."""
        cad_path = tmp_path / "model.obj"
        cad_path.touch()

        with pytest.raises(ValueError, match="Unsupported CAD file format"):
            read_cad_file(cad_path)


@pytest.mark.unit
class TestReadFileExpanded:
    """Expanded tests for the read_file dispatch function."""

    def test_read_file_zip(self, tmp_path):
        """Verify read_file routes .zip to read_zip_file."""
        (tmp_path / "f.txt").write_text("data")
        zip_path = tmp_path / "test.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.write(tmp_path / "f.txt", "f.txt")

        content = read_file(zip_path)
        assert content is not None
        assert "ZIP Archive" in content
        assert "f.txt" in content

    def test_read_file_tar_gz(self, tmp_path):
        """Verify compound extension .tar.gz routes correctly."""
        (tmp_path / "data.txt").write_text("tar content")
        tar_path = tmp_path / "test.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            tf.add(tmp_path / "data.txt", arcname="data.txt")

        content = read_file(tar_path)
        assert content is not None
        assert "TAR Archive" in content
        assert "data.txt" in content

    def test_read_file_step(self, tmp_path):
        """Verify .step routes to read_cad_file -> read_step_file."""
        step_content = (
            "ISO-10303-21;\n"
            "HEADER;\n"
            "FILE_DESCRIPTION(('Test'),'2;1');\n"
            "ENDSEC;\n"
            "DATA;\n"
            "ENDSEC;\n"
            "END-ISO-10303-21;\n"
        )
        step_path = tmp_path / "model.step"
        step_path.write_text(step_content)

        content = read_file(step_path)
        assert content is not None
        assert "STEP File Information" in content

    @patch("file_organizer.utils.file_readers.EZDXF_AVAILABLE", False)
    def test_read_file_dxf(self, tmp_path):
        """Verify .dxf routes to read_cad_file -> read_dxf_file (raises when unavailable)."""
        dxf_path = tmp_path / "drawing.dxf"
        dxf_path.touch()

        with pytest.raises(ImportError, match="ezdxf is not installed"):
            read_file(dxf_path)
