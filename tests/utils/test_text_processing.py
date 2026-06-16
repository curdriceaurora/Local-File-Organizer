"""Tests for text_processing.py.

WP-4.4 (#1234): text processing is now fully offline and deterministic — vendored
English stopwords + the pure-Python ``snowballstemmer`` package, with a regex ASCII
tokenizer. There is no longer any NLTK import, ``NLTK_AVAILABLE`` flag, or
``nltk.download()`` machinery to mock; these tests assert the deterministic offline
behavior directly.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.utils.text_processing import (
    _ENGLISH_STOPWORDS,
    clean_text,
    ensure_nltk_data,
    extract_keywords,
    get_unwanted_words,
    sanitize_filename,
    truncate_text,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


class TestEnsureNltkData:
    """`ensure_nltk_data` is now a no-op backward-compat shim."""

    def test_ensure_nltk_data_is_noop_and_does_not_raise(self) -> None:
        """No-op shim returns None without raising."""
        assert ensure_nltk_data() is None

    def test_ensure_nltk_data_logs_debug_only(self) -> None:
        """Shim only emits a debug log; no warnings/info/network."""
        with patch("file_organizer.utils.text_processing.logger") as mock_logger:
            ensure_nltk_data()
            mock_logger.debug.assert_called_once()
            mock_logger.warning.assert_not_called()
            mock_logger.info.assert_not_called()

    def test_module_no_longer_exposes_nltk_symbols(self) -> None:
        """No nltk import / download is reachable from the module."""
        import file_organizer.utils.text_processing as mod

        # The module must not even import nltk anymore.
        assert not hasattr(mod, "nltk")
        assert not hasattr(mod, "NLTK_AVAILABLE")
        assert not hasattr(mod, "word_tokenize")
        assert not hasattr(mod, "stopwords")
        assert not hasattr(mod, "WordNetLemmatizer")


class TestGetUnwantedWords:
    """`get_unwanted_words` unions curated words with vendored stopwords."""

    def test_includes_curated_words(self) -> None:
        """Hand-curated words are preserved."""
        unwanted = get_unwanted_words()
        assert "generated" in unwanted
        assert "untitled" in unwanted
        assert "filename" in unwanted

    def test_includes_vendored_stopwords(self) -> None:
        """Vendored English stopwords are unioned in."""
        unwanted = get_unwanted_words()
        assert "the" in unwanted
        assert "and" in unwanted
        assert "a" in unwanted
        # Every vendored stopword should be present.
        assert _ENGLISH_STOPWORDS <= unwanted

    def test_returns_set(self) -> None:
        """Returns a (mutable) set."""
        unwanted = get_unwanted_words()
        assert isinstance(unwanted, set)
        assert len(unwanted) > 100


class TestCleanText:
    """`clean_text` deterministic offline behavior."""

    def test_clean_text_empty(self) -> None:
        """Empty / falsy input returns empty string."""
        assert clean_text("") == ""
        assert clean_text(None) == ""

    def test_clean_text_basic_filters_stopwords(self) -> None:
        """Stopwords filtered; numbers and punctuation stripped."""
        text = "Hello World! This is a test 123."
        # "this", "is", "a" are stopwords; "123" and "!" removed.
        result = clean_text(text, lemmatize=False)
        assert result == "hello_world_test"

    def test_clean_text_max_words(self) -> None:
        """`max_words` caps the output token count."""
        text = "apple banana orange grape pear kiwi"
        result = clean_text(text, max_words=3, remove_unwanted=False, lemmatize=False)
        assert result == "apple_banana_orange"

    def test_clean_text_camel_case(self) -> None:
        """camelCase / PascalCase is split into words."""
        result = clean_text("camelCaseFileName", remove_unwanted=False, lemmatize=False)
        assert result == "camel_case_file_name"

    def test_clean_text_removes_numbers(self) -> None:
        """Digits are stripped."""
        result = clean_text("report 2024 analysis 42", remove_unwanted=False, lemmatize=False)
        assert "2024" not in result
        assert "42" not in result
        assert "report" in result

    def test_clean_text_removes_special_chars(self) -> None:
        """Special characters become separators."""
        result = clean_text("hello@world#foo$bar", remove_unwanted=False, lemmatize=False)
        assert "@" not in result
        assert "#" not in result
        assert "$" not in result
        assert "hello" in result
        assert "world" in result

    def test_clean_text_removes_duplicates(self) -> None:
        """Duplicate tokens are deduped, order preserved."""
        result = clean_text("apple apple banana apple banana", max_words=10, lemmatize=False)
        words = result.split("_")
        assert words == ["apple", "banana"]

    def test_clean_text_no_removal_keeps_stopwords(self) -> None:
        """remove_unwanted=False preserves stopwords like 'the'."""
        result = clean_text("the quick fox", remove_unwanted=False, max_words=10, lemmatize=False)
        words = result.split("_")
        assert words == ["the", "quick", "fox"]

    def test_clean_text_lowercases(self) -> None:
        """Output is lowercase."""
        result = clean_text("HELLO WORLD", remove_unwanted=False, lemmatize=False)
        assert result == result.lower()


class TestStemming:
    """Deterministic Snowball stemming via the `lemmatize` flag."""

    def test_stemming_is_applied_by_default(self) -> None:
        """Default lemmatize=True stems tokens (running -> run, dogs -> dog)."""
        result = clean_text("running dogs", remove_unwanted=False)
        assert result == "run_dog"

    def test_stemming_disabled_preserves_surface_form(self) -> None:
        """lemmatize=False leaves surface forms intact."""
        result = clean_text("running dogs", remove_unwanted=False, lemmatize=False)
        assert result == "running_dogs"

    def test_stemming_is_deterministic(self) -> None:
        """Repeated calls yield identical output."""
        text = "organizing organized organizes organization"
        first = clean_text(text)
        second = clean_text(text)
        assert first == second
        # All four collapse to the same Snowball stem 'organiz', deduped to one token.
        assert first == "organiz"

    def test_stemming_collapses_inflections(self) -> None:
        """Inflected forms stem to a shared root and dedupe (remove_unwanted dedupes)."""
        result = clean_text("jumps jumping jumped")
        assert result == "jump"


class TestSanitizeFilename:
    """`sanitize_filename` end-to-end."""

    def test_basic(self) -> None:
        """Basic name is lowercased and underscore-joined."""
        result = sanitize_filename("My Report 2024")
        assert isinstance(result, str)
        assert len(result) > 0
        assert result == result.lower()
        assert " " not in result

    def test_empty_returns_untitled(self) -> None:
        """Empty input yields the default."""
        assert sanitize_filename("") == "untitled"

    def test_only_stopwords_returns_untitled(self) -> None:
        """A name of only stopwords cleans to empty -> untitled."""
        assert sanitize_filename("the and a of") == "untitled"

    def test_max_length(self) -> None:
        """Output is capped to max_length."""
        long_name = " ".join(["word"] * 50)
        result = sanitize_filename(long_name, max_length=20)
        assert 1 <= len(result) <= 20

    def test_special_chars(self) -> None:
        """Special characters are stripped end-to-end."""
        result = sanitize_filename("file@name#with$chars!")
        for ch in "@#$!":
            assert ch not in result

    def test_leading_trailing_underscores(self) -> None:
        """No leading/trailing underscores remain."""
        result = sanitize_filename("  hello world  ")
        assert not result.startswith("_")
        assert not result.endswith("_")


class TestExtractKeywords:
    """`extract_keywords` deterministic frequency extraction."""

    def test_empty(self) -> None:
        """Empty input returns empty list."""
        assert extract_keywords("") == []

    def test_frequency_ordering(self) -> None:
        """Most frequent words returned first (>3 chars, non-stopword)."""
        text = "apple banana apple orange apple banana pear"
        keywords = extract_keywords(text, top_n=2)
        assert keywords == ["apple", "banana"]

    def test_top_n_limit(self) -> None:
        """`top_n` caps the result count."""
        text = "alpha beta gamma alpha beta alpha"
        keywords = extract_keywords(text, top_n=1)
        assert keywords == ["alpha"]

    def test_short_words_filtered(self) -> None:
        """Words <= 3 chars are dropped."""
        keywords = extract_keywords("the big extraordinary cat extraordinary")
        assert "the" not in keywords
        assert "big" not in keywords
        assert "cat" not in keywords
        assert "extraordinary" in keywords

    def test_stopwords_filtered(self) -> None:
        """Long stopwords are dropped."""
        keywords = extract_keywords("about because through python python")
        assert "about" not in keywords
        assert "because" not in keywords
        assert "through" not in keywords
        assert keywords == ["python"]

    def test_deterministic(self) -> None:
        """Repeated calls return identical results."""
        text = "report report invoice invoice payment"
        assert extract_keywords(text) == extract_keywords(text)


class TestTruncateText:
    """`truncate_text` edge cases."""

    def test_no_truncation(self) -> None:
        """Text within limit is unchanged."""
        assert truncate_text("1234567890", max_chars=15) == "1234567890"

    def test_truncation(self) -> None:
        """Over-limit text is truncated with an ellipsis."""
        assert truncate_text("1234567890", max_chars=5) == "12345..."

    def test_empty(self) -> None:
        """Empty string returns empty string."""
        assert truncate_text("") == ""

    def test_exact_length(self) -> None:
        """Text exactly at the limit is unchanged."""
        assert truncate_text("12345", max_chars=5) == "12345"
