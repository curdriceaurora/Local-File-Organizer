"""Coverage tests for EnhancedEPUBReader — targets uncovered branches."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# EPUBMetadata / EPUBChapter dataclasses
# ---------------------------------------------------------------------------


class TestEPUBMetadata:
    def test_post_init_defaults(self):
        from file_organizer.utils.epub_enhanced import EPUBMetadata

        meta = EPUBMetadata(title="Test", authors=["Author"])
        assert meta.identifiers == {}
        assert meta.subjects == []
        assert meta.contributors == []


class TestEPUBChapter:
    def test_create(self):
        from file_organizer.utils.epub_enhanced import EPUBChapter

        ch = EPUBChapter(title="Ch1", content="Hello world", order=0, word_count=2)
        assert ch.title == "Ch1"


# ---------------------------------------------------------------------------
# EnhancedEPUBReader — import checks
# ---------------------------------------------------------------------------


class TestImportChecks:
    def test_no_ebooklib(self):
        with patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", False):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            with pytest.raises(ImportError, match="ebooklib"):
                EnhancedEPUBReader()

    def test_no_bs4(self):
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", False),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            with pytest.raises(ImportError, match="beautifulsoup4"):
                EnhancedEPUBReader()


# ---------------------------------------------------------------------------
# _word_to_number
# ---------------------------------------------------------------------------


class TestWordToNumber:
    def test_known_words(self):
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            reader = EnhancedEPUBReader()
            assert reader._word_to_number("one") == 1
            assert reader._word_to_number("ten") == 10
            assert reader._word_to_number("first") == 1
            assert reader._word_to_number("unknown") is None


# ---------------------------------------------------------------------------
# _clean_isbn
# ---------------------------------------------------------------------------


class TestCleanISBN:
    def test_cleans_isbn(self):
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            reader = EnhancedEPUBReader()
            assert reader._clean_isbn("978-3-16-148410-0") == "9783161484100"
            assert reader._clean_isbn("0-306-40615-X") == "030640615X"


# ---------------------------------------------------------------------------
# _detect_series
# ---------------------------------------------------------------------------


class TestDetectSeries:
    def _get_reader(self):
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            return EnhancedEPUBReader()

    def test_from_title_book_pattern(self):
        reader = self._get_reader()
        mock_book = MagicMock()
        mock_book.get_metadata.return_value = []
        series, idx = reader._detect_series("My Series, Book 3", mock_book)
        assert series == "My Series"
        assert idx == 3.0

    def test_from_title_hash_pattern(self):
        reader = self._get_reader()
        mock_book = MagicMock()
        mock_book.get_metadata.return_value = []
        series, idx = reader._detect_series("Epic Saga #5", mock_book)
        assert series == "Epic Saga"
        assert idx == 5.0

    def test_no_series(self):
        reader = self._get_reader()
        mock_book = MagicMock()
        mock_book.get_metadata.return_value = []
        series, idx = reader._detect_series("Just a Title", mock_book)
        assert series is None
        assert idx is None

    def test_calibre_metadata(self):
        reader = self._get_reader()
        mock_book = MagicMock()
        mock_book.get_metadata.side_effect = lambda ns, key: {
            ("", "calibre:series"): [("My Series",)],
            ("", "calibre:series_index"): [("3",)],
        }.get((ns, key), [])
        series, idx = reader._detect_series("Title", mock_book)
        assert series == "My Series"
        assert idx == 3.0


# ---------------------------------------------------------------------------
# _has_cover
# ---------------------------------------------------------------------------


class TestHasCover:
    def test_has_cover_from_metadata(self):
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            reader = EnhancedEPUBReader()
            mock_book = MagicMock()
            mock_book.get_metadata.return_value = [("cover-image",)]
            assert reader._has_cover(mock_book) is True

    def test_no_cover(self):
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            reader = EnhancedEPUBReader()
            mock_book = MagicMock()
            mock_book.get_metadata.return_value = []
            mock_book.get_items.return_value = []
            assert reader._has_cover(mock_book) is False


# ---------------------------------------------------------------------------
# _detect_epub_version
# ---------------------------------------------------------------------------


class TestDetectVersion:
    def test_version_from_attribute(self):
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            reader = EnhancedEPUBReader()
            mock_book = MagicMock()
            mock_book.version = "3.0"
            assert reader._detect_epub_version(mock_book) == "3.0"

    def test_version_exception(self):
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            reader = EnhancedEPUBReader()
            mock_book = MagicMock()
            mock_book.version = None
            mock_book.get_items.side_effect = RuntimeError("fail")
            assert reader._detect_epub_version(mock_book) is None


# ---------------------------------------------------------------------------
# read_epub — file not found
# ---------------------------------------------------------------------------


class TestReadEpub:
    def test_file_not_found(self):
        with (
            patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", True),
            patch("file_organizer.utils.epub_enhanced.BS4_AVAILABLE", True),
        ):
            from file_organizer.utils.epub_enhanced import EnhancedEPUBReader

            reader = EnhancedEPUBReader()
            with pytest.raises(FileNotFoundError):
                reader.read_epub(Path("/nonexistent.epub"))


# ---------------------------------------------------------------------------
# get_epub_metadata — no ebooklib
# ---------------------------------------------------------------------------


class TestGetEpubMetadata:
    def test_no_ebooklib(self):
        with patch("file_organizer.utils.epub_enhanced.EBOOKLIB_AVAILABLE", False):
            from file_organizer.utils.epub_enhanced import get_epub_metadata

            with pytest.raises(ImportError, match="ebooklib"):
                get_epub_metadata(Path("/test.epub"))
