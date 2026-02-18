"""
Shared test fixtures and configuration for the file_organizer test suite.

Provides version-aware fixtures and skip markers for multi-version testing.
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
def is_py39() -> bool:
    """True when running on Python 3.9."""
    return sys.version_info[:2] == (3, 9)


@pytest.fixture
def is_py310_plus() -> bool:
    """True when running on Python 3.10 or later."""
    return sys.version_info >= (3, 10)


@pytest.fixture
def is_py311_plus() -> bool:
    """True when running on Python 3.11 or later."""
    return sys.version_info >= (3, 11)


# ---------------------------------------------------------------------------
# Skip markers
# ---------------------------------------------------------------------------

skip_below_py310 = pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason="Requires Python 3.10+",
)

skip_below_py311 = pytest.mark.skipif(
    sys.version_info < (3, 11),
    reason="Requires Python 3.11+",
)

skip_below_py312 = pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="Requires Python 3.12+",
)

skip_on_py39 = pytest.mark.skipif(
    sys.version_info[:2] == (3, 9),
    reason="Not applicable on Python 3.9",
)

requires_py39 = pytest.mark.skipif(
    sys.version_info[:2] != (3, 9),
    reason="Only runs on Python 3.9",
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
