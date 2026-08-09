"""End-to-end integration tests for the desktop launcher.

The unit tests in ``tests/desktop/`` mock ``webview``, the server thread, and
the readiness poll. These instead let :func:`launch` boot the **real**
FastAPI app under uvicorn in a daemon thread on a real ephemeral port, wait
for it via the real readiness loop, and confirm the running server actually
serves HTTP — only ``webview`` (absent in this env) is faked so its
``start()`` performs the connectivity check instead of opening a window.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import types
from pathlib import Path
from typing import Any

import httpx
import pytest

from file_organizer.desktop import app as desktop_app

pytestmark = [pytest.mark.integration, pytest.mark.ci]

skip_on_windows = pytest.mark.skipif(
    sys.platform == "win32", reason="POSIX-only shell shim / signal handling"
)


def _make_fake_webview(on_start: Any) -> types.ModuleType:
    """Build a fake ``webview`` module whose start() runs *on_start*."""
    module = types.ModuleType("webview")
    captured: dict[str, Any] = {}

    def create_window(title: str, url: str, **kwargs: Any) -> object:
        captured["title"] = title
        captured["url"] = url
        captured["kwargs"] = kwargs
        return object()

    def start(**kwargs: Any) -> None:
        on_start(captured)

    module.create_window = create_window  # type: ignore[attr-defined]
    module.start = start  # type: ignore[attr-defined]
    module.captured = captured  # type: ignore[attr-defined]
    module.FOLDER_DIALOG = 1  # type: ignore[attr-defined]
    module.OPEN_DIALOG = 2  # type: ignore[attr-defined]
    module.SAVE_DIALOG = 3  # type: ignore[attr-defined]
    return module


def test_launch_boots_real_server_and_opens_window(monkeypatch: pytest.MonkeyPatch) -> None:
    """launch() starts the real FastAPI/uvicorn daemon and it serves HTTP."""
    probe: dict[str, Any] = {}

    def on_start(captured: dict[str, Any]) -> None:
        # webview.start() runs on the main thread once the server is ready.
        # Confirm the *real* server behind the captured URL answers HTTP.
        resp = httpx.get(captured["url"] + "/", timeout=5.0)
        probe["status"] = resp.status_code
        probe["url"] = captured["url"]

    fake_webview = _make_fake_webview(on_start)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    desktop_app.launch(title="FO Test", width=900, height=700)

    # The window was created pointing at the loopback server, and that server
    # responded over real HTTP.
    assert probe.get("status") == 200
    assert probe["url"].startswith("http://127.0.0.1:")
    assert fake_webview.captured["title"] == "FO Test"  # type: ignore[attr-defined]
    assert fake_webview.captured["kwargs"]["width"] == 900  # type: ignore[attr-defined]


def test_launch_raises_when_server_never_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the server never starts, launch() raises rather than opening a window."""
    fake_webview = _make_fake_webview(lambda captured: None)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    monkeypatch.setattr(desktop_app, "_run_server", lambda sock, **kw: None)
    monkeypatch.setattr(desktop_app, "_wait_for_server", lambda ready, thread, timeout=0.0: False)

    with pytest.raises(RuntimeError, match="failed to start"):
        desktop_app.launch()


def test_bind_free_socket_holds_the_port() -> None:
    """The port must NOT be re-bindable — that is the anti-TOCTOU property.

    The previous helper returned a bare int and released the socket, so the
    port was free for anything else to claim during uvicorn's multi-second
    boot. This asserts the inverse of that old contract.
    """
    sock = desktop_app._bind_free_socket()
    try:
        port = sock.getsockname()[1]
        assert 1024 < port < 65536
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as other:
            with pytest.raises(OSError, match="Address already in use"):
                other.bind(("127.0.0.1", port))
    finally:
        sock.close()


def test_wait_for_server_times_out_when_never_signalled() -> None:
    """Readiness comes from an event, not from a TCP probe."""
    ready = threading.Event()
    stop = threading.Event()
    alive = threading.Thread(target=stop.wait, daemon=True)
    alive.start()

    assert desktop_app._wait_for_server(ready, alive, timeout=0.3) is False


def test_wait_for_server_returns_true_once_signalled() -> None:
    ready = threading.Event()
    stop = threading.Event()
    alive = threading.Thread(target=stop.wait, daemon=True)
    alive.start()
    threading.Timer(0.05, ready.set).start()

    assert desktop_app._wait_for_server(ready, alive, timeout=2.0) is True


def test_wait_for_server_gives_up_immediately_if_the_thread_died() -> None:
    """A dead server must not cost the full timeout before being noticed."""
    ready = threading.Event()  # never set
    dead = threading.Thread(target=lambda: None, daemon=True)
    dead.start()
    dead.join()

    started = time.monotonic()
    assert desktop_app._wait_for_server(ready, dead, timeout=10.0) is False
    assert time.monotonic() - started < 2.0


# ---------------------------------------------------------------------------
# DesktopAPI.open_path — real subprocess against a fake file manager
# ---------------------------------------------------------------------------


@skip_on_windows
def test_open_path_invokes_real_file_manager(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """open_path dispatches a real subprocess and reports success on rc 0."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = bin_dir / "calls.log"
    # Fake both the macOS and Linux file-manager commands so the test is
    # platform-agnostic on POSIX.
    for name in ("xdg-open", "open"):
        shim = bin_dir / name
        shim.write_text(
            f'#!/usr/bin/env bash\nprintf "%s\\n" "$@" >> "{log}"\nexit 0\n',
            encoding="utf-8",
        )
        shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    target = tmp_path / "reveal_me"
    target.mkdir()

    api = desktop_app.DesktopAPI()
    assert api.open_path(str(target)) is True
    assert log.exists() and log.read_text(encoding="utf-8").strip()


def test_open_path_empty_returns_false() -> None:
    """An empty path is rejected before any subprocess is spawned."""
    assert desktop_app.DesktopAPI().open_path("") is False
