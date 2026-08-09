"""Smoke tests for file_organizer.desktop.app.

These tests do NOT launch a real browser window or uvicorn server.  They verify
the helper utilities (_find_free_port, _wait_for_server) and the error paths of
launch() without requiring pywebview to be installed.
"""

from __future__ import annotations

import runpy
import socket
import sys
import threading
import time
from unittest.mock import ANY, MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# _find_free_port
# ---------------------------------------------------------------------------


class _FakeSocket:
    """Stands in for a bound listening socket in launch/_run_server tests."""

    def __init__(self, port: int) -> None:
        self._port = port
        self.closed = False

    def getsockname(self) -> tuple[str, int]:
        return ("127.0.0.1", self._port)

    def close(self) -> None:
        self.closed = True


class TestBindFreeSocket:
    def test_returns_a_listening_socket_on_a_valid_port(self) -> None:
        from file_organizer.desktop.app import _bind_free_socket

        sock = _bind_free_socket()
        try:
            port = sock.getsockname()[1]
            assert isinstance(port, int)
            assert 1024 <= port <= 65535
        finally:
            sock.close()

    def test_port_is_held_not_released(self) -> None:
        """The anti-TOCTOU property, and the inverse of the old contract.

        This previously asserted the port was re-bindable immediately after
        the call — which is exactly the race: the helper bound port 0, read
        the number, closed the socket, and uvicorn re-bound seconds later.
        Anything could take it in between. The socket is now held open and
        handed to uvicorn, so a second bind must FAIL.
        """
        from file_organizer.desktop.app import _bind_free_socket

        sock = _bind_free_socket()
        try:
            port = sock.getsockname()[1]
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as other:
                with pytest.raises(OSError, match="Address already in use"):
                    other.bind(("127.0.0.1", port))
        finally:
            sock.close()


class TestWaitForServer:
    def test_returns_true_once_the_server_signals_ready(self) -> None:
        from file_organizer.desktop.app import _wait_for_server

        ready = threading.Event()
        ready.set()
        stop = threading.Event()
        alive = threading.Thread(target=stop.wait, daemon=True)
        alive.start()

        assert _wait_for_server(ready, alive, timeout=2.0) is True

    def test_returns_false_when_the_server_never_signals(self) -> None:
        from file_organizer.desktop.app import _wait_for_server

        ready = threading.Event()  # never set
        stop = threading.Event()
        alive = threading.Thread(target=stop.wait, daemon=True)
        alive.start()

        assert _wait_for_server(ready, alive, timeout=0.15) is False

    def test_returns_false_promptly_when_the_server_thread_dies(self) -> None:
        """uvicorn calls sys.exit() on a bind failure, and a SystemExit raised
        inside a thread is swallowed by ``Thread._bootstrap_inner``. Without
        watching liveness, a dead server would still burn the whole timeout and
        report "did not become ready" rather than "it crashed".
        """
        from file_organizer.desktop.app import _wait_for_server

        ready = threading.Event()  # never set
        dead = threading.Thread(target=lambda: None, daemon=True)
        dead.start()
        dead.join()

        started = time.monotonic()
        assert _wait_for_server(ready, dead, timeout=10.0) is False
        assert time.monotonic() - started < 2.0, "should not wait out the full timeout"


# ---------------------------------------------------------------------------
# _wait_for_server
# ---------------------------------------------------------------------------


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
            with pytest.raises(RuntimeError, match="failed to start"):
                launch()

        _ = sys  # keep import for clarity

    def test_launch_passes_custom_title_width_height(self) -> None:
        """launch() should forward title/width/height to webview.create_window."""
        mock_webview = MagicMock()

        from file_organizer.desktop import app as desktop_app

        with (
            patch.dict(sys.modules, {"webview": mock_webview}),
            patch("file_organizer.desktop.app._wait_for_server", return_value=True),
            patch("file_organizer.desktop.app.threading") as mock_threading,
        ):
            desktop_app.launch(title="My App", width=1024, height=768)

        # launch() must start the server in a background thread.
        assert mock_threading.Thread.call_args.kwargs["target"].__name__ == "_run_server"
        mock_webview.create_window.assert_called_once_with(
            "My App",
            ANY,
            width=1024,
            height=768,
            resizable=True,
            min_size=(800, 600),
            js_api=ANY,
        )

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
            patch("file_organizer.desktop.app.threading") as mock_threading,
        ):
            mock_threading.Thread.return_value = MagicMock()

            desktop_app.launch()

        # launch() must start the server in a background thread.
        assert mock_threading.Thread.call_args.kwargs["target"].__name__ == "_run_server"
        mock_webview.start.assert_called_once()

    def test_native_window_loads_the_shared_web_routes(self) -> None:
        """Desktop points at the same FastAPI Web UI and only injects its native API."""
        mock_webview = MagicMock()

        from file_organizer.desktop import app as desktop_app

        with (
            patch.dict(sys.modules, {"webview": mock_webview}),
            patch(
                "file_organizer.desktop.app._bind_free_socket",
                return_value=_FakeSocket(43123),
            ),
            patch("file_organizer.desktop.app._wait_for_server", return_value=True),
            patch("file_organizer.desktop.app.threading") as mock_threading,
        ):
            desktop_app.launch()

        # launch() must start the server in a background thread.
        assert mock_threading.Thread.call_args.kwargs["target"].__name__ == "_run_server"
        args, kwargs = mock_webview.create_window.call_args
        assert args == ("File Organizer", "http://127.0.0.1:43123")
        assert isinstance(kwargs["js_api"], desktop_app.DesktopAPI)


