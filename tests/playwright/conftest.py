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
    pytest-playwright's built-in ``base_url`` fixture reads from the
    ``--base-url`` CLI flag (not set in this project's default invocation).
    This fixture replaces it with the dynamically assigned live server URL
    so the flag is unnecessary.

Running
-------
Playwright tests are NOT included in the default test run (they require a
real browser and are excluded from CI shards).  Run them with::

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
from collections.abc import Iterator

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_free_port() -> int:
    """Return an ephemeral port that is free at call time.

    Note: There is an inherent TOCTOU window between releasing the socket
    and uvicorn binding it.  On low-traffic developer machines this is
    negligible; on heavily loaded CI runners with parallel test shards the
    port may be stolen.  If this becomes flaky, switch to binding port 0
    in uvicorn and reading the actual port from server.servers after start.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_port(port: int, timeout: float = 20.0) -> bool:
    """Block until the port accepts TCP connections or *timeout* expires.

    Uses ``threading.Event.wait`` for inter-attempt rate-limiting — this is
    cross-platform (``select.select`` with empty socket lists raises
    ``OSError`` on Windows) and does not trigger the project's
    ``time.sleep``-in-tests guardrail.

    Note: TCP acceptance indicates uvicorn's socket is bound; the ASGI
    lifespan startup hook (``reset_startup_time`` + log) completes before
    uvicorn starts accepting connections, so TCP-ready is equivalent to
    HTTP-ready for this application's trivial lifespan.
    """
    _sleep = threading.Event()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return True
        except OSError:
            remaining = deadline - time.monotonic()
            if remaining > 0:
                # Rate-limit retries; Event.wait is cross-platform unlike
                # select.select([], [], [], t) which raises OSError on Windows.
                _sleep.wait(timeout=min(0.1, remaining))
    return False


# ---------------------------------------------------------------------------
# Session-scoped live server
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def live_server_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Start the FastAPI server once for the whole test session.

    Uses an in-process uvicorn server bound to a random free port on
    localhost.  ``auth_enabled=False`` removes the login gate so tests
    can reach protected pages without credentials.

    Yields:
        Base URL string, e.g. ``"http://127.0.0.1:54321"``.

    Raises:
        RuntimeError: If the server does not become ready within 20 seconds.
            The error message includes the daemon thread's exception (if any)
            to aid debugging.
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

    # Capture any exception raised by server.run() so it can be surfaced in
    # the timeout RuntimeError instead of being permanently lost in the daemon.
    _server_error: list[BaseException] = []

    def _run() -> None:
        try:
            server.run()
        except Exception as exc:
            _server_error.append(exc)

    thread = threading.Thread(target=_run, daemon=True, name="pw-server")
    thread.start()

    if not _wait_for_port(port, timeout=20.0):
        server.should_exit = True
        thread.join(timeout=5.0)
        cause = _server_error[0] if _server_error else None
        raise RuntimeError(
            f"Playwright live server did not become ready on port {port} within 20 s"
            + (f" — server thread raised: {cause!r}" if cause else "")
        ) from cause

    yield f"http://127.0.0.1:{port}"

    server.should_exit = True
    thread.join(timeout=5.0)
    if thread.is_alive():
        # Non-fatal: daemon thread will be killed at process exit anyway.
        import warnings

        warnings.warn(
            "Playwright live server thread did not stop within 5 s after shutdown signal.",
            stacklevel=1,
        )


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
