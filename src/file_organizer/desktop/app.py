"""pywebview desktop launcher for File Organizer.

Starts the FastAPI server on a random available port in a daemon thread, waits
until the server is accepting connections, then opens a native OS window via
pywebview pointing at ``http://localhost:<port>``.

The server thread is a daemon so it is automatically torn down when the
pywebview main loop exits (i.e. when the user closes the window).

Design constraints
------------------
- Port allocation binds an ephemeral port and hands uvicorn the **still-open**
  socket. Binding, reading the port and then releasing the socket would leave
  a multi-second window -- spanning uvicorn's import and app construction --
  in which another process can take the port; passing the bound socket removes
  that window rather than narrowing it.
- Readiness comes from uvicorn's own ``started`` flag, relayed through a
  ``threading.Event``, not from probing the port. With a pre-bound socket a TCP
  connect succeeds as soon as the socket listens, which is well before the ASGI
  app can serve, so a connect probe would open the window on a blank page.
- ``webview.start()`` **must** be called from the main thread (OS requirement
  on macOS and Windows). The server thread is therefore a background daemon.
"""

from __future__ import annotations

import contextlib
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
                proc = subprocess.run(  # noqa: subprocess-returncode
                    # proc.returncode is checked at the bottom of the enclosing
                    # try body; detector can't follow the cross-branch reference.
                    ["open", "-R", resolved],
                    check=False,
                    timeout=5,
                )
            elif sys.platform == "win32":
                proc = subprocess.run(  # noqa: subprocess-returncode
                    # proc.returncode is checked at the bottom of the enclosing
                    # try body; detector can't follow the cross-branch reference.
                    ["explorer", f"/select,{resolved}"],
                    check=False,
                    timeout=5,
                )
            elif sys.platform.startswith("linux"):
                # Open the directory itself; fall back to parent for files.
                target = resolved if Path(resolved).is_dir() else str(Path(resolved).parent)
                proc = subprocess.run(  # noqa: subprocess-returncode
                    # proc.returncode is checked at the bottom of the enclosing
                    # try body; detector can't follow the cross-branch reference.
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
_SHUTDOWN_TIMEOUT = 5.0  # seconds to wait for uvicorn to stop


def _bind_free_socket() -> socket.socket:
    """Bind an ephemeral port and return the still-open listening socket.

    The socket is deliberately **not** closed. Binding, reading the port and
    then releasing the socket leaves a window — several seconds wide, spanning
    uvicorn's import and app construction — in which any other process can take
    that port. Handing the bound socket to uvicorn removes the window rather
    than narrowing it.

    Callers own the returned socket and must close it if they do not pass it
    to :func:`_run_server`.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(128)
    return sock


def _wait_for_server(
    ready: threading.Event,
    server_thread: threading.Thread,
    timeout: float = _READY_TIMEOUT,
) -> bool:
    """Wait for uvicorn to report startup complete.

    Waits on an event the server thread sets once uvicorn's own ``started``
    flag flips, rather than probing the port. With a pre-bound socket a TCP
    connect succeeds the instant the socket is listening — the kernel accepts
    into the backlog long before the ASGI app can serve a request — so a
    connect-based probe would report ready while the app was still importing.

    Returns ``False`` promptly if the server thread dies. uvicorn calls
    ``sys.exit()`` on a startup failure, and a ``SystemExit`` raised inside a
    thread is swallowed by ``Thread._bootstrap_inner``; without this check a
    dead thread would still burn the full timeout.

    Args:
        ready: Set by the server thread once uvicorn has started.
        server_thread: The thread running uvicorn, watched for early death.
        timeout: Maximum seconds to wait before giving up.

    Returns:
        ``True`` if the server started within *timeout* seconds.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if ready.wait(timeout=_READY_POLL_INTERVAL):
            return True
        if not server_thread.is_alive():
            return False
    return False


def _run_server(
    sock: socket.socket,
    *,
    ready: threading.Event | None = None,
    server_box: dict[str, Any] | None = None,
    **uvicorn_kwargs: Any,
) -> None:
    """Serve the File Organizer FastAPI app on an already-bound socket.

    Intended to be run in a daemon thread.

    Args:
        sock: Listening socket to serve on. Ownership transfers here.
        ready: Set once uvicorn reports startup complete, so the caller does
            not have to infer readiness from a TCP probe.
        server_box: Optional dict receiving the ``uvicorn.Server`` under key
            ``"server"``, so the caller can request shutdown.
        **uvicorn_kwargs: Additional keyword arguments forwarded to
            ``uvicorn.Config``.
    """
    import asyncio

    import uvicorn

    from file_organizer.api.main import create_app

    async def _serve(server: Any) -> None:
        serve_task = asyncio.ensure_future(server.serve(sockets=[sock]))
        while not server.started and not serve_task.done():
            await asyncio.sleep(_READY_POLL_INTERVAL)
        # Only on a real start. Setting the event unconditionally here would
        # report a failed boot as ready; a failure must instead reach the
        # caller as the thread dying, which `_wait_for_server` watches for.
        if server.started and ready is not None:
            ready.set()
        await serve_task

    try:
        # Inside the guard: `create_app()` builds 15 routers and can raise, as
        # can Config/Server construction. Outside it, such a failure killed the
        # thread with the socket still bound — leaking the port for the life of
        # the process, which is the very failure mode this function exists to
        # make survivable.
        app = create_app()
        config = uvicorn.Config(app, log_level="warning", **uvicorn_kwargs)
        server = uvicorn.Server(config)
        if server_box is not None:
            server_box["server"] = server
        asyncio.run(_serve(server))
    finally:
        with contextlib.suppress(OSError):
            sock.close()


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
    # Install the credential-redacting log filter before any desktop log
    # output (the API server thread also installs it; the call is idempotent).
    from file_organizer.utils.log_redact import install_on_root

    install_on_root()

    try:
        import webview  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError(
            "pywebview is required for the desktop UI. "
            "Install it with: pip install 'file-organizer[desktop]'"
        ) from exc

    sock = _bind_free_socket()
    port = sock.getsockname()[1]
    url = f"http://127.0.0.1:{port}"

    logger.info("Starting File Organizer server on %s", url)

    ready = threading.Event()
    server_box: dict[str, Any] = {}
    server_thread = threading.Thread(
        target=_run_server,
        args=(sock,),
        kwargs={"ready": ready, "server_box": server_box},
        daemon=True,
        name="fo-server",
    )
    server_thread.start()

    if not _wait_for_server(ready, server_thread):
        detail = (
            "the server thread exited during startup"
            if not server_thread.is_alive()
            else f"it did not start within {_READY_TIMEOUT}s"
        )
        raise RuntimeError(f"File Organizer server failed to start: {detail}")

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
    try:
        webview.start(debug=False)
    finally:
        # Ask uvicorn to stop. Without this the daemon thread outlives the
        # window, holding the port and its loguru sink for the life of the
        # process -- which in a test session is the rest of the worker's run.
        server = server_box.get("server")
        if server is not None:
            server.should_exit = True
        server_thread.join(timeout=_SHUTDOWN_TIMEOUT)
    logger.info("Window closed — exiting")
    _ = window  # suppress "window created but never used" linters
