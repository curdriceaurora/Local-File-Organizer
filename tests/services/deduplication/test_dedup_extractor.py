"""Tests for DocumentExtractor class.

Tests text extraction from PDF, DOCX, TXT, MD, RTF, and ODT document formats.
All external dependencies (pypdf, docx, striprtf) are mocked.
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def extractor():
    """Create a DocumentExtractor instance with mocked dependency checks."""
    with patch(
        "file_organizer.services.deduplication.extractor.DocumentExtractor._check_dependencies"
    ):
        from file_organizer.services.deduplication.extractor import DocumentExtractor

        return DocumentExtractor()


@pytest.fixture
def tmp_txt(tmp_path):
    """Create a temporary .txt file."""
    p = tmp_path / "sample.txt"
    p.write_text("Hello World\nLine two", encoding="utf-8")
    return p


@pytest.fixture
def tmp_md(tmp_path):
    """Create a temporary .md file."""
    p = tmp_path / "readme.md"
    p.write_text("# Heading\nSome markdown content.", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDocumentExtractorInit:
    """Tests for DocumentExtractor initialization."""

    def test_supported_extensions(self, extractor):
        exts = extractor.supported_extensions
        assert ".pdf" in exts
        assert ".docx" in exts
        assert ".txt" in exts
        assert ".rtf" in exts
        assert ".odt" in exts
        assert ".md" in exts

    def test_check_dependencies_missing_modules(self):
        """When optional deps are missing, a warning is logged but no error raised."""
        import builtins

        original_import = builtins.__import__

        def selective_import(name, *args, **kwargs):
            if name in ("pypdf", "docx"):
                raise ImportError(f"no {name}")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=selective_import):
            from file_organizer.services.deduplication.extractor import DocumentExtractor

            # Should not raise
            ext = DocumentExtractor()
            assert ext is not None

    def test_check_dependencies_present(self):
        """When deps are present, no warning is logged."""
        with patch(
            "file_organizer.services.deduplication.extractor.DocumentExtractor._check_dependencies"
        ):
            from file_organizer.services.deduplication.extractor import DocumentExtractor

            ext = DocumentExtractor()
            assert ext is not None


# ---------------------------------------------------------------------------
# supports_format / get_supported_formats
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFormatSupport:
    """Tests for format checking."""

    def test_supports_pdf(self, extractor):
        assert extractor.supports_format(Path("doc.pdf"))

    def test_supports_docx(self, extractor):
        assert extractor.supports_format(Path("doc.docx"))

    def test_supports_txt(self, extractor):
        assert extractor.supports_format(Path("notes.txt"))

    def test_supports_md(self, extractor):
        assert extractor.supports_format(Path("readme.md"))

    def test_supports_rtf(self, extractor):
        assert extractor.supports_format(Path("doc.rtf"))

    def test_supports_odt(self, extractor):
        assert extractor.supports_format(Path("doc.odt"))

    def test_unsupported_format(self, extractor):
        assert not extractor.supports_format(Path("image.jpg"))

    def test_case_insensitive(self, extractor):
        assert extractor.supports_format(Path("DOC.PDF"))

    def test_get_supported_formats_returns_sorted(self, extractor):
        formats = extractor.get_supported_formats()
        assert formats == sorted(formats)
        assert ".pdf" in formats


# ---------------------------------------------------------------------------
# extract_text - plain text / markdown
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractText:
    """Tests for _extract_text (txt, md)."""

    def test_extract_txt(self, extractor, tmp_txt):
        result = extractor.extract_text(tmp_txt)
        assert "Hello World" in result
        assert "Line two" in result

    def test_extract_md(self, extractor, tmp_md):
        result = extractor.extract_text(tmp_md)
        assert "# Heading" in result
        assert "markdown content" in result

    def test_file_not_found(self, extractor):
        with pytest.raises(OSError, match="File not found"):
            extractor.extract_text(Path("/nonexistent/file.txt"))

    def test_unsupported_format_raises(self, extractor, tmp_path):
        p = tmp_path / "photo.jpg"
        p.write_bytes(b"\xff\xd8\xff")
        with pytest.raises(ValueError, match="Unsupported format"):
            extractor.extract_text(p)

    def test_encoding_fallback(self, extractor, tmp_path):
        """Test fallback to latin-1 when UTF-8 fails."""
        p = tmp_path / "latin.txt"
        p.write_bytes("caf\xe9".encode("latin-1"))
        result = extractor.extract_text(p)
        assert "caf" in result


# ---------------------------------------------------------------------------
# extract_text - PDF
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractPdf:
    """Tests for _extract_pdf."""

    def test_extract_pdf_success(self, extractor, tmp_path):
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"fake pdf")

        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page one text"
        mock_reader = MagicMock()
        mock_reader.pages = [mock_page]

        with patch.dict("sys.modules", {"pypdf": MagicMock()}):
            with patch("builtins.open", mock_open(read_data=b"fake")):
                import sys

                sys.modules["pypdf"].PdfReader.return_value = mock_reader
                result = extractor._extract_pdf(p)

        assert "Page one text" in result

    def test_extract_pdf_import_error(self, extractor, tmp_path):
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"fake pdf")

        with patch("builtins.__import__", side_effect=ImportError("no pypdf")):
            result = extractor._extract_pdf(p)

        assert result == ""

    def test_extract_pdf_generic_error(self, extractor, tmp_path):
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"fake pdf")

        with patch("builtins.open", side_effect=Exception("corrupt")):
            result = extractor._extract_pdf(p)

        assert result == ""


# ---------------------------------------------------------------------------
# extract_text - DOCX
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractDocx:
    """Tests for _extract_docx."""

    def test_extract_docx_success(self, extractor, tmp_path):
        p = tmp_path / "doc.docx"
        p.write_bytes(b"fake docx")

        mock_para = MagicMock()
        mock_para.text = "Paragraph text"

        mock_cell = MagicMock()
        mock_cell.text = "Table cell"

        mock_row = MagicMock()
        mock_row.cells = [mock_cell]

        mock_table = MagicMock()
        mock_table.rows = [mock_row]

        mock_doc = MagicMock()
        mock_doc.paragraphs = [mock_para]
        mock_doc.tables = [mock_table]

        mock_docx_module = MagicMock()
        mock_docx_module.Document.return_value = mock_doc

        with patch.dict("sys.modules", {"docx": mock_docx_module}):
            result = extractor._extract_docx(p)

        assert "Paragraph text" in result
        assert "Table cell" in result

    def test_extract_docx_import_error(self, extractor, tmp_path):
        p = tmp_path / "doc.docx"
        p.write_bytes(b"fake docx")

        with patch("builtins.__import__", side_effect=ImportError("no docx")):
            result = extractor._extract_docx(p)

        assert result == ""


# ---------------------------------------------------------------------------
# extract_text - RTF
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractRtf:
    """Tests for _extract_rtf."""

    def test_extract_rtf_with_striprtf(self, extractor, tmp_path):
        p = tmp_path / "doc.rtf"
        p.write_text("{\\rtf1 Hello RTF}", encoding="utf-8")

        mock_striprtf_mod = MagicMock()
        mock_striprtf_mod.striprtf.rtf_to_text.return_value = "Hello RTF"

        with patch.dict(
            "sys.modules",
            {"striprtf": mock_striprtf_mod, "striprtf.striprtf": mock_striprtf_mod.striprtf},
        ):
            result = extractor._extract_rtf(p)

        assert "Hello RTF" in result

    def test_extract_rtf_fallback_basic(self, extractor, tmp_path):
        p = tmp_path / "doc.rtf"
        p.write_text("{\\rtf1\\ansi Hello RTF}", encoding="utf-8")
        # Without striprtf, basic stripping removes control words and braces
        result = extractor._extract_rtf(p)
        assert "Hello RTF" in result

    def test_extract_rtf_error(self, extractor, tmp_path):
        p = tmp_path / "doc.rtf"
        p.write_text("bad content", encoding="utf-8")

        with patch("builtins.open", side_effect=Exception("fail")):
            result = extractor._extract_rtf(p)

        assert result == ""


# ---------------------------------------------------------------------------
# extract_text - ODT
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractOdt:
    """Tests for _extract_odt."""

    def test_extract_odt_success(self, extractor, tmp_path):
        p = tmp_path / "doc.odt"

        # Create a minimal ODT (zip containing content.xml)
        content_xml = (
            '<?xml version="1.0"?>'
            "<office:document-content "
            'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
            'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0">'
            "<office:body><office:text>"
            "<text:p>First paragraph</text:p>"
            "<text:p>Second paragraph</text:p>"
            "</office:text></office:body>"
            "</office:document-content>"
        )
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("content.xml", content_xml)

        result = extractor._extract_odt(p)
        assert "First paragraph" in result
        assert "Second paragraph" in result

    def test_extract_odt_error(self, extractor, tmp_path):
        p = tmp_path / "broken.odt"
        p.write_bytes(b"not a zip")

        result = extractor._extract_odt(p)
        assert result == ""


# ---------------------------------------------------------------------------
# extract_batch
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractBatch:
    """Tests for batch extraction."""

    def test_extract_batch_multiple_files(self, extractor, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("Alpha", encoding="utf-8")
        f2 = tmp_path / "b.txt"
        f2.write_text("Beta", encoding="utf-8")

        results = extractor.extract_batch([f1, f2])
        assert len(results) == 2
        assert "Alpha" in results[f1]
        assert "Beta" in results[f2]

    def test_extract_batch_with_errors(self, extractor, tmp_path):
        good = tmp_path / "good.txt"
        good.write_text("Good text", encoding="utf-8")
        bad = Path("/nonexistent/bad.txt")

        results = extractor.extract_batch([good, bad])
        assert len(results) == 2
        assert "Good text" in results[good]
        assert results[bad] == ""

    def test_extract_batch_empty_list(self, extractor):
        results = extractor.extract_batch([])
        assert results == {}


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases."""

    def test_extract_empty_text_file(self, extractor, tmp_path):
        p = tmp_path / "empty.txt"
        p.write_text("", encoding="utf-8")
        result = extractor.extract_text(p)
        assert result == ""

    def test_extract_binary_fallback(self, extractor, tmp_path):
        """When all encodings fail, binary read with errors='ignore' is used."""
        p = tmp_path / "binary.txt"
        # Write bytes that fail most encodings
        p.write_bytes(b"\x80\x81\x82\x83 some text")
        result = extractor.extract_text(p)
        assert "some text" in result

    def test_extract_text_catches_errors(self, extractor, tmp_path):
        """_extract_text catches exceptions and returns empty string."""
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"fake")

        with patch(
            "file_organizer.services.deduplication.extractor.DocumentExtractor._extract_pdf",
            side_effect=Exception("boom"),
        ):
            result = extractor.extract_text(p)
            assert result == ""
