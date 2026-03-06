"""Tests for daemon signal handler deadlock fix (self-pipe pattern) and coverage gaps."""

from __future__ import annotations

import os
import signal
import threading
import time
from pathlib import Path

import pytest

from file_organizer.daemon.config import DaemonConfig
from file_organizer.daemon.service import DaemonService

from .conftest import wired_pipe

pytestmark = pytest.mark.unit


def _make_config(**kwargs) -> DaemonConfig:
    defaults = {
        "watch_directories": [],
        "output_directory": Path("tmp/organized"),
        "pid_file": None,
        "poll_interval": 0.05,
    }
    defaults.update(kwargs)
    return DaemonConfig(**defaults)


# ---------------------------------------------------------------------------
# Self-pipe signal handler tests
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestSignalHandlerWritesToPipe:
    """TestSignalHandlerWritesToPipe test suite."""
    def test_signal_handler_writes_byte_to_pipe(self) -> None:
        """Verify signal handler writes a byte to the wakeup pipe."""
        daemon = DaemonService(_make_config())
        with wired_pipe(daemon) as (r, _w):
            daemon._handle_signal(signal.SIGTERM, None)
            data = os.read(r, 1024)
            assert data == b"\x00"

    def test_signal_handler_tolerates_closed_pipe(self) -> None:
        """Verify signal handler gracefully handles a closed write pipe."""
        daemon = DaemonService(_make_config())
        _r, w = os.pipe()
        os.close(_r)
        os.close(w)
        daemon._sig_wakeup_w = w

        # Should not raise — OSError is caught internally
        daemon._handle_signal(signal.SIGTERM, None)

    def test_signal_handler_tolerates_none_pipe(self) -> None:
        """Verify signal handler works correctly when no pipe is initialized."""
        daemon = DaemonService(_make_config())
        assert daemon._sig_wakeup_w is None
        # Should not raise when pipe is None
        daemon._handle_signal(signal.SIGTERM, None)


@pytest.mark.ci
class TestRunLoopExitsOnPipeSignal:
    """TestRunLoopExitsOnPipeSignal test suite."""
    def test_run_loop_exits_on_pipe_signal(self) -> None:
        """Verify run loop exits when signal is written to pipe."""
        daemon = DaemonService(_make_config())
        with wired_pipe(daemon) as (_r, w):
            # Write a byte to simulate a signal arrival
            os.write(w, b"\x00")
            daemon._run_loop()
            assert daemon._stop_event.is_set()

    def test_run_loop_falls_back_to_event_wait(self) -> None:
        """Verify run loop falls back to event.wait when no pipe available.

        This tests the Windows-compatibility path where select() is not available
        and the loop waits on the stop event directly.
        """
        daemon = DaemonService(_make_config())
        assert daemon._sig_wakeup_r is None  # No pipe

        # Set stop event after a short delay
        def stop_later() -> None:
            """Set stop event after a delay."""
            time.sleep(0.05)
            daemon._stop_event.set()

        t = threading.Thread(target=stop_later)
        t.start()
        daemon._run_loop()
        t.join(timeout=2.0)
        assert daemon._stop_event.is_set()


class TestPipeClosedOnRestore:
    """TestPipeClosedOnRestore test suite."""
    def test_pipe_closed_on_restore(self) -> None:
        """Verify pipes are properly closed when signal handlers are restored."""
        daemon = DaemonService(_make_config())

        # Call from main thread so it doesn't skip
        daemon._install_signal_handlers()

        # Verify pipe was created
        assert daemon._sig_wakeup_r is not None
        assert daemon._sig_wakeup_w is not None
        r_fd = daemon._sig_wakeup_r
        w_fd = daemon._sig_wakeup_w

        daemon._restore_signal_handlers()

        # Verify pipe fds are cleared
        assert daemon._sig_wakeup_r is None
        assert daemon._sig_wakeup_w is None

        # Verify fds are actually closed (os.fstat should fail)
        with pytest.raises(OSError):
            os.fstat(r_fd)
        with pytest.raises(OSError):
            os.fstat(w_fd)


# ---------------------------------------------------------------------------
# Coverage gap tests (lines 215, 301-304, 316-320)
# ---------------------------------------------------------------------------


class TestInstallSignalHandlersMainThread:
    """TestInstallSignalHandlersMainThread test suite."""
    def test_install_signal_handlers_success_main_thread(self):
        """Cover lines 301-304: signal handler installation in main thread."""
        daemon = DaemonService(_make_config())

        try:
            daemon._install_signal_handlers()
            assert daemon._original_sigterm is not None
            assert daemon._original_sigint is not None
            assert daemon._sig_wakeup_r is not None
            assert daemon._sig_wakeup_w is not None
        finally:
            daemon._restore_signal_handlers()


class TestRestoreSignalHandlersMainThread:
    """TestRestoreSignalHandlersMainThread test suite."""
    def test_restore_signal_handlers_success_main_thread(self):
        """Cover lines 316-320: signal handler restoration in main thread."""
        daemon = DaemonService(_make_config())

        # Set up state as if handlers were installed
        r, w = os.pipe()
        daemon._original_sigterm = signal.SIG_DFL
        daemon._original_sigint = signal.SIG_DFL
        daemon._sig_wakeup_r = r
        daemon._sig_wakeup_w = w

        daemon._restore_signal_handlers()

        assert daemon._original_sigterm is None
        assert daemon._original_sigint is None
        assert daemon._sig_wakeup_r is None
        assert daemon._sig_wakeup_w is None
