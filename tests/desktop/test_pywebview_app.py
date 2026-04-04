"""Smoke tests for file_organizer.desktop.app.

These tests do NOT launch a real browser window or uvicorn server.  They verify
the helper utilities (_find_free_port, _wait_for_server) and the error paths of
launch() without requiring pywebview to be installed.
"""

from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# _find_free_port
# ---------------------------------------------------------------------------


class TestFindFreePort:
    def test_returns_integer(self) -> None:
        from file_organizer.desktop.app import _find_free_port

        port = _find_free_port()
        assert isinstance(port, int)
        assert 1024 <= port <= 65535

    def test_port_in_valid_range(self) -> None:
        from file_organizer.desktop.app import _find_free_port

        port = _find_free_port()
        assert 1024 <= port <= 65535

    def test_port_is_free(self) -> None:
        """The returned port should be bindable immediately after the call."""
        from file_organizer.desktop.app import _find_free_port

        port = _find_free_port()
        # Re-binding to the port should succeed (it is free).
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))  # raises OSError if port in use


# ---------------------------------------------------------------------------
# _wait_for_server
# ---------------------------------------------------------------------------


class TestWaitForServer:
    def test_returns_true_when_port_open(self) -> None:
        from file_organizer.desktop.app import _find_free_port, _wait_for_server

        # Open a real listening socket so _wait_for_server can connect.
        port = _find_free_port()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind(("127.0.0.1", port))
            srv.listen(1)
            assert _wait_for_server(port, timeout=2.0) is True

    def test_returns_false_when_nothing_listening(self) -> None:
        from file_organizer.desktop.app import _find_free_port, _wait_for_server

        port = _find_free_port()
        # Nothing is bound — should time out quickly.
        assert _wait_for_server(port, timeout=0.15) is False


# ---------------------------------------------------------------------------
# launch() — error paths only (no real window opened)
# ---------------------------------------------------------------------------


class TestLaunch:
    def test_raises_import_error_without_pywebview(self) -> None:
        """launch() must raise ImportError with helpful message when pywebview is absent."""
        from file_organizer.desktop.app import launch

        with patch.dict("sys.modules", {"webview": None}):
            with pytest.raises(ImportError, match="pywebview is required"):
                launch()

    def test_raises_runtime_error_when_server_never_starts(self) -> None:
        """launch() must raise RuntimeError if server does not become ready."""
        import sys

        from file_organizer.desktop.app import launch

        mock_webview = MagicMock()
        # Ensure webview import succeeds but server never becomes ready.
        with (
            patch.dict("sys.modules", {"webview": mock_webview}),
            patch("file_organizer.desktop.app._wait_for_server", return_value=False),
            patch("file_organizer.desktop.app._run_server"),
        ):
            with pytest.raises(RuntimeError, match="did not become ready"):
                launch()

        _ = sys  # keep import for clarity

    def test_happy_path_calls_webview_start(self) -> None:
        """launch() must call webview.start() when server is ready."""
        import sys

        mock_webview = MagicMock()

        # Ensure the module is already imported before applying patches so that
        # the module-level references we patch are stable.
        from file_organizer.desktop import app as desktop_app

        with (
            patch.dict(sys.modules, {"webview": mock_webview}),
            patch("file_organizer.desktop.app._wait_for_server", return_value=True),
            patch("file_organizer.desktop.app._run_server"),
            patch("file_organizer.desktop.app.threading") as mock_threading,
        ):
            mock_threading.Thread.return_value = MagicMock()

            desktop_app.launch()

        mock_webview.start.assert_called_once()
