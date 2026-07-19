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
    """If the server never binds, launch() times out with a RuntimeError."""
    fake_webview = _make_fake_webview(lambda captured: None)
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    # Force readiness to fail fast instead of booting a real server.
    monkeypatch.setattr(desktop_app, "_run_server", lambda port, **kw: None)
    monkeypatch.setattr(desktop_app, "_wait_for_server", lambda port, timeout=0.0: False)

    with pytest.raises(RuntimeError, match="did not become ready"):
        desktop_app.launch()


def test_find_free_port_returns_bindable_port() -> None:
    """_find_free_port returns a port that is actually free to bind."""
    port = desktop_app._find_free_port()
    assert isinstance(port, int)
    assert 1024 < port < 65536
    # It is free right now: we can bind it ourselves.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


def test_wait_for_server_times_out_on_dead_port() -> None:
    """_wait_for_server returns False when nothing is listening."""
    dead_port = desktop_app._find_free_port()  # free => nothing is listening
    assert desktop_app._wait_for_server(dead_port, timeout=0.3) is False


def test_wait_for_server_detects_live_socket() -> None:
    """_wait_for_server returns True once a socket is accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert desktop_app._wait_for_server(port, timeout=2.0) is True


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
