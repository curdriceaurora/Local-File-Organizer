"""Coverage tests for daemon.service module."""

from __future__ import annotations

import signal
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.daemon.config import DaemonConfig
from file_organizer.daemon.service import DaemonService

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def _make_config(**kwargs) -> DaemonConfig:
    defaults = {
        "watch_directories": [],
        "output_directory": Path("tmp/organized"),
        "pid_file": None,
        "poll_interval": 0.05,
    }
    defaults.update(kwargs)
    return DaemonConfig(**defaults)


class TestDaemonServiceInit:
    """TestDaemonServiceInit test suite."""
    def test_initial_state(self):
        """Test initial state."""
        config = _make_config()
        daemon = DaemonService(config)
        assert daemon.is_running is False
        assert daemon.uptime_seconds == 0.0
        assert daemon.files_processed == 0


class TestDaemonServiceStartBackground:
    """TestDaemonServiceStartBackground test suite."""
    def test_start_and_stop(self):
        """Test start and stop."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        try:
            assert daemon.is_running is True
            assert daemon.uptime_seconds > 0
        finally:
            daemon.stop()
        assert daemon.is_running is False

    def test_double_start_raises(self):
        """Test double start raises."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        try:
            with pytest.raises(RuntimeError, match="already running"):
                daemon.start_background()
        finally:
            daemon.stop()

    def test_stop_when_not_running(self):
        """Test stop when not running."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.stop()  # Should not raise


class TestDaemonServiceRestart:
    """TestDaemonServiceRestart test suite."""
    def test_restart(self):
        """Test restart."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        try:
            daemon.restart()
            assert daemon.is_running is True
        finally:
            daemon.stop()

    def test_restart_from_stopped(self):
        """Test restart from stopped."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.restart()
        try:
            assert daemon.is_running is True
        finally:
            daemon.stop()


class TestDaemonServiceCallbacks:
    """TestDaemonServiceCallbacks test suite."""
    def test_on_start_callback(self):
        """Test on start callback."""
        config = _make_config()
        daemon = DaemonService(config)
        start_called = threading.Event()
        daemon.on_start(lambda: start_called.set())
        daemon.start_background()
        try:
            assert start_called.wait(timeout=2.0)
        finally:
            daemon.stop()

    def test_on_stop_callback(self):
        """Test on stop callback."""
        config = _make_config()
        daemon = DaemonService(config)
        stop_called = threading.Event()
        daemon.on_stop(lambda: stop_called.set())
        daemon.start_background()
        daemon.stop()
        assert stop_called.wait(timeout=2.0)

    def test_on_start_callback_exception_does_not_crash(self):
        """Test on start callback exception does not crash."""
        config = _make_config()
        daemon = DaemonService(config)

        def bad_callback():
            """bad_callback."""
            raise RuntimeError("boom")

        daemon.on_start(bad_callback)
        daemon.start_background()
        try:
            assert daemon.is_running is True
        finally:
            daemon.stop()

    def test_on_stop_callback_exception_does_not_crash(self):
        """Test on stop callback exception does not crash."""
        config = _make_config()
        daemon = DaemonService(config)

        def bad_callback():
            """bad_callback."""
            raise RuntimeError("boom")

        daemon.on_stop(bad_callback)
        daemon.start_background()
        daemon.stop()
        # Should complete without crashing


class TestDaemonServicePidFile:
    """TestDaemonServicePidFile test suite."""
    def test_pid_file_written_and_removed(self, tmp_path):
        """Test pid file written and removed."""
        pid_file = tmp_path / "daemon.pid"
        config = _make_config(pid_file=pid_file)
        daemon = DaemonService(config)
        daemon.start_background()
        try:
            # PID file should exist
            assert pid_file.exists()
        finally:
            daemon.stop()
        # PID file should be removed
        assert not pid_file.exists()


class TestDaemonServiceScheduler:
    """TestDaemonServiceScheduler test suite."""
    def test_scheduler_accessible(self):
        """Test scheduler accessible."""
        config = _make_config()
        daemon = DaemonService(config)
        assert daemon.scheduler is not None


class TestDaemonServiceSignalHandling:
    """TestDaemonServiceSignalHandling test suite."""
    def test_handle_signal_writes_to_pipe(self):
        """Signal handler writes to self-pipe (no longer sets stop event directly)."""
        import os

        from .conftest import wired_pipe

        config = _make_config()
        daemon = DaemonService(config)
        with wired_pipe(daemon) as (r, _w):
            daemon._handle_signal(signal.SIGTERM, None)
            data = os.read(r, 1024)
            assert len(data) > 0


class TestDaemonServiceUptimeProperty:
    """TestDaemonServiceUptimeProperty test suite."""
    def test_uptime_zero_when_not_running(self):
        """Test uptime zero when not running."""
        config = _make_config()
        daemon = DaemonService(config)
        assert daemon.uptime_seconds == 0.0

    def test_uptime_positive_when_running(self):
        """Test uptime positive when running."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        try:
            time.sleep(0.05)
            assert daemon.uptime_seconds > 0
        finally:
            daemon.stop()

    def test_uptime_zero_after_stop(self):
        """Test uptime zero after stop."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        daemon.stop()
        assert daemon.uptime_seconds == 0.0


class TestDaemonServiceForeground:
    """TestDaemonServiceForeground test suite."""
    def test_start_foreground_runs_loop_until_stop(self, tmp_path):
        """start() runs in foreground blocking until stop_event is set."""
        pid_file = tmp_path / "daemon.pid"
        config = _make_config(pid_file=pid_file)
        daemon = DaemonService(config)

        # Run start() in a thread since it blocks
        started = threading.Event()
        daemon.on_start(lambda: started.set())

        t = threading.Thread(target=daemon.start, daemon=True)
        t.start()
        try:
            assert started.wait(timeout=5.0), "Daemon did not start"
            assert daemon.is_running
            assert pid_file.exists()
        finally:
            daemon.stop()
            t.join(timeout=5.0)

        assert not daemon.is_running

    def test_start_foreground_callback_exception_logged(self):
        """on_start callback exception in foreground mode should be logged, not crash."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.on_start(lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        t = threading.Thread(target=daemon.start, daemon=True)
        t.start()
        try:
            time.sleep(0.1)
            assert daemon.is_running
        finally:
            daemon.stop()
            t.join(timeout=5.0)

    def test_start_foreground_double_start_raises(self):
        """Calling start() while already running should raise."""
        config = _make_config()
        daemon = DaemonService(config)

        t = threading.Thread(target=daemon.start, daemon=True)
        t.start()
        try:
            # Verify first start reached readiness before attempting double-start
            assert daemon._started_event.wait(timeout=5.0), "First start did not reach readiness"
            with pytest.raises(RuntimeError, match="already running"):
                daemon.start()
        finally:
            daemon.stop()
            t.join(timeout=5.0)


