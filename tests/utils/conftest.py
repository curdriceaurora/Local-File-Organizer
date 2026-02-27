"""NLTK-specific fixtures for text processing tests.

Ensures test hermeticity by providing comprehensive NLTK mocks that work
in isolated environments without pre-installed NLTK corpus data.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def mock_nltk_globally(
    mock_nltk_tokenizer: MagicMock,
    mock_nltk_stopwords: MagicMock,
    mock_nltk_lemmatizer: MagicMock,
    mock_nltk_freqdist: MagicMock,
) -> None:
    """Automatically mock all NLTK components for text processing tests.

    This fixture patches NLTK imports at module level to ensure tests work
    in clean containers without host NLTK corpus data.
    """
    with patch('file_organizer.utils.text_processing.word_tokenize', mock_nltk_tokenizer), \
         patch('file_organizer.utils.text_processing.stopwords', mock_nltk_stopwords), \
         patch('file_organizer.utils.text_processing.WordNetLemmatizer', mock_nltk_lemmatizer), \
         patch('file_organizer.utils.text_processing.nltk.probability.FreqDist', mock_nltk_freqdist):
        yield
