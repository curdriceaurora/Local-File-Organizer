"""Fixtures for text-processing tests.

WP-4.4 (#1234): text processing no longer depends on NLTK or any downloadable
corpus — stopwords are vendored in-module and stemming uses the pure-Python
``snowballstemmer`` package. The previous autouse ``mock_nltk_globally`` fixture
(which patched ``word_tokenize`` / ``stopwords`` / ``WordNetLemmatizer`` /
``nltk.probability.FreqDist`` onto the module) is therefore obsolete: those symbols
no longer exist, and the module is deterministic and offline by construction, so no
mocking is required.

This module intentionally registers no NLTK-related fixtures.
"""

from __future__ import annotations
