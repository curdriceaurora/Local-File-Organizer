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
    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_ensure_nltk_data_unavailable(self):
        # Should return early without error
        ensure_nltk_data()

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.nltk.download")
    @patch("file_organizer.utils.text_processing.stopwords.words")
    @patch("file_organizer.utils.text_processing.word_tokenize")
    @patch("nltk.corpus.wordnet.synsets")
    def test_ensure_nltk_data_available_success(
        self, mock_synsets, mock_tokenize, mock_words, mock_download
    ):
        # No LookUpErrors
        ensure_nltk_data()
        mock_download.assert_not_called()

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.nltk.download")
    def test_ensure_nltk_data_lookup_error_download(self, mock_download):
        from file_organizer.utils.text_processing import stopwords

        with patch.object(stopwords, "words", side_effect=[LookupError("not found"), True]):
            ensure_nltk_data()
            mock_download.assert_called()

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch(
        "file_organizer.utils.text_processing.nltk.download", side_effect=Exception("Network error")
    )
    def test_ensure_nltk_data_download_error(self, mock_download):
        from file_organizer.utils.text_processing import stopwords

        with patch.object(stopwords, "words", side_effect=LookupError("not found")):
            # Should catch exception and not raise
            ensure_nltk_data()

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    def test_ensure_nltk_data_general_error(self):
        from file_organizer.utils.text_processing import stopwords

        with patch.object(stopwords, "words", side_effect=Exception("Some other error")):
            # Should catch exception and not raise
            ensure_nltk_data()

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_get_unwanted_words_no_nltk(self):
        words = get_unwanted_words()
        assert "the" in words
        assert "custom_word" not in words

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    def test_get_unwanted_words_with_nltk(self):
        from file_organizer.utils.text_processing import stopwords

        with patch.object(stopwords, "words", return_value=["teststopword"]):
            words = get_unwanted_words()
            assert "teststopword" in words

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    def test_get_unwanted_words_with_nltk_lookup_error(self):
        from file_organizer.utils.text_processing import stopwords

        with patch.object(stopwords, "words", side_effect=LookupError("Not found")):
            words = get_unwanted_words()
            assert "the" in words

    def test_clean_text_empty(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_clean_text_basic(self):
        result = clean_text("The Quick Brown Fox Jumps Over 123 Lazy Dogs!", max_words=3)
        # Without lemmatization should lowercase and filter unwanted
        # 'the', 'over' are in unwanted
        # Words left: quick, brown, fox, jumps, lazy, dogs
        assert result == "quick_brown_fox"

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize", side_effect=LookupError)
    def test_clean_text_tokenize_fallback(self, mock_tokenize):
        result = clean_text("a camelCase test")
        assert result == "camel_case_test"

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.WordNetLemmatizer")
    def test_clean_text_lemmatize(self, mock_lemmatizer_class):
        mock_lemmatizer = MagicMock()
        mock_lemmatizer.lemmatize.side_effect = lambda x: x + "lem"
        mock_lemmatizer_class.return_value = mock_lemmatizer

        result = clean_text("testing words")
        assert "testinglem" in result or "testlem" in result

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch(
        "file_organizer.utils.text_processing.WordNetLemmatizer", side_effect=Exception("Failed")
    )
    def test_clean_text_lemmatize_error(self, mock_lemmatizer_class):
        result = clean_text("Test error")
        assert "test" in result

    def test_sanitize_filename(self):
        assert sanitize_filename("") == "untitled"
        assert sanitize_filename("Only the") == "untitled"
        assert sanitize_filename("A valid name") == "valid_name"
        assert sanitize_filename("A" * 100, max_length=10) == "a" * 10

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)
    def test_extract_keywords_no_nltk(self):
        result = extract_keywords("apple banana apple cherry")
        assert result == ["apple", "banana", "cherry"] or "apple" in result

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    def test_extract_keywords_with_nltk(self):
        with patch(
            "file_organizer.utils.text_processing.word_tokenize",
            return_value=["apple", "apple", "banana", "the"],
        ):
            from file_organizer.utils.text_processing import stopwords

            with patch.object(stopwords, "words", return_value=["the"]):
                result = extract_keywords("dummy text", top_n=2)
                assert "apple" in result

    @patch("file_organizer.utils.text_processing.NLTK_AVAILABLE", True)
    @patch("file_organizer.utils.text_processing.word_tokenize", side_effect=Exception("Error"))
    def test_extract_keywords_error(self, mock_tokenize):
        assert (
            extract_keywords(
                "Test",
            )
            == []
        )

    def test_truncate_text(self):
        assert truncate_text("short test", 100) == "short test"
        assert truncate_text("a" * 10, 5) == "aaaaa..."
