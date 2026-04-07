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

import os
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

try:
    from playwright.sync_api import Page
except ImportError as exc:
    raise ImportError(
        "Playwright is required to run the desktop E2E tests. "
        "Install it with: pip install playwright && playwright install chromium"
    ) from exc

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
def playwright_config_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped isolated config dir for the Playwright live server.

    Returned so tests that need to reset ``setup_completed`` (e.g.
    ``test_home_redirect``) can delete or rewrite ``config.yaml`` directly.
    """
    return tmp_path_factory.mktemp("playwright_config")


@pytest.fixture(scope="session")
def live_server_url(
    tmp_path_factory: pytest.TempPathFactory,
    playwright_config_dir: Path,
) -> Iterator[str]:
    """Start the FastAPI server once for the whole test session.

    Uses an in-process uvicorn server bound to a random free port on
    localhost.  ``auth_enabled=False`` removes the login gate so tests
    can reach protected pages without credentials.

    Isolation: Monkeypatches ``file_organizer.config.manager.DEFAULT_CONFIG_DIR``
    and sets ``XDG_CONFIG_HOME`` so any ``ConfigManager()`` instantiated by
    route handlers reads from a session-scoped tmp dir instead of the
    developer's or CI runner's real ``~/.config/file-organizer``. Without
    this, tests pollute the host config and pollute each other (e.g.
    ``test_setup_wizard_flow`` flips ``setup_completed=True``, breaking
    ``test_home_redirect`` under randomized order).

    Yields:
        Base URL string, e.g. ``"http://127.0.0.1:54321"``.

    Raises:
        RuntimeError: If the server does not become ready within 20 seconds.
            The error message includes the daemon thread's exception (if any)
            to aid debugging.
    """
    # Redirect config lookups BEFORE importing the API modules so any
    # module-level ``DEFAULT_CONFIG_DIR = get_config_dir()`` capture lands on
    # the tmp dir. ``platformdirs.user_config_dir(APP_NAME)`` honours
    # ``XDG_CONFIG_HOME`` on macOS/Linux.
    orig_xdg = os.environ.get("XDG_CONFIG_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(playwright_config_dir)

    import file_organizer.config.manager as _config_manager

    orig_default_config_dir = _config_manager.DEFAULT_CONFIG_DIR
    # APP_NAME subdir mirrors what ``get_config_dir()`` would have produced.
    _config_manager.DEFAULT_CONFIG_DIR = playwright_config_dir / "file-organizer"

    thread: threading.Thread | None = None
    server = None
    try:
        _config_manager.DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)

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
            cause = _server_error[0] if _server_error else None
            raise RuntimeError(
                f"Playwright live server did not become ready on port {port} within 20 s"
                + (f" — server thread raised: {cause!r}" if cause else "")
            ) from cause

        yield f"http://127.0.0.1:{port}"
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=5.0)
            if thread.is_alive():
                # Non-fatal: daemon thread will be killed at process exit anyway.
                import warnings

                warnings.warn(
                    "Playwright live server thread did not stop within 5 s after shutdown signal.",
                    stacklevel=1,
                )

        # Restore module-level config dir + XDG env var so other test sessions
        # in the same process (or pytest re-runs) don't see the tmp value.
        _config_manager.DEFAULT_CONFIG_DIR = orig_default_config_dir
        if orig_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = orig_xdg


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


# ---------------------------------------------------------------------------
# pywebview mock fixture
# ---------------------------------------------------------------------------

_PYWEBVIEW_MOCK_SCRIPT = """
window.__mockPyw = {
  browse_directory_result: "/mock/dir",
  browse_file_result:      "/mock/file.json",
  save_file_result:        "/mock/save/dest.json",
  open_path_result:        true,
  open_path_calls:         [],
};
window.pywebview = {
  api: {
    browse_directory: function()     { return Promise.resolve(window.__mockPyw.browse_directory_result || ""); },
    browse_file:      function(ft)   { return Promise.resolve(window.__mockPyw.browse_file_result || ""); },
    save_file:        function(n,ft) { return Promise.resolve(window.__mockPyw.save_file_result || ""); },
    open_path:        function(p)    {
      window.__mockPyw.open_path_calls.push(p);
      return Promise.resolve(window.__mockPyw.open_path_result !== undefined ? window.__mockPyw.open_path_result : true);
    },
  }
};
"""


class PywebviewMockHandle:
    """Helpers for mutating the injected pywebview mock state from Python tests.

    All methods use ``page.evaluate()`` to read/write ``window.__mockPyw``
    in the browser context.
    """

    def __init__(self, page: Page) -> None:  # type: ignore[name-defined]
        """Store a reference to the Playwright page.

        Args:
            page: The Playwright ``Page`` object whose JS context hosts the mock.
        """
        self._page = page

    def set_browse_directory_result(self, path: str) -> None:
        """Override the path returned by ``browse_directory()``.

        Args:
            path: Absolute path string the mock should resolve to.
        """
        self._page.evaluate(f"() => {{ window.__mockPyw.browse_directory_result = {path!r}; }}")

    def set_browse_file_result(self, path: str) -> None:
        """Override the path returned by ``browse_file()``.

        Args:
            path: Absolute file path string the mock should resolve to.
        """
        self._page.evaluate(f"() => {{ window.__mockPyw.browse_file_result = {path!r}; }}")

    def set_save_file_result(self, path: str) -> None:
        """Override the path returned by ``save_file()``.

        Args:
            path: Absolute file path string the mock should resolve to.
        """
        self._page.evaluate(f"() => {{ window.__mockPyw.save_file_result = {path!r}; }}")

    def set_open_path_result(self, value: bool) -> None:
        """Override the bool returned by ``open_path()``.

        Args:
            value: ``True`` to simulate success, ``False`` to simulate failure.
        """
        js_value = "true" if value else "false"
        self._page.evaluate(f"() => {{ window.__mockPyw.open_path_result = {js_value}; }}")

    def get_open_path_calls(self) -> list[str]:
        """Return the list of paths that ``open_path()`` was called with.

        Returns:
            Ordered list of path strings passed to ``open_path()`` since the
            mock was last reset (i.e. since page navigation).
        """
        result: list[str] = self._page.evaluate("() => window.__mockPyw.open_path_calls || []")
        return result


@pytest.fixture
def pywebview_mock(page: Page) -> PywebviewMockHandle:  # type: ignore[name-defined]
    """Inject a controllable ``window.pywebview.api`` mock into the page.

    Uses ``page.add_init_script()`` so the mock is available before any
    navigation.  After the fixture is applied, desktop_api.js will detect
    ``window.pywebview`` and set ``document.body.dataset.desktopApp = "1"``,
    enabling ``[data-desktop-only]`` elements.

    Returns:
        A :class:`PywebviewMockHandle` with helpers to read and override
        mock return values and call records.
    """
    page.add_init_script(_PYWEBVIEW_MOCK_SCRIPT)
    return PywebviewMockHandle(page)
