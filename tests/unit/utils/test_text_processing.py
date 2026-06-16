"""Unit tests for text_processing.py (WP-4.4 #1234, offline + deterministic)."""

from unittest.mock import patch

import pytest

from file_organizer.utils.text_processing import (
    clean_text,
    ensure_nltk_data,
    extract_keywords,
    get_unwanted_words,
    sanitize_filename,
    truncate_text,
)

pytestmark = [pytest.mark.unit]


class TestEnsureNltkData:
    def test_ensure_nltk_data_is_noop(self):
        # Backward-compat shim: returns early, no error, no network.
        assert ensure_nltk_data() is None

    def test_ensure_nltk_data_does_not_warn(self):
        with patch("file_organizer.utils.text_processing.logger") as mock_logger:
            ensure_nltk_data()
            mock_logger.warning.assert_not_called()


class TestGetUnwantedWords:
    def test_includes_stopwords_and_curated(self):
        words = get_unwanted_words()
        assert "the" in words
        assert "and" in words
        assert "generated" in words
        assert "custom_word" not in words


class TestCleanText:
    def test_clean_text_empty(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""

    def test_clean_text_basic(self):
        # "the", "over" are stopwords; numbers and punctuation stripped.
        result = clean_text(
            "The Quick Brown Fox Jumps Over 123 Lazy Dogs!", max_words=3, lemmatize=False
        )
        assert result == "quick_brown_fox"

    def test_clean_text_camel_case_fallback(self):
        # 'a' is a stopword and is filtered out.
        result = clean_text("a camelCase test", lemmatize=False)
        assert result == "camel_case_test"

    def test_clean_text_stems_by_default(self):
        # Default lemmatize=True: testing -> test, words -> word.
        result = clean_text("testing words", remove_unwanted=False)
        assert result == "test_word"

    def test_clean_text_no_stem(self):
        result = clean_text("Test error", lemmatize=False, remove_unwanted=False)
        assert "test" in result
        assert "error" in result


class TestSanitizeFilename:
    def test_sanitize_filename(self):
        assert sanitize_filename("") == "untitled"
        # Only stopwords -> cleans to empty -> default.
        assert sanitize_filename("the and a of") == "untitled"
        # 'A' is a stopword; 'valid'/'name' stem to themselves.
        assert sanitize_filename("A valid name", max_words=5) == "valid_name"
        assert sanitize_filename("A" * 100, max_length=10) == "a" * 10


class TestExtractKeywords:
    def test_extract_keywords_frequency(self):
        # 'apple' (>3 chars) appears most; 'banana' next; 'cherry' last.
        result = extract_keywords("apple banana apple cherry")
        assert result[0] == "apple"
        assert "banana" in result
        assert "cherry" in result

    def test_extract_keywords_empty(self):
        assert extract_keywords("") == []

    def test_extract_keywords_filters_short_and_stopwords(self):
        # 'the' is a stopword; 'cat' is <=3 chars; both dropped.
        result = extract_keywords("the cat python python", top_n=2)
        assert result == ["python"]

    def test_extract_keywords_non_positive_top_n_returns_empty(self):
        # A non-positive top_n must return [] rather than slicing ranked[:top_n]
        # (top_n=0 -> empty slice; top_n=-1 -> almost-all keywords) (#1291 review).
        text = "apple banana apple cherry mango"
        assert extract_keywords(text, top_n=0) == []
        assert extract_keywords(text, top_n=-1) == []


class TestTruncateText:
    def test_truncate_text(self):
        assert truncate_text("short test", 100) == "short test"
        assert truncate_text("a" * 10, 5) == "aaaaa..."
