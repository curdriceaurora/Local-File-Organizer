"""
Shared test fixtures and configuration for the file_organizer test suite.

Provides version-aware fixtures and skip markers for multi-version testing.
Requires Python 3.11+.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.api.realtime import realtime_manager

# ---------------------------------------------------------------------------
# Version-aware fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def python_version() -> tuple[int, int]:
    """Return the current Python (major, minor) version tuple.

    Useful for tests that need to branch logic based on runtime version.
    """
    return sys.version_info[:2]


@pytest.fixture
def python_version_string() -> str:
    """Return a human-readable Python version string like '3.12.1'."""
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


@pytest.fixture
def is_py311_plus() -> bool:
    """True when running on Python 3.11 or later (always True for this project)."""
    return sys.version_info >= (3, 11)


# ---------------------------------------------------------------------------
# Skip markers
# ---------------------------------------------------------------------------

skip_below_py311 = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="Requires Python 3.11+",
)

skip_below_py312 = pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="Requires Python 3.12+",
)


# ---------------------------------------------------------------------------
# Shared test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_realtime_state() -> None:
    """Reset realtime manager state between tests."""
    realtime_manager.reset()
    yield
    realtime_manager.reset()


@pytest.fixture(autouse=True)
def ensure_default_event_loop(request: pytest.FixtureRequest) -> None:
    """Ensure sync tests can instantiate asyncio-bound widgets across Python versions.

    Some Textual widgets allocate ``asyncio.Lock`` during ``__init__``. On Python 3.9,
    after async tests run, the default loop policy can be left with no current loop
    in the main thread, which raises ``RuntimeError`` for later sync widget tests.
    This fixture gives each sync test an explicit default loop; async tests use
    ``pytest-asyncio``/``anyio`` loop management and are skipped here.
    """
    if request.node.get_closest_marker("asyncio") or request.node.get_closest_marker("anyio"):
        yield
        return

    created_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(created_loop)

    yield

    created_loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture
def mock_text_model() -> MagicMock:
    """Create a mock TextModel that returns deterministic responses.

    Returns:
        A MagicMock mimicking the TextModel interface.
    """
    model = MagicMock()
    model.generate.return_value = "Mock AI response for testing."
    model.generate_streaming.return_value = iter(["Mock ", "response."])
    model.is_initialized = True
    model._initialized = True
    model.config = MagicMock()
    model.config.name = "mock-model:test"
    return model


@pytest.fixture
def mock_ollama() -> MagicMock:
    """Create a mock Ollama client.

    Returns:
        A MagicMock mimicking the ollama.Client interface.
    """
    client = MagicMock()
    client.list.return_value = {
        "models": [
            {"name": "qwen2.5:3b-instruct-q4_K_M", "size": "1.9 GB"},
            {"name": "qwen2.5vl:7b-q4_K_M", "size": "6.0 GB"},
        ]
    }
    client.show.return_value = {"name": "test-model"}
    client.generate.return_value = {"response": "Test output", "total_duration": 1_000_000_000}
    return client


@pytest.fixture
def sample_config_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for configuration files.

    Returns:
        Path to the temp config directory.
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_files_dir(tmp_path: Path) -> Path:
    """Create a temporary directory with sample files for testing.

    Returns:
        Path to the temp directory containing sample files.
    """
    d = tmp_path / "samples"
    d.mkdir()
    (d / "document.txt").write_text("Sample document content for testing.")
    (d / "notes.md").write_text("# Notes\n\n- Item 1\n- Item 2\n")
    (d / "data.csv").write_text("col1,col2\nval1,val2\n")
    return d


# ---------------------------------------------------------------------------
# NLTK test fixtures for hermeticity (Issue #470)
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_nltk_tokenizer() -> MagicMock:
    """Create a mock NLTK word_tokenize function.

    Returns a list of tokens that mimics NLTK tokenization behavior.
    """
    tokenizer_mock = MagicMock()

    def tokenize_text(text: str) -> list[str]:
        """Simple tokenizer that splits on whitespace and punctuation."""
        import re

        # Simple regex-based tokenization
        tokens = re.findall(r"\b\w+\b", text.lower())
        return tokens

    tokenizer_mock.side_effect = tokenize_text
    return tokenizer_mock


@pytest.fixture
def mock_nltk_stopwords() -> MagicMock:
    """Create a mock NLTK stopwords corpus.

    Returns a mock that provides English stopwords without requiring downloads.
    """
    stopwords_mock = MagicMock()

    # Minimal English stopwords set
    english_stopwords = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "he",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "to",
        "was",
        "will",
        "with",
        "i",
        "you",
        "we",
        "they",
        "she",
        "him",
        "her",
        "me",
        "us",
        "can",
        "could",
        "would",
        "should",
        "do",
        "does",
        "did",
        "have",
        "having",
        "not",
        "no",
        "nor",
        "so",
        "than",
        "too",
        "very",
        "just",
        "own",
        "same",
    }

    def get_stopwords(language: str = "english") -> set[str]:
        """Return a minimal set of stopwords."""
        if language == "english":
            return english_stopwords
        return set()

    stopwords_mock.words.side_effect = get_stopwords
    return stopwords_mock


@pytest.fixture
def mock_nltk_lemmatizer() -> MagicMock:
    """Create a mock NLTK WordNetLemmatizer.

    Returns a mock lemmatizer that performs basic lemmatization.
    """
    lemmatizer_class = MagicMock()
    lemmatizer_instance = MagicMock()

    def lemmatize(word: str, pos: str = "n") -> str:
        """Simple lemmatization - just return the word."""
        # In real lemmatization, this would transform words to their base form
        # For testing, we just return the word as-is
        return word.lower()

    lemmatizer_instance.lemmatize.side_effect = lemmatize
    lemmatizer_class.return_value = lemmatizer_instance
    return lemmatizer_class


@pytest.fixture
def mock_nltk_freqdist() -> MagicMock:
    """Create a mock NLTK FreqDist class.

    Returns a mock frequency distribution that supports most_common().
    """
    freqdist_class = MagicMock()

    def create_freq_dist(words: list[str]) -> MagicMock:
        """Create a mock FreqDist instance."""
        from collections import Counter

        freq_dist_instance = MagicMock()
        word_counts = Counter(words)

        def most_common(n: int | None = None) -> list[tuple[str, int]]:
            """Return the most common words."""
            return word_counts.most_common(n)

        freq_dist_instance.most_common.side_effect = most_common
        return freq_dist_instance

    freqdist_class.side_effect = create_freq_dist
    return freqdist_class


@pytest.fixture
def mock_nltk_ensure_data_no_op() -> None:
    """Fixture that ensures ensure_nltk_data() doesn't create directories.

    When used, mocks ensure_nltk_data() to be a no-op, preventing any
    filesystem operations during test setup.

    Usage:
        def test_something(mock_nltk_ensure_data_no_op):
            # ensure_nltk_data() is mocked as a no-op
            ...
    """
    from unittest.mock import patch

    with patch("file_organizer.utils.text_processing.ensure_nltk_data"):
        yield


@pytest.fixture
def isolated_nltk_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fixture that simulates a clean container without NLTK corpus.

    Sets NLTK_AVAILABLE to False to test fallback behavior in isolated
    environments where NLTK data is not pre-installed.

    Usage:
        def test_something_without_nltk(isolated_nltk_environment):
            # Tests run as if NLTK is not available
            ...
    """
    # Mock NLTK_AVAILABLE as False
    monkeypatch.setattr("file_organizer.utils.text_processing.NLTK_AVAILABLE", False)


