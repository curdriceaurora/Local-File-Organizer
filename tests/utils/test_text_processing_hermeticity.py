"""Tests for text-processing hermeticity (Issue #470, WP-4.4 #1234).

Verifies that text processing is fully offline and deterministic. As of WP-4.4 the
module no longer depends on NLTK or any downloadable corpus — stopwords are vendored
and stemming uses the pure-Python ``snowballstemmer`` package — so these tests now
pass trivially in any environment (no corpus to install, no network to reach).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from file_organizer.utils.text_processing import (
    clean_text,
    ensure_nltk_data,
    extract_keywords,
    get_unwanted_words,
    sanitize_filename,
)

pytestmark = pytest.mark.unit


class TestOfflineHermeticity:
    """Tests ensuring text processing works fully offline."""

    @pytest.mark.parametrize(
        "text,expected_contains",
        [
            ("Hello World Test", ["hello", "world", "test"]),
            ("CamelCaseTest", ["camel", "case", "test"]),
            ("Multiple   Spaces", ["multiple", "spaces"]),
        ],
    )
    def test_clean_text_offline(
        self,
        text: str,
        expected_contains: list[str],
        isolated_nltk_environment: None,
    ) -> None:
        """clean_text works fully offline; surface forms preserved (lemmatize=False)."""
        result = clean_text(text, max_words=5, lemmatize=False)

        # Result should be non-empty and lowercase.
        assert result
        assert result == result.lower()

        # Expected words present.
        result_words = set(result.split("_"))
        for expected_word in expected_contains:
            assert expected_word in result_words, (
                f"Expected '{expected_word}' in result '{result}' (words: {result_words})"
            )

    def test_extract_keywords_offline(
        self,
        isolated_nltk_environment: None,
    ) -> None:
        """extract_keywords works fully offline."""
        text = "python programming language development tools"
        keywords = extract_keywords(text, top_n=3)

        # 5 non-stopword words >3 chars, top_n=3 -> exactly 3 returned.
        assert len(keywords) == 3
        for keyword in keywords:
            assert keyword in text.lower()

    def test_get_unwanted_words_offline(
        self,
        isolated_nltk_environment: None,
    ) -> None:
        """get_unwanted_words includes vendored stopwords without any corpus."""
        unwanted = get_unwanted_words()

        assert isinstance(unwanted, set)
        assert len(unwanted) > 0
        # Vendored stopwords are always present.
        assert "the" in unwanted
        assert "and" in unwanted
        assert "a" in unwanted

    def test_sanitize_filename_offline(
        self,
        isolated_nltk_environment: None,
    ) -> None:
        """sanitize_filename works fully offline."""
        name = "Test Document Name 2025"
        result = sanitize_filename(name)

        assert result
        assert result == result.lower()
        assert all(c.isalnum() or c == "_" for c in result)

    def test_ensure_nltk_data_is_noop(
        self,
        isolated_nltk_environment: None,
    ) -> None:
        """ensure_nltk_data is a no-op that does not raise or touch the network."""
        with patch("file_organizer.utils.text_processing.logger") as mock_logger:
            assert ensure_nltk_data() is None
            mock_logger.warning.assert_not_called()
            mock_logger.info.assert_not_called()


class TestDeterministicBehavior:
    """Tests verifying deterministic, offline NLP behavior."""

    def test_clean_text_stems_deterministically(self) -> None:
        """Default stemming is deterministic and offline."""
        # running -> run, files -> file, organized -> organiz
        result = clean_text("running files organized", remove_unwanted=False)
        assert result == "run_file_organiz"
        # Repeated call is identical.
        assert result == clean_text("running files organized", remove_unwanted=False)

    def test_extract_keywords_deterministic(self) -> None:
        """Frequency-ranked keywords are deterministic."""
        text = "python test code testing python"
        first = extract_keywords(text, top_n=2)
        second = extract_keywords(text, top_n=2)
        assert first == second
        # 'python' appears twice -> ranked first; 'testing' (>3 chars) next.
        assert first[0] == "python"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