class TestDaemonServiceSignalHandlerEdgeCases:
    """TestDaemonServiceSignalHandlerEdgeCases test suite."""
    def test_signal_handlers_skipped_in_non_main_thread(self):
        """_install_signal_handlers should skip when not in main thread."""
        config = _make_config()
        daemon = DaemonService(config)
        result = []

        def worker():
            """worker."""
            daemon._install_signal_handlers()
            # Should not have set any original handlers
            result.append(daemon._original_sigterm)
            result.append(daemon._original_sigint)

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5.0)
        # Both should still be None (handlers not installed from non-main thread)
        assert result == [None, None]

    def test_signal_handler_installation_oserror(self):
        """OSError during signal handler installation should be caught."""
        config = _make_config()
        daemon = DaemonService(config)
        with patch("signal.getsignal", side_effect=OSError("not supported")):
            # Should not raise
            daemon._install_signal_handlers()

    def test_restore_signal_handlers_skipped_in_non_main_thread(self):
        """_restore_signal_handlers should skip when not in main thread."""
        config = _make_config()
        daemon = DaemonService(config)
        # Set some fake originals
        daemon._original_sigterm = signal.SIG_DFL
        daemon._original_sigint = signal.SIG_DFL

        def worker():
            """worker."""
            daemon._restore_signal_handlers()

        t = threading.Thread(target=worker)
        t.start()
        t.join(timeout=5.0)
        # Should NOT have restored (not main thread), originals still set
        assert daemon._original_sigterm is not None
        assert daemon._original_sigint is not None

    def test_restore_signal_handlers_oserror(self):
        """OSError during signal handler restoration should be caught."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon._original_sigterm = signal.SIG_DFL
        daemon._original_sigint = signal.SIG_DFL
        with patch("signal.signal", side_effect=OSError("not supported")):
            # Should not raise
            daemon._restore_signal_handlers()
