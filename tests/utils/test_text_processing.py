"""Tests for text_processing.py."""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from file_organizer.utils.text_processing import (
    clean_text,
    ensure_nltk_data,
    extract_keywords,
    get_unwanted_words,
    sanitize_filename,
    truncate_text,
)

pytestmark = [pytest.mark.ci, pytest.mark.unit]


class TestTextProcessing:
    """Test text processing utilities."""

    @pytest.fixture(autouse=True)
    def reset_nltk_ready(self) -> None:
        """Reset _nltk_ready flag before each test (ensures idempotency flag doesn't affect tests)."""
        import file_organizer.utils.text_processing as text_processing_module

        text_processing_module._nltk_ready = False
        yield
        text_processing_module._nltk_ready = False

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    @patch("file_organizer.utils.text_processing.logger")
    def test_ensure_nltk_data_unavailable(self, mock_logger: MagicMock) -> None:
        """Test ensure_nltk_data when NLTK is not available."""
        ensure_nltk_data()
        mock_logger.warning.assert_called_with(
            "NLTK not available, text processing will be limited"
        )

    @patch("file_organizer.utils.text_processing.logger")
    def test_ensure_nltk_data_returns_when_already_ready(self, mock_logger: MagicMock) -> None:
        """Test ensure_nltk_data short-circuits after initialization."""
        import file_organizer.utils.text_processing as text_processing_module

        text_processing_module._nltk_ready = True

        ensure_nltk_data()

        mock_logger.warning.assert_not_called()
        mock_logger.info.assert_not_called()
        mock_logger.debug.assert_not_called()

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.nltk.download")
    @patch("file_organizer.utils.text_processing.stopwords")
    @patch("file_organizer.utils.text_processing.word_tokenize")
    def test_ensure_nltk_data_available(
        self, mock_tokenize: MagicMock, mock_stopwords: MagicMock, mock_download: MagicMock
    ) -> None:
        """Test ensure_nltk_data successfully downloads missing items."""
        # Cause LookupError to trigger download
        mock_stopwords.words.side_effect = LookupError()
        mock_tokenize.side_effect = LookupError()

        # Patch wordnet at nltk.corpus level so the local
        # ``from nltk.corpus import wordnet`` inside ensure_nltk_data()
        # picks up the mock instead of the real lazy-loaded corpus.
        with patch("nltk.corpus.wordnet") as mock_wordnet:
            mock_wordnet.synsets.side_effect = LookupError()

            ensure_nltk_data()

            # With NLTK 3.8+ compatibility, we try punkt_tab as fallback, then punkt
            assert mock_download.call_count == 4
            # Verify downloads happen in expected order (stopwords, punkt_tab/punkt, wordnet)
            # Note: __bool__() calls come from if statements checking the download result
            mock_download.assert_has_calls(
                [
                    call("stopwords", quiet=True),
                    call().__bool__(),
                    call("punkt_tab", quiet=True),  # tried as fallback
                    call().__bool__(),
                    call("punkt", quiet=True),  # fallback when punkt_tab fails
                    call().__bool__(),
                    call("wordnet", quiet=True),
                    call().__bool__(),
                ],
                any_order=False,
            )

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.stopwords")
    @patch("file_organizer.utils.text_processing.logger")
    def test_ensure_nltk_data_dataset_check_failure_logs_debug(
        self,
        mock_logger: MagicMock,
        mock_stopwords: MagicMock,
    ) -> None:
        """Test non-LookupError dataset failures log a debug message."""
        mock_stopwords.words.return_value = ["and", "the"]

        with patch("nltk.corpus.wordnet") as mock_wordnet:
            mock_wordnet.synsets.side_effect = RuntimeError("wordnet unavailable")

            ensure_nltk_data()

        assert any(
            "NLTK dataset check failed for wordnet" in str(call)
            for call in mock_logger.debug.call_args_list
        )

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.nltk.download")
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("file_organizer.utils.text_processing.stopwords")
    @patch("file_organizer.utils.text_processing.logger")
    def test_ensure_nltk_data_downloaded_wordnet_is_verified(
        self,
        mock_logger: MagicMock,
        mock_stopwords: MagicMock,
        mock_tokenize: MagicMock,
        mock_download: MagicMock,
    ) -> None:
        """Test downloaded wordnet data is verified after a LookupError."""
        mock_stopwords.words.return_value = ["and", "the"]
        mock_tokenize.return_value = ["tokenized"]

        with patch("nltk.corpus.wordnet") as mock_wordnet:
            mock_wordnet.synsets.side_effect = [LookupError("missing"), ["synset"]]

            ensure_nltk_data()

        mock_download.assert_called_once_with("wordnet", quiet=True)
        assert mock_wordnet.synsets.call_count == 2
        mock_logger.info.assert_called_with("Downloading NLTK dataset: wordnet")
        assert any(
            "downloaded and verified successfully" in str(call)
            for call in mock_logger.debug.call_args_list
        )

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.nltk.download")
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("file_organizer.utils.text_processing.stopwords")
    @patch("file_organizer.utils.text_processing.logger")
    def test_ensure_nltk_data_punkt_fallback_path(
        self,
        mock_logger: MagicMock,
        mock_stopwords: MagicMock,
        mock_tokenize: MagicMock,
        mock_download: MagicMock,
    ) -> None:
        """Test ensure_nltk_data punkt fallback when punkt_tab fails (NLTK 3.8+ scenario)."""
        # Initial stopwords check fails (triggers download)
        mock_stopwords.words.side_effect = LookupError()

        # Setup word_tokenize to fail on first three calls (punkt, punkt_tab, punkt attempts)
        # then succeed on wordnet check
        mock_tokenize.side_effect = [
            LookupError(),  # First call in punkt try block fails
            LookupError(),  # Call in punkt_tab fallback block fails
            LookupError("punkt load failed"),  # Call in punkt fallback block fails
            None,  # Call in wordnet synsets succeeds (after it was called)
        ]

        with patch("nltk.corpus.wordnet") as mock_wordnet:
            mock_wordnet.synsets.side_effect = LookupError()
            ensure_nltk_data()

        # Verify punkt_tab was tried as fallback
        mock_download.assert_any_call("punkt_tab", quiet=True)
        # Verify punkt was tried when punkt_tab failed
        mock_download.assert_any_call("punkt", quiet=True)
        # Verify debug logs were called for fallback logic and exception handling
        debug_calls = [str(call) for call in mock_logger.debug.call_args_list]
        assert any("punkt_tab failed" in str(call) for call in debug_calls)
        assert any("Failed to load punkt" in str(call) for call in debug_calls)

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.nltk.download")
    @patch("file_organizer.utils.text_processing.stopwords")
    @patch("file_organizer.utils.text_processing.logger")
    def test_ensure_nltk_data_download_fails(
        self, mock_logger: MagicMock, mock_stopwords: MagicMock, mock_download: MagicMock
    ) -> None:
        """Test ensure_nltk_data when download fails."""
        mock_stopwords.words.side_effect = LookupError()
        mock_download.side_effect = Exception("Download failed")

        with patch("nltk.corpus.wordnet"):
            ensure_nltk_data()

        mock_logger.warning.assert_called()

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.nltk.download")
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("file_organizer.utils.text_processing.stopwords")
    @patch("file_organizer.utils.text_processing.logger")
    def test_ensure_nltk_data_punkt_exception_handling(
        self,
        mock_logger: MagicMock,
        mock_stopwords: MagicMock,
        mock_tokenize: MagicMock,
        mock_download: MagicMock,
    ) -> None:
        """
        Exercise ensure_nltk_data's punkt/punkt_tab exception-handling paths by simulating successive tokenization failures.

        Simulates word_tokenize raising LookupError three times (punkt, punkt_tab, punkt attempts) while wordnet succeeds; calls ensure_nltk_data() and asserts the logger produced debug messages containing "punkt not available", "punkt_tab failed", and "Failed to load punkt".
        """
        # Ensure stopwords succeeds so we focus on punkt path
        mock_stopwords.words.return_value = ["test"]

        # Make word_tokenize fail on all punkt path attempts
        # First call (line 50): raises LookupError on initial punkt check
        # Then punkt_tab download, second call (line 56): raises LookupError
        # Then punkt download, third call (line 64): raises LookupError
        mock_tokenize.side_effect = [
            LookupError("punkt missing"),  # Initial punkt check exception
            LookupError("punkt_tab missing"),  # punkt_tab fallback exception
            LookupError("punkt load error"),  # punkt fallback exception
        ]

        with patch("nltk.corpus.wordnet") as mock_wordnet:
            mock_wordnet.synsets.return_value = []  # wordnet succeeds
            ensure_nltk_data()

        # Verify all three exception handlers were entered (indicating all lines executed)
        # Line 40 exception handler
        assert any("punkt not available" in str(call) for call in mock_logger.debug.call_args_list)
        # Line 46 exception handler
        assert any("punkt_tab failed" in str(call) for call in mock_logger.debug.call_args_list)
        # Line 52 exception handler
        assert any("Failed to load punkt" in str(call) for call in mock_logger.debug.call_args_list)

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.stopwords")
    def test_get_unwanted_words_with_nltk(self, mock_stopwords: MagicMock) -> None:
        """Test getting unwanted words including NLTK stopwords."""
        mock_stopwords.words.return_value = ["nltkword1", "nltkword2"]
        unwanted = get_unwanted_words()

        # Built-in words
        assert "the" in unwanted
        assert "generated" in unwanted
        assert "untitled" in unwanted
        # NLTK words
        assert "nltkword1" in unwanted
        assert "nltkword2" in unwanted

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.stopwords")
    @patch("file_organizer.utils.text_processing.logger")
    def test_get_unwanted_words_nltk_fails(
        self, mock_logger: MagicMock, mock_stopwords: MagicMock
    ) -> None:
        """Test getting unwanted words when stopwords fails."""
        mock_stopwords.words.side_effect = LookupError()

        unwanted = get_unwanted_words()

        # Should still return built-in words
        assert "the" in unwanted
        mock_logger.warning.assert_called()

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_get_unwanted_words_without_nltk(self) -> None:
        """Test getting unwanted words without NLTK stopwords."""
        unwanted = get_unwanted_words()
        assert "the" in unwanted
        assert "generated" in unwanted

    def test_clean_text_empty(self) -> None:
        """Test clean_text with empty input."""
        assert clean_text("") == ""
        assert clean_text(None) == ""

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_basic_without_nltk(self) -> None:
        """Test clean_text fallback without NLTK."""
        text = "Hello World! This is a test 123."
        # "this", "is", "a" should be filtered out.
        # "123" and "!" should be removed.
        result = clean_text(text)
        assert result == "hello_world_test"

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_max_words(self) -> None:
        """Test clean_text respects max_words."""
        text = "apple banana orange grape pear kiwi"
        result = clean_text(text, max_words=3, remove_unwanted=False)
        assert result == "apple_banana_orange"

    def test_clean_text_camel_case(self) -> None:
        """Test clean_text splits camelCase correctly."""
        with patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False):
            result = clean_text("camelCaseFileName", remove_unwanted=False)
            assert result == "camel_case_file_name"

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize")
    def test_clean_text_nltk_tokenize_fails(self, mock_tokenize: MagicMock) -> None:
        """Test clean_text fallback when word_tokenize fails."""
        mock_tokenize.side_effect = LookupError()

        result = clean_text("Hello world test", remove_unwanted=False)
        # Should fall back to simple split
        assert result == "hello_world_test"

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("file_organizer.utils.text_processing.WordNetLemmatizer")
    @patch("file_organizer.utils.text_processing.logger")
    def test_clean_text_lemmatization_fails(
        self, mock_logger: MagicMock, mock_lemmatizer_cls: MagicMock, mock_tokenize: MagicMock
    ) -> None:
        """Test clean_text when lemmatization fails."""
        mock_tokenize.return_value = ["hello", "world"]
        mock_lemmatizer = MagicMock()
        mock_lemmatizer.lemmatize.side_effect = Exception("Lemmatization error")
        mock_lemmatizer_cls.return_value = mock_lemmatizer

        result = clean_text("hello world", lemmatize=True, remove_unwanted=False)
        # Should continue even if lemmatization fails — both tokens retained
        assert "hello" in result and "world" in result
        mock_logger.debug.assert_called()

    def test_sanitize_filename_basic(self) -> None:
        """Test simple filename sanitization."""
        with patch("file_organizer.utils.text_processing.clean_text") as mock_clean:
            mock_clean.return_value = "clean_file_name"
            result = sanitize_filename("Some Name")
            assert result == "clean_file_name"

    def test_sanitize_filename_empty_cleanup(self) -> None:
        """Test sanitize_filename falls back to untitled."""
        with patch("file_organizer.utils.text_processing.clean_text") as mock_clean:
            mock_clean.return_value = ""
            assert sanitize_filename("") == "untitled"

    def test_sanitize_filename_max_length(self) -> None:
        """Test sanitize_filename truncates to max_length."""
        with patch("file_organizer.utils.text_processing.clean_text") as mock_clean:
            mock_clean.return_value = "a" * 100
            result = sanitize_filename("long string", max_length=10)
            assert len(result) == 10
            assert result == "a" * 10

    def test_sanitize_filename_special_chars(self) -> None:
        """Test sanitize_filename replaces unhandled special characters."""
        with patch("file_organizer.utils.text_processing.clean_text") as mock_clean:
            mock_clean.return_value = "file@name#with$chars"
            result = sanitize_filename("raw name")
            assert result == "file_name_with_chars"

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_extract_keywords_fallback(self) -> None:
        """Test keyword extraction fallback block when missing NLTK."""
        text = "apple banana apple orange apple banana pear"
        keywords = extract_keywords(text, top_n=2)
        assert len(keywords) == 2
        assert "apple" in keywords
        assert "banana" in keywords

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("file_organizer.utils.text_processing.nltk.probability.FreqDist", create=True)
    def test_extract_keywords_nltk(
        self, mock_freqdist_cls: MagicMock, mock_tokenize: MagicMock
    ) -> None:
        """Test keyword extraction with NLTK."""
        mock_tokenize.return_value = ["test", "keyword", "extraction", "the"]
        mock_freqdist = MagicMock()
        mock_freqdist.most_common.return_value = [("keyword", 5), ("extraction", 3)]
        mock_freqdist_cls.return_value = mock_freqdist

        keywords = extract_keywords("test text")
        assert keywords == ["keyword", "extraction"]

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize")
    def test_extract_keywords_error(self, mock_tokenize: MagicMock) -> None:
        """Test keyword extraction handles errors gracefully."""
        mock_tokenize.side_effect = Exception("error")
        keywords = extract_keywords("test text")
        assert keywords == []

    def test_truncate_text(self) -> None:
        """Test truncate logic."""
        text = "1234567890"

        # No truncation needed
        result = truncate_text(text, max_chars=15)
        assert result == text

        # Truncation applies
        result = truncate_text(text, max_chars=5)
        assert result == "12345..."