# ---------------------------------------------------------------------------
# _run_server — exercises lines 76-81 (uvicorn import + create_app + run)
# ---------------------------------------------------------------------------


class TestRunServer:
    """`_run_server` serves on the socket it is handed, and signals readiness."""

    @staticmethod
    def _uvicorn_double() -> tuple[MagicMock, MagicMock]:
        """Return (uvicorn_module, server) doubles wired for one clean serve."""
        server = MagicMock()
        server.started = True

        async def _serve(sockets=None):
            server.serve_sockets = sockets

        server.serve = _serve
        mock_uvicorn = MagicMock()
        mock_uvicorn.Server.return_value = server
        return mock_uvicorn, server

    def test_serves_on_the_socket_it_was_given(self) -> None:
        """The whole point of the change: uvicorn must not re-bind a port."""
        from file_organizer.desktop.app import _run_server

        mock_uvicorn, server = self._uvicorn_double()
        mock_api_main = MagicMock()
        mock_app = MagicMock()
        mock_api_main.create_app.return_value = mock_app
        sock = _FakeSocket(54321)

        with patch.dict(
            sys.modules, {"uvicorn": mock_uvicorn, "file_organizer.api.main": mock_api_main}
        ):
            _run_server(sock)

        assert server.serve_sockets == [sock], "uvicorn was not handed the bound socket"
        mock_uvicorn.Config.assert_called_once_with(mock_app, log_level="warning")
        assert sock.closed, "the socket must be released when serving stops"

    def test_sets_the_ready_event_once_uvicorn_reports_started(self) -> None:
        from file_organizer.desktop.app import _run_server

        mock_uvicorn, _ = self._uvicorn_double()
        mock_api_main = MagicMock()
        mock_api_main.create_app.return_value = MagicMock()
        ready = threading.Event()

        with patch.dict(
            sys.modules, {"uvicorn": mock_uvicorn, "file_organizer.api.main": mock_api_main}
        ):
            _run_server(_FakeSocket(54322), ready=ready)

        assert ready.is_set()

    def test_does_not_signal_ready_when_startup_fails(self) -> None:
        """A crashed boot must not look like a successful one.

        uvicorn exits the process on a bind failure; inside a thread that
        `SystemExit` is swallowed. If `_run_server` set the event regardless,
        `launch()` would open a window onto a server that never started.
        """
        from file_organizer.desktop.app import _run_server

        server = MagicMock()
        server.started = False  # never starts

        async def _serve(sockets=None):
            raise SystemExit(3)

        server.serve = _serve
        mock_uvicorn = MagicMock()
        mock_uvicorn.Server.return_value = server
        mock_api_main = MagicMock()
        mock_api_main.create_app.return_value = MagicMock()
        ready = threading.Event()

        with patch.dict(
            sys.modules, {"uvicorn": mock_uvicorn, "file_organizer.api.main": mock_api_main}
        ):
            with pytest.raises(SystemExit):
                _run_server(_FakeSocket(54323), ready=ready)

        assert not ready.is_set()

    def test_publishes_the_server_so_the_caller_can_stop_it(self) -> None:
        """`launch()` needs a handle to shut uvicorn down when the window closes."""
        from file_organizer.desktop.app import _run_server

        mock_uvicorn, server = self._uvicorn_double()
        mock_api_main = MagicMock()
        mock_api_main.create_app.return_value = MagicMock()
        box: dict[str, object] = {}

        with patch.dict(
            sys.modules, {"uvicorn": mock_uvicorn, "file_organizer.api.main": mock_api_main}
        ):
            _run_server(_FakeSocket(54324), server_box=box)

        assert box["server"] is server

    def test_forwards_extra_kwargs_to_uvicorn_config(self) -> None:
        from file_organizer.desktop.app import _run_server

        mock_uvicorn, _ = self._uvicorn_double()
        mock_api_main = MagicMock()
        mock_app = MagicMock()
        mock_api_main.create_app.return_value = mock_app

        with patch.dict(
            sys.modules, {"uvicorn": mock_uvicorn, "file_organizer.api.main": mock_api_main}
        ):
            _run_server(_FakeSocket(9999), workers=2)

        mock_uvicorn.Config.assert_called_once_with(mock_app, log_level="warning", workers=2)


class TestLaunchShutdown:
    """The window closing must stop the server, not leak the thread."""

    def test_window_close_requests_uvicorn_shutdown(self) -> None:
        """Previously the daemon thread outlived the window.

        It kept the port bound and its loguru sink installed for the life of
        the process — which in a test session is the rest of the worker's run.
        """
        mock_webview = MagicMock()
        fake_server = MagicMock()

        from file_organizer.desktop import app as desktop_app

        def _fake_run_server(sock, *, ready=None, server_box=None, **kw):
            if server_box is not None:
                server_box["server"] = fake_server
            if ready is not None:
                ready.set()

        with (
            patch.dict(sys.modules, {"webview": mock_webview}),
            patch(
                "file_organizer.desktop.app._bind_free_socket",
                return_value=_FakeSocket(43999),
            ),
            patch("file_organizer.desktop.app._run_server", _fake_run_server),
            patch("file_organizer.desktop.app._wait_for_server", return_value=True),
        ):
            desktop_app.launch()

        assert fake_server.should_exit is True


# ---------------------------------------------------------------------------
# __main__ — covers the if __name__ == "__main__" guard in __main__.py
# ---------------------------------------------------------------------------


class TestMainModule:
    def test_main_calls_launch(self) -> None:
        """Running the package as __main__ should call launch()."""
        with patch("file_organizer.desktop.app.launch") as mock_launch:
            runpy.run_module("file_organizer.desktop", run_name="__main__")

        mock_launch.assert_called_once_with()
