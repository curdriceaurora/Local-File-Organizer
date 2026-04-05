"""pywebview desktop launcher for File Organizer.

Starts the FastAPI server on a random available port in a daemon thread, waits
until the server is accepting connections, then opens a native OS window via
pywebview pointing at ``http://localhost:<port>``.

The server thread is a daemon so it is automatically torn down when the
pywebview main loop exits (i.e. when the user closes the window).

Design constraints
------------------
- Port allocation uses ``socket`` to find a free port before handing it to
  uvicorn, avoiding TOCTOU races on busy machines.
- A blocking poll loop (50 ms intervals, 10 s timeout) waits for the HTTP
  server to be ready before creating the webview window; this prevents the
  window from displaying a blank/error page on slow cold starts.
- ``webview.start()`` **must** be called from the main thread (OS requirement
  on macOS and Windows). The server thread is therefore a background daemon.
"""

from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TITLE = "File Organizer"


class DesktopAPI:
    """Python methods exposed to the webview JavaScript context via ``js_api``.

    Accessible in the browser as ``window.pywebview.api.<method>()``.
    """

    def browse_directory(self) -> str:
        """Open a native folder-picker dialog and return the selected path.

        Returns:
            Absolute path to the selected folder, or an empty string if the
            user cancelled the dialog or if the dialog could not be opened.
        """
        import webview  # type: ignore[import-untyped]

        try:
            result = webview.active_window().create_file_dialog(webview.FOLDER_DIALOG)
            return result[0] if result else ""
        except Exception:
            logger.debug("browse_directory: create_file_dialog raised an exception")
            return ""


_DEFAULT_WIDTH = 1280
_DEFAULT_HEIGHT = 800
_READY_POLL_INTERVAL = 0.05  # seconds
_READY_TIMEOUT = 10.0  # seconds


def _find_free_port() -> int:
    """Return an ephemeral port that is free at the time of the call."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(port: int, timeout: float = _READY_TIMEOUT) -> bool:
    """Poll until the server is accepting TCP connections or timeout expires.

    Args:
        port: Local port to poll.
        timeout: Maximum seconds to wait before giving up.

    Returns:
        ``True`` if the server became ready within *timeout* seconds, ``False``
        otherwise.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return True
        except OSError:
            time.sleep(_READY_POLL_INTERVAL)
    return False


def _run_server(port: int, **uvicorn_kwargs: Any) -> None:
    """Start uvicorn with the File Organizer FastAPI app.

    Intended to be run in a daemon thread.

    Args:
        port: Port to bind uvicorn to.
        **uvicorn_kwargs: Additional keyword arguments forwarded to
            ``uvicorn.run``.
    """
    import uvicorn

    from file_organizer.api.main import create_app

    app = create_app()
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        **uvicorn_kwargs,
    )


def launch(
    *,
    title: str = _DEFAULT_TITLE,
    width: int = _DEFAULT_WIDTH,
    height: int = _DEFAULT_HEIGHT,
) -> None:
    """Launch the desktop application.

    Creates a free port, starts the FastAPI server in a daemon thread, waits
    for readiness, then opens a pywebview native window.  Blocks until the
    user closes the window.

    Args:
        title: Window title bar text.
        width: Initial window width in logical pixels.
        height: Initial window height in logical pixels.

    Raises:
        RuntimeError: If the server does not become ready within
            ``_READY_TIMEOUT`` seconds.
        ImportError: If ``pywebview`` is not installed.  Install it with
            ``pip install 'file-organizer[desktop]'``.
    """
    try:
        import webview  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "pywebview is required for the desktop UI. "
            "Install it with: pip install 'file-organizer[desktop]'"
        ) from exc

    port = _find_free_port()
    url = f"http://127.0.0.1:{port}"

    logger.info("Starting File Organizer server on %s", url)

    server_thread = threading.Thread(
        target=_run_server,
        args=(port,),
        daemon=True,
        name="fo-server",
    )
    server_thread.start()

    if not _wait_for_server(port):
        raise RuntimeError(f"File Organizer server did not become ready within {_READY_TIMEOUT}s")

    logger.info("Server ready — opening window")

    api = DesktopAPI()
    window = webview.create_window(
        title,
        url,
        width=width,
        height=height,
        resizable=True,
        min_size=(800, 600),
        js_api=api,
    )
    # webview.start() blocks until the window is closed; MUST run on main thread.
    webview.start(debug=False)
    logger.info("Window closed — exiting")
    _ = window  # suppress "window created but never used" linters