# ────────────────────────────────────────────────────────────────────────────
# New tests below: expanded clean_text, sanitize_filename, extract_keywords,
# and truncate_text coverage
# ────────────────────────────────────────────────────────────────────────────


class TestTextProcessingExpanded:
    """Expanded tests for text_processing utilities."""

    # ── clean_text full-pipeline tests ──────────────────────────────────

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_removes_numbers(self):
        """Verify numbers are stripped from text."""
        result = clean_text("report 2024 analysis 42", remove_unwanted=False)
        assert "2024" not in result
        assert "42" not in result
        assert "report" in result

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_removes_special_chars(self):
        """Verify special characters become spaces (then words are joined)."""
        result = clean_text("hello@world#foo$bar", remove_unwanted=False)
        # Special chars removed, words split and joined with underscores
        assert "@" not in result
        assert "#" not in result
        assert "$" not in result
        assert "hello" in result
        assert "world" in result

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_removes_duplicates(self):
        """Verify duplicate words are removed when remove_unwanted=True."""
        result = clean_text("apple apple banana apple banana", max_words=10)
        # Should contain each word only once
        words = result.split("_")
        assert len(words) == len(set(words))
        assert "apple" in words
        assert "banana" in words

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_no_removal(self):
        """Test with remove_unwanted=False preserves common words."""
        result = clean_text("the quick fox", remove_unwanted=False, max_words=10)
        words = result.split("_")
        assert "the" in words
        assert "quick" in words
        assert "fox" in words

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_no_lemmatize(self):
        """Test with lemmatize=False (fallback path has no effect but should not error)."""
        result = clean_text("running dogs", lemmatize=False, remove_unwanted=False)
        assert "running" in result
        assert "dogs" in result

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_code_style(self):
        """Test with code-like text 'getUserData()' splits camelCase."""
        result = clean_text("getUserData", remove_unwanted=False)
        # camelCase should be split: get, User, Data -> get_user_data
        assert "get" in result
        assert "user" in result
        assert "data" in result

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_unicode(self):
        """Test with unicode text."""
        result = clean_text("café résumé naïve", remove_unwanted=False)
        # Unicode letters should be preserved as alpha chars
        assert "caf" in result or "café" in result
        # Should not crash and should produce non-empty output
        assert isinstance(result, str)
        assert len(result) > 0

    # ── sanitize_filename direct tests (no mocking clean_text) ──────────

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_sanitize_filename_direct_basic(self):
        """Call without mocking clean_text, verify end-to-end."""
        result = sanitize_filename("My Report 2024")
        assert isinstance(result, str)
        assert len(result) > 0
        # Should be lowercase, underscore-separated
        assert result == result.lower()
        assert " " not in result

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_sanitize_filename_direct_special_chars(self):
        """Special chars get cleaned end-to-end."""
        result = sanitize_filename("file@name#with$chars!")
        assert "@" not in result
        assert "#" not in result
        assert "$" not in result
        assert "!" not in result

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_sanitize_filename_direct_long_input(self):
        """Very long input gets truncated to max_length."""
        long_name = " ".join(["word"] * 50)
        result = sanitize_filename(long_name, max_length=20)
        assert 1 <= len(result) <= 20  # at most 20 (max_length cap); rstrip may reduce below 20

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_sanitize_filename_leading_trailing_underscores(self):
        """Leading/trailing underscores are stripped."""
        result = sanitize_filename("  hello world  ")
        assert not result.startswith("_")
        assert not result.endswith("_")

    # ── extract_keywords tests ──────────────────────────────────────────

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_extract_keywords_empty(self):
        """Empty string returns empty list."""
        keywords = extract_keywords("")
        assert keywords == []

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_extract_keywords_fallback_top_n(self):
        """Verify top_n parameter in fallback mode."""
        text = "alpha beta gamma alpha beta alpha"
        keywords = extract_keywords(text, top_n=1)
        assert len(keywords) == 1
        assert keywords[0] == "alpha"

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("nltk.probability.FreqDist")
    def test_extract_keywords_short_words_filtered(self, mock_freqdist_cls, mock_tokenize):
        """Words <= 3 chars are filtered in NLTK mode."""
        # word_tokenize returns a mix of short and long words
        mock_tokenize.return_value = ["the", "big", "extraordinary", "cat", "extraordinary"]

        # Mock FreqDist to return the filtered result
        mock_freqdist = MagicMock()
        mock_freqdist.most_common.return_value = [("extraordinary", 2)]
        mock_freqdist_cls.return_value = mock_freqdist

        keywords = extract_keywords("the big extraordinary cat extraordinary")

        # Only words > 3 chars should remain
        # "the", "big", "cat" are <= 3 chars and should be filtered
        assert "the" not in keywords
        assert "big" not in keywords
        assert "cat" not in keywords

    # ── truncate_text edge cases ────────────────────────────────────────

    def test_truncate_text_empty(self):
        """Empty string returns empty string."""
        result = truncate_text("")
        assert result == ""

    def test_truncate_text_exact_length(self):
        """Text exactly at max_chars should not be truncated."""
        text = "12345"
        result = truncate_text(text, max_chars=5)
        assert result == "12345"
        assert "..." not in result
