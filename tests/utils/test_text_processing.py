"""Tests for text_processing.py."""

from unittest.mock import MagicMock, patch

from file_organizer.utils.text_processing import (
    clean_text,
    ensure_nltk_data,
    extract_keywords,
    get_unwanted_words,
    sanitize_filename,
    truncate_text,
)


class TestTextProcessing:
    """Test text processing utilities."""

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    @patch("file_organizer.utils.text_processing.logger")
    def test_ensure_nltk_data_unavailable(self, mock_logger):
        """Test ensure_nltk_data when NLTK is not available."""
        ensure_nltk_data()
        mock_logger.warning.assert_called_with("NLTK not available, text processing will be limited")

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.nltk.download")
    @patch("file_organizer.utils.text_processing.stopwords")
    @patch("file_organizer.utils.text_processing.word_tokenize")
    def test_ensure_nltk_data_available(self, mock_tokenize, mock_stopwords, mock_download):
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

            assert mock_download.call_count == 3
            mock_download.assert_any_call("stopwords", quiet=True)
            mock_download.assert_any_call("punkt", quiet=True)
            mock_download.assert_any_call("wordnet", quiet=True)

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.stopwords")
    def test_get_unwanted_words_with_nltk(self, mock_stopwords):
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

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_get_unwanted_words_without_nltk(self):
        """Test getting unwanted words without NLTK stopwords."""
        unwanted = get_unwanted_words()
        assert "the" in unwanted
        assert "generated" in unwanted

    def test_clean_text_empty(self):
        """Test clean_text with empty input."""
        assert clean_text("") == ""
        assert clean_text(None) == ""

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_basic_without_nltk(self):
        """Test clean_text fallback without NLTK."""
        text = "Hello World! This is a test 123."
        # "this", "is", "a" should be filtered out.
        # "123" and "!" should be removed.
        result = clean_text(text)
        assert result == "hello_world_test"

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_max_words(self):
        """Test clean_text respects max_words."""
        text = "apple banana orange grape pear kiwi"
        result = clean_text(text, max_words=3, remove_unwanted=False)
        assert result == "apple_banana_orange"

    def test_clean_text_camel_case(self):
        """Test clean_text splits camelCase correctly."""
        with patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False):
            result = clean_text("camelCaseFileName", remove_unwanted=False)
            assert result == "camel_case_file_name"

    def test_sanitize_filename_basic(self):
        """Test simple filename sanitization."""
        with patch("file_organizer.utils.text_processing.clean_text") as mock_clean:
            mock_clean.return_value = "clean_file_name"
            result = sanitize_filename("Some Name")
            assert result == "clean_file_name"

    def test_sanitize_filename_empty_cleanup(self):
        """Test sanitize_filename falls back to untitled."""
        with patch("file_organizer.utils.text_processing.clean_text") as mock_clean:
            mock_clean.return_value = ""
            assert sanitize_filename("") == "untitled"

    def test_sanitize_filename_max_length(self):
        """Test sanitize_filename truncates to max_length."""
        with patch("file_organizer.utils.text_processing.clean_text") as mock_clean:
            mock_clean.return_value = "a" * 100
            result = sanitize_filename("long string", max_length=10)
            assert len(result) == 10
            assert result == "a" * 10

    def test_sanitize_filename_special_chars(self):
        """Test sanitize_filename replaces unhandled special characters."""
        with patch("file_organizer.utils.text_processing.clean_text") as mock_clean:
            mock_clean.return_value = "file@name#with$chars"
            result = sanitize_filename("raw name")
            assert result == "file_name_with_chars"

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_extract_keywords_fallback(self):
        """Test keyword extraction fallback block when missing NLTK."""
        text = "apple banana apple orange apple banana pear"
        keywords = extract_keywords(text, top_n=2)
        assert len(keywords) == 2
        assert "apple" in keywords
        assert "banana" in keywords

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("file_organizer.utils.text_processing.nltk.probability.FreqDist", create=True)
    def test_extract_keywords_nltk(self, mock_freqdist_cls, mock_tokenize):
        """Test keyword extraction with NLTK."""
        mock_tokenize.return_value = ["test", "keyword", "extraction", "the"]
        mock_freqdist = MagicMock()
        mock_freqdist.most_common.return_value = [("keyword", 5), ("extraction", 3)]
        mock_freqdist_cls.return_value = mock_freqdist

        keywords = extract_keywords("test text")
        assert keywords == ["keyword", "extraction"]

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize")
    def test_extract_keywords_error(self, mock_tokenize):
        """Test keyword extraction handles errors gracefully."""
        mock_tokenize.side_effect = Exception("error")
        keywords = extract_keywords("test text")
        assert keywords == []

    def test_truncate_text(self):
        """Test truncate logic."""
        text = "1234567890"

        # No truncation needed
        result = truncate_text(text, max_chars=15)
        assert result == text

        # Truncation applies
        result = truncate_text(text, max_chars=5)
        assert result == "12345..."
