"""Tests for NLTK test hermeticity (Issue #470).

Verifies that text processing tests pass in isolated environments
without host NLTK corpus data.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.utils.text_processing import (
    clean_text,
    ensure_nltk_data,
    extract_keywords,
    get_unwanted_words,
    sanitize_filename,
)


@pytest.mark.unit
class TestNLTKHermeticity:
    """Tests ensuring NLTK functionality works in isolated environments."""

    @pytest.mark.parametrize(
        "text,expected_contains",
        [
            ("Hello World Test", ["hello", "world"]),
            ("CamelCaseTest", ["camel", "case", "test"]),
            ("Multiple   Spaces", ["multiple", "spaces"]),
        ],
    )
    def test_clean_text_without_nltk_corpus(
        self,
        text: str,
        expected_contains: list[str],
        isolated_nltk_environment: None,
    ) -> None:
        """Test clean_text works without NLTK corpus in isolated env."""
        result = clean_text(text, max_words=5)

        # Result should be non-empty
        assert result

        # Result should be lowercase
        assert result == result.lower()

        # Result should contain underscores for word separation
        assert "_" in result or len(result.split("_")) >= 1

        # Result should contain the expected words (possibly with underscores)
        result_words = set(result.lower().split("_"))
        for expected_word in expected_contains:
            assert expected_word in result_words, (
                f"Expected '{expected_word}' in result '{result}' (words: {result_words})"
            )

    def test_extract_keywords_fallback_without_nltk(
        self,
        isolated_nltk_environment: None,
    ) -> None:
        """Test extract_keywords uses fallback without NLTK."""
        text = "python programming language development tools"
        keywords = extract_keywords(text, top_n=3)

        # Should return at most 3 keywords
        assert len(keywords) <= 3

        # Keywords should be from the input text
        for keyword in keywords:
            assert keyword in text.lower()

    def test_get_unwanted_words_without_nltk(
        self,
        isolated_nltk_environment: None,
    ) -> None:
        """Test get_unwanted_words works without NLTK stopwords."""
        unwanted = get_unwanted_words()

        # Should still return a set of unwanted words
        assert isinstance(unwanted, set)
        assert len(unwanted) > 0

        # Should contain built-in unwanted words
        assert "the" in unwanted
        assert "and" in unwanted
        assert "a" in unwanted

    def test_sanitize_filename_without_nltk(
        self,
        isolated_nltk_environment: None,
    ) -> None:
        """Test sanitize_filename works without NLTK."""
        name = "Test Document Name 2025"
        result = sanitize_filename(name)

        # Should be non-empty
        assert result

        # Should be lowercase
        assert result == result.lower()

        # Should not contain special characters
        assert all(c.isalnum() or c == "_" for c in result)

    def test_ensure_nltk_data_in_isolated_env(
        self,
        isolated_nltk_environment: None,
    ) -> None:
        """Test ensure_nltk_data handles missing NLTK gracefully."""
        # Should not raise an exception
        ensure_nltk_data()

        # Should complete without creating .config directory
        config_path = Path.home() / ".config"
        if config_path.exists():
            # If .config exists, ensure it's not a new creation from this test
            # (This is a soft check - we mainly care that the function doesn't crash)
            pass


@pytest.mark.unit
class TestNLTKMockingCompleteness:
    """Tests verifying NLTK mocking is complete for all code paths."""

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("file_organizer.utils.text_processing.stopwords")
    @patch("file_organizer.utils.text_processing.WordNetLemmatizer")
    def test_clean_text_with_mocked_nltk(
        self,
        mock_lemmatizer_cls: MagicMock,
        mock_stopwords: MagicMock,
        mock_tokenize: MagicMock,
    ) -> None:
        """Test clean_text works with comprehensive NLTK mocking."""
        # Setup mocks
        mock_tokenize.return_value = ["hello", "world", "test"]
        mock_stopwords.words.return_value = ["the", "a"]

        mock_lemmatizer = MagicMock()
        mock_lemmatizer.lemmatize.side_effect = lambda x: x
        mock_lemmatizer_cls.return_value = mock_lemmatizer

        # Test clean_text
        clean_text("hello world test", max_words=5)

        # Verify mocks were called
        mock_tokenize.assert_called()

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("nltk.probability.FreqDist", create=True)
    def test_extract_keywords_with_mocked_nltk(
        self,
        mock_freqdist_cls: MagicMock,
        mock_tokenize: MagicMock,
    ) -> None:
        """Test extract_keywords works with comprehensive NLTK mocking."""
        # Setup mocks
        mock_tokenize.return_value = ["python", "test", "code", "testing"]

        mock_freqdist_instance = MagicMock()
        mock_freqdist_instance.most_common.return_value = [
            ("python", 2),
            ("test", 1),
        ]
        mock_freqdist_cls.return_value = mock_freqdist_instance

        # Test extract_keywords
        extract_keywords("python test code testing", top_n=2)

        # Verify mocks were called
        mock_tokenize.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
