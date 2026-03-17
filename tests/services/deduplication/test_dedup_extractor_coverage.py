"""Coverage tests for DocumentExtractor — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.deduplication.extractor import DocumentExtractor

pytestmark = pytest.mark.unit


@pytest.fixture()
def extractor():
    return DocumentExtractor()


# ---------------------------------------------------------------------------
# extract_text — format dispatch
# ---------------------------------------------------------------------------


class TestExtractText:
    def test_nonexistent_file_raises(self, extractor):
        with pytest.raises(OSError, match="File not found"):
            extractor.extract_text(Path("/no/such/file.pdf"))

    def test_unsupported_format_raises(self, extractor, tmp_path):
        f = tmp_path / "file.xyz"
        f.write_text("content")
        with pytest.raises(ValueError, match="Unsupported format"):
            extractor.extract_text(f)

    def test_txt_file(self, extractor, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world", encoding="utf-8")
        text = extractor.extract_text(f)
        assert text == "hello world"

    def test_md_file(self, extractor, tmp_path):
        f = tmp_path / "readme.md"
        f.write_text("# Title\n\nSome content", encoding="utf-8")
        text = extractor.extract_text(f)
        assert "Title" in text

    def test_extract_catches_internal_errors(self, extractor, tmp_path):
        f = tmp_path / "bad.txt"
        f.write_text("x")
        with patch.object(extractor, "_extract_text", side_effect=Exception("boom")):
            result = extractor.extract_text(f)
        assert result == ""


# ---------------------------------------------------------------------------
# extract_batch
# ---------------------------------------------------------------------------


class TestExtractBatch:
    def test_batch_normal(self, extractor, tmp_path):
        f1 = tmp_path / "a.txt"
        f1.write_text("alpha")
        f2 = tmp_path / "b.txt"
        f2.write_text("bravo")
        results = extractor.extract_batch([f1, f2])
        assert results[f1] == "alpha"
        assert results[f2] == "bravo"

    def test_batch_with_error(self, extractor, tmp_path):
        f1 = tmp_path / "good.txt"
        f1.write_text("good")
        f2 = tmp_path / "bad.xyz"
        f2.write_text("bad")
        results = extractor.extract_batch([f1, f2])
        assert results[f1] == "good"
        assert results[f2] == ""  # unsupported format caught


# ---------------------------------------------------------------------------
# supports_format / get_supported_formats
# ---------------------------------------------------------------------------


class TestFormatSupport:
    def test_supported(self, extractor, tmp_path):
        assert extractor.supports_format(tmp_path / "test.pdf") is True
        assert extractor.supports_format(tmp_path / "test.docx") is True
        assert extractor.supports_format(tmp_path / "test.txt") is True

    def test_unsupported(self, extractor, tmp_path):
        assert extractor.supports_format(tmp_path / "test.xyz") is False

    def test_get_supported_formats(self, extractor):
        formats = extractor.get_supported_formats()
        assert ".txt" in formats
        assert isinstance(formats, list)
        assert formats == sorted(formats)


# ---------------------------------------------------------------------------
# _extract_text — encoding fallback
# ---------------------------------------------------------------------------


class TestExtractTextEncoding:
    def test_utf8(self, extractor, tmp_path):
        f = tmp_path / "utf8.txt"
        f.write_text("unicode: \u00e9\u00e8\u00ea", encoding="utf-8")
        text = extractor._extract_text(f)
        assert "\u00e9" in text

    def test_latin1_fallback(self, extractor, tmp_path):
        f = tmp_path / "latin1.txt"
        f.write_bytes(b"caf\xe9 \xf1")
        text = extractor._extract_text(f)
        assert len(text) > 0

    def test_binary_fallback(self, extractor, tmp_path):
        f = tmp_path / "binary.txt"
        # Create bytes that fail all standard encodings
        f.write_bytes(bytes(range(256)))
        text = extractor._extract_text(f)
        assert isinstance(text, str)


# ---------------------------------------------------------------------------
# _extract_pdf — import error + runtime error
# ---------------------------------------------------------------------------


class TestExtractPdf:
    def test_pdf_import_error(self, extractor, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"%PDF-1.4")
        with patch.dict("sys.modules", {"pypdf": None}):
            with patch("builtins.__import__", side_effect=ImportError("no pypdf")):
                result = extractor._extract_pdf(f)
        assert result == ""

    def test_pdf_runtime_error(self, extractor, tmp_path):
        f = tmp_path / "test.pdf"
        f.write_bytes(b"not a real pdf")
        result = extractor._extract_pdf(f)
        assert result == ""


# ---------------------------------------------------------------------------
# _extract_docx — import error
# ---------------------------------------------------------------------------


class TestExtractDocx:
    def test_docx_import_error(self, extractor, tmp_path):
        f = tmp_path / "test.docx"
        f.write_bytes(b"PK\x03\x04")
        with patch("builtins.__import__", side_effect=ImportError("no docx")):
            result = extractor._extract_docx(f)
        assert result == ""

    def test_docx_runtime_error(self, extractor, tmp_path):
        f = tmp_path / "test.docx"
        f.write_bytes(b"not a docx")
        result = extractor._extract_docx(f)
        assert result == ""


# ---------------------------------------------------------------------------
# _extract_rtf — with and without striprtf
# ---------------------------------------------------------------------------


class TestExtractRtf:
    def test_rtf_basic_extraction_fallback(self, extractor, tmp_path):
        f = tmp_path / "test.rtf"
        f.write_text(r"{\rtf1 Hello \b World}", encoding="utf-8")
        # Without striprtf, basic extraction may return empty on error
        result = extractor._extract_rtf(f)
        assert isinstance(result, str)

    def test_rtf_error(self, extractor, tmp_path):
        f = tmp_path / "test.rtf"
        f.write_text("content")
        with patch("builtins.open", side_effect=Exception("fail")):
            result = extractor._extract_rtf(f)
        assert result == ""


# ---------------------------------------------------------------------------
# _extract_odt
# ---------------------------------------------------------------------------


class TestExtractOdt:
    def test_odt_error(self, extractor, tmp_path):
        f = tmp_path / "test.odt"
        f.write_bytes(b"not a zip")
        result = extractor._extract_odt(f)
        assert result == ""