# ---------------------------------------------------------------------------
# Database fixtures for API tests
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> MagicMock:
    """Create a mock database session for API tests.

    Used for dependency injection in tests that require a database session
    but don't need a real database connection.

    Returns:
        A MagicMock session object suitable for API testing.
    """
    from sqlalchemy.orm import Session

    session = MagicMock(spec=Session)
    return session


# ---------------------------------------------------------------------------
# Web route test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def web_client_builder(tmp_path: Path):
    """Factory fixture for creating web test clients with customizable settings.

    Centralizes _build_client logic to avoid duplication across test files.

    Returns:
        A callable that creates TestClient instances with specified options.
    """
    from fastapi.testclient import TestClient

    from file_organizer.api.main import create_app
    from file_organizer.api.test_utils import build_test_settings

    def _build(allowed_paths: list[str] | None = None, auth_enabled: bool = False) -> TestClient:
        """Build a test client with the specified settings.

        Args:
            allowed_paths: List of allowed directory paths. Defaults to [str(tmp_path)].
            auth_enabled: Whether authentication is enabled. Defaults to False.

        Returns:
            A FastAPI TestClient for the app.
        """
        if allowed_paths is None:
            allowed_paths = [str(tmp_path)]
        settings = build_test_settings(
            tmp_path,
            allowed_paths=allowed_paths,
            auth_overrides={"auth_enabled": auth_enabled},
        )
        app = create_app(settings)
        return TestClient(app)

    return _build


@pytest.fixture
def mock_marketplace_service() -> MagicMock:
    """Create marketplace service mock with deterministic test behavior.

    Provides mocked responses for marketplace operations without requiring
    actual marketplace service dependencies.

    Returns:
        A MagicMock configured for marketplace service operations.
    """
    mock_instance = MagicMock()
    mock_instance.list_plugins.return_value = ([], 0)
    mock_instance.list_installed.return_value = []
    return mock_instance
