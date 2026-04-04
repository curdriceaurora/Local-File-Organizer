"""Playwright E2E test infrastructure.

Fixtures
--------
live_server_url : str  (session-scoped)
    Starts the FastAPI app on a random free port in a daemon thread and
    returns ``http://127.0.0.1:<port>``.  The thread is a daemon so it is
    torn down automatically when the test process exits.

base_url : str  (session-scoped, overrides pytest-playwright default)
    Returns ``live_server_url``, enabling relative paths in ``page.goto()``.
    e.g. ``page.goto("/ui/files")`` resolves to the live server.

Running
-------
Playwright tests are NOT included in the default test run (they require a
real browser and are too slow for the smoke/ci suites).  Run them with::

    # First-time browser installation (once per machine / CI image):
    playwright install chromium

    # Then run the suite:
    pytest tests/playwright/ --browser chromium --override-ini='addopts='

The ``--override-ini='addopts='`` flag strips the project-wide
``--cov`` / ``--cov-fail-under`` options so coverage measurement does not
interfere with browser-process isolation.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    """Return an ephemeral port that is free at call time."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 20.0) -> bool:
    """Block until the port accepts TCP connections or *timeout* expires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            time.sleep(0.1)
    return False


# ---------------------------------------------------------------------------
# Session-scoped live server
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def live_server_url(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Start the FastAPI server once for the whole test session.

    Uses an in-process uvicorn server bound to a random free port on
    localhost.  ``auth_enabled=False`` removes the login gate so tests
    can reach protected pages without credentials.

    Yields:
        Base URL string, e.g. ``"http://127.0.0.1:54321"``.
    """
    import uvicorn

    from file_organizer.api.config import ApiSettings
    from file_organizer.api.main import create_app

    tmp = tmp_path_factory.mktemp("playwright_server")
    settings = ApiSettings(
        allowed_paths=[str(tmp)],
        auth_enabled=False,
        auth_db_path=str(tmp / "auth.db"),
    )
    app = create_app(settings)
    port = _find_free_port()

    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",  # keep test output clean
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True, name="pw-server")
    thread.start()

    if not _wait_for_port(port, timeout=20.0):
        server.should_exit = True
        raise RuntimeError(
            f"Playwright live server did not become ready on port {port} within 20 s"
        )

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True


# ---------------------------------------------------------------------------
# Override pytest-playwright's base_url so relative goto() paths work
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def base_url(live_server_url: str) -> str:  # type: ignore[override]
    """Return the live server URL as the Playwright base URL.

    With this fixture in place tests may call ``page.goto("/ui/files")``
    and Playwright resolves it against the live server automatically.
    """
    return live_server_url
