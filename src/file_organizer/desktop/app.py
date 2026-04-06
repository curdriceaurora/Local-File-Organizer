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
import subprocess
import sys
import threading
import time
from pathlib import Path
from subprocess import SubprocessError as _SubprocessError
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
            logger.debug("browse_directory: create_file_dialog raised an exception", exc_info=True)
            return ""

    def browse_file(
        self,
        file_types: tuple[tuple[str, str], ...] = (),
    ) -> str:
        """Open a native file-picker dialog and return the selected file path.

        Args:
            file_types: Sequence of ``(description, glob_pattern)`` pairs
                forwarded to ``create_file_dialog``.  Example:
                ``(('JSON files (*.json)', '*.json'),)``.  Passing an empty
                tuple shows all files.

        Returns:
            Absolute path to the selected file, or an empty string if the
            user cancelled the dialog or if the dialog raised
            ``OSError``, ``RuntimeError``, or ``ValueError``.  Any other
            unexpected exception is logged and re-raised.
        """
        import webview  # type: ignore[import-untyped]

        try:
            result = webview.active_window().create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=file_types,
            )
            return result[0] if result else ""
        except (OSError, RuntimeError, ValueError):
            logger.debug("browse_file: create_file_dialog raised an exception", exc_info=True)
            return ""
        except Exception:
            logger.exception("browse_file: unexpected exception from create_file_dialog")
            raise

    def save_file(
        self,
        suggested_name: str = "",
        file_types: tuple[tuple[str, str], ...] = (),
    ) -> str:
        r"""Open a native Save-As dialog and return the chosen destination path.

        Args:
            suggested_name: Pre-filled filename in the dialog.  Must not
                contain path separators; any ``/`` or ``\\`` characters are
                stripped before the value is forwarded to the dialog.
            file_types: Sequence of ``(description, glob_pattern)`` pairs.
                Example: ``(('JSON files (*.json)', '*.json'),)``.

        Returns:
            Absolute destination path the user confirmed, or an empty string
            if they cancelled or if the dialog raised ``OSError``,
            ``RuntimeError``, or ``ValueError``.  Any other unexpected
            exception is logged and re-raised.
        """
        import webview  # type: ignore[import-untyped]

        # Strip path separators so the caller cannot accidentally pass a full
        # path and have the dialog silently accept it (F4).
        safe_name = suggested_name.replace("/", "").replace("\\", "")

        try:
            result = webview.active_window().create_file_dialog(
                webview.SAVE_DIALOG,
                save_filename=safe_name,
                file_types=file_types,
            )
            return result[0] if result else ""
        except (OSError, RuntimeError, ValueError):
            logger.debug("save_file: create_file_dialog raised an exception", exc_info=True)
            return ""
        except Exception:
            logger.exception("save_file: unexpected exception from create_file_dialog")
            raise

    def open_path(self, path: str) -> bool:
        """Reveal *path* in the native file manager.

        Opens the platform-appropriate file manager to reveal the item:

        - **macOS**: ``open -R <path>`` reveals the item in Finder.
        - **Windows**: ``explorer /select,<path>`` selects the item in Explorer.
        - **Linux**: ``xdg-open <path>`` opens a directory directly, or
          ``xdg-open <parent>`` for files.

        The subprocess is always invoked without a shell (``shell=False``) so
        the path cannot be interpreted as a shell command regardless of its
        content (F4).

        Args:
            path: Absolute or relative path to reveal.  Resolved via
                :func:`pathlib.Path.resolve` before use.  An empty string
                returns ``False`` immediately without spawning a process.

        Returns:
            ``True`` if the command was dispatched and exited with return code
            zero, ``False`` if *path* is empty, the path resolution or
            subprocess raised, the subprocess returned a non-zero exit code,
            or the platform is not recognised.
        """
        if not path:
            return False

        try:
            resolved = str(Path(path).resolve())
            if sys.platform == "darwin":
                proc = subprocess.run(
                    ["open", "-R", resolved],
                    check=False,
                    timeout=5,
                )
            elif sys.platform == "win32":
                proc = subprocess.run(
                    ["explorer", f"/select,{resolved}"],
                    check=False,
                    timeout=5,
                )
            elif sys.platform.startswith("linux"):
                # Open the directory itself; fall back to parent for files.
                target = resolved if Path(resolved).is_dir() else str(Path(resolved).parent)
                proc = subprocess.run(
                    ["xdg-open", target],
                    check=False,
                    timeout=5,
                )
            else:
                return False
            if proc.returncode != 0:
                logger.debug(
                    "open_path: command failed for path %r with rc=%s",
                    path,
                    proc.returncode,
                )
                return False
        except (OSError, ValueError, RuntimeError, _SubprocessError):
            logger.debug("open_path: subprocess raised for path %r", path, exc_info=True)
            return False

        return True


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
