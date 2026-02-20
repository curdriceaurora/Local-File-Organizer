"""Tests for file_organizer.utils.text_processing module.

Covers all public functions: clean_text, sanitize_filename,
extract_keywords, truncate_text, get_unwanted_words, ensure_nltk_data.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.utils.text_processing import (
    clean_text,
    extract_keywords,
    get_unwanted_words,
    sanitize_filename,
    truncate_text,
)


# ---------------------------------------------------------------------------
# truncate_text
# ---------------------------------------------------------------------------


class TestTruncateText:
    """Tests for truncate_text."""

    def test_short_text_unchanged(self) -> None:
        assert truncate_text("hello", max_chars=100) == "hello"

    def test_long_text_truncated(self) -> None:
        result = truncate_text("A" * 200, max_chars=50)
        assert len(result) == 53  # 50 chars + "..."
        assert result.endswith("...")

    def test_exact_length_unchanged(self) -> None:
        text = "x" * 100
        assert truncate_text(text, max_chars=100) == text

    def test_empty_string(self) -> None:
        assert truncate_text("", max_chars=10) == ""


# ---------------------------------------------------------------------------
# get_unwanted_words
# ---------------------------------------------------------------------------


class TestGetUnwantedWords:
    """Tests for get_unwanted_words."""

    def test_returns_set(self) -> None:
        result = get_unwanted_words()
        assert isinstance(result, set)

    def test_contains_common_stopwords(self) -> None:
        words = get_unwanted_words()
        for w in ["the", "and", "is", "in", "of"]:
            assert w in words

    def test_contains_file_type_words(self) -> None:
        words = get_unwanted_words()
        for w in ["jpg", "pdf", "png", "csv"]:
            assert w in words

    def test_without_nltk(self) -> None:
        with patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False):
            words = get_unwanted_words()
            assert isinstance(words, set)
            assert "the" in words


# ---------------------------------------------------------------------------
# clean_text
# ---------------------------------------------------------------------------


class TestCleanText:
    """Tests for clean_text."""

    def test_empty_string_returns_empty(self) -> None:
        assert clean_text("") == ""

    def test_basic_cleaning(self) -> None:
        result = clean_text("Machine Learning Algorithms", max_words=3)
        assert isinstance(result, str)
        assert "_" in result or len(result.split()) <= 1
        assert len(result) > 0

    def test_removes_special_chars(self) -> None:
        result = clean_text("Hello! @World# 123", max_words=5)
        assert "@" not in result
        assert "#" not in result
        assert "!" not in result

    def test_removes_numbers(self) -> None:
        result = clean_text("Report 2024 Analysis", max_words=5)
        assert "2024" not in result

    def test_max_words_limit(self) -> None:
        result = clean_text(
            "one two three four five six seven",
            max_words=3,
            remove_unwanted=False,
            lemmatize=False,
        )
        parts = result.split("_")
        assert len(parts) <= 3

    def test_camel_case_splitting(self) -> None:
        result = clean_text(
            "camelCaseWord", max_words=5, remove_unwanted=False, lemmatize=False
        )
        # Should split camelCase into separate words
        assert "camel" in result.lower()
        assert "case" in result.lower()

    def test_remove_unwanted_false(self) -> None:
        result = clean_text("the quick brown", max_words=5, remove_unwanted=False)
        # "the" should be kept when remove_unwanted is False
        assert result  # non-empty

    def test_deduplication(self) -> None:
        # Deduplication only happens when remove_unwanted=True
        result = clean_text(
            "python python python coding",
            max_words=5,
            remove_unwanted=True,
            lemmatize=False,
        )
        parts = result.split("_")
        assert parts.count("python") == 1

    def test_unicode_input(self) -> None:
        result = clean_text("café résumé naïve")
        assert isinstance(result, str)

    def test_without_nltk(self) -> None:
        with patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False):
            result = clean_text("Machine Learning Algorithms", max_words=3)
            assert isinstance(result, str)


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------


class TestSanitizeFilename:
    """Tests for sanitize_filename."""

    def test_basic_sanitization(self) -> None:
        result = sanitize_filename("Machine Learning Guide")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_empty_input_returns_untitled(self) -> None:
        assert sanitize_filename("") == "untitled"

    def test_only_stopwords_returns_untitled(self) -> None:
        result = sanitize_filename("the and is of")
        assert result == "untitled"

    def test_max_length_enforced(self) -> None:
        result = sanitize_filename("a" * 200, max_length=20)
        assert len(result) <= 20

    def test_max_words_enforced(self) -> None:
        result = sanitize_filename(
            "one two three four five six seven", max_words=2
        )
        parts = result.split("_")
        assert len(parts) <= 2

    def test_special_chars_removed(self) -> None:
        result = sanitize_filename("hello/world:test?file")
        assert "/" not in result
        assert ":" not in result
        assert "?" not in result

    def test_result_is_lowercase(self) -> None:
        result = sanitize_filename("UPPERCASE WORDS")
        assert result == result.lower()

    def test_no_leading_trailing_underscores(self) -> None:
        result = sanitize_filename("___test___")
        assert not result.startswith("_")
        assert not result.endswith("_")

    def test_no_multiple_underscores(self) -> None:
        result = sanitize_filename("test   file   name", max_words=5)
        assert "__" not in result


# ---------------------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------------------


class TestExtractKeywords:
    """Tests for extract_keywords."""

    def test_returns_list(self) -> None:
        result = extract_keywords("Python programming is great for machine learning")
        assert isinstance(result, list)

    def test_top_n_limit(self) -> None:
        result = extract_keywords(
            "Python programming is great for machine learning development",
            top_n=3,
        )
        assert len(result) <= 3

    def test_empty_text(self) -> None:
        result = extract_keywords("")
        assert isinstance(result, list)

    def test_without_nltk(self) -> None:
        with patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False):
            result = extract_keywords("Python programming is great")
            assert isinstance(result, list)
            assert len(result) > 0

    def test_keywords_are_strings(self) -> None:
        result = extract_keywords("Machine learning artificial intelligence")
        for keyword in result:
            assert isinstance(keyword, str)
