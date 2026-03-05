"""Coverage tests for daemon.service module."""

from __future__ import annotations

import signal
import threading
import time
from pathlib import Path

import pytest

from file_organizer.daemon.config import DaemonConfig
from file_organizer.daemon.service import DaemonService

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


class TestDaemonServiceInit:
    def test_initial_state(self):
        config = _make_config()
        daemon = DaemonService(config)
        assert daemon.is_running is False
        assert daemon.uptime_seconds == 0.0
        assert daemon.files_processed == 0


class TestDaemonServiceStartBackground:
    def test_start_and_stop(self):
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
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        try:
            with pytest.raises(RuntimeError, match="already running"):
                daemon.start_background()
        finally:
            daemon.stop()

    def test_stop_when_not_running(self):
        config = _make_config()
        daemon = DaemonService(config)
        daemon.stop()  # Should not raise


class TestDaemonServiceRestart:
    def test_restart(self):
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        try:
            daemon.restart()
            assert daemon.is_running is True
        finally:
            daemon.stop()

    def test_restart_from_stopped(self):
        config = _make_config()
        daemon = DaemonService(config)
        daemon.restart()
        try:
            assert daemon.is_running is True
        finally:
            daemon.stop()


class TestDaemonServiceCallbacks:
    def test_on_start_callback(self):
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
        config = _make_config()
        daemon = DaemonService(config)
        stop_called = threading.Event()
        daemon.on_stop(lambda: stop_called.set())
        daemon.start_background()
        daemon.stop()
        assert stop_called.wait(timeout=2.0)

    def test_on_start_callback_exception_does_not_crash(self):
        config = _make_config()
        daemon = DaemonService(config)

        def bad_callback():
            raise RuntimeError("boom")

        daemon.on_start(bad_callback)
        daemon.start_background()
        try:
            assert daemon.is_running is True
        finally:
            daemon.stop()

    def test_on_stop_callback_exception_does_not_crash(self):
        config = _make_config()
        daemon = DaemonService(config)

        def bad_callback():
            raise RuntimeError("boom")

        daemon.on_stop(bad_callback)
        daemon.start_background()
        daemon.stop()
        # Should complete without crashing


class TestDaemonServicePidFile:
    def test_pid_file_written_and_removed(self, tmp_path):
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
    def test_scheduler_accessible(self):
        config = _make_config()
        daemon = DaemonService(config)
        assert daemon.scheduler is not None


class TestDaemonServiceSignalHandling:
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
    def test_uptime_zero_when_not_running(self):
        config = _make_config()
        daemon = DaemonService(config)
        assert daemon.uptime_seconds == 0.0

    def test_uptime_positive_when_running(self):
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        try:
            time.sleep(0.05)
            assert daemon.uptime_seconds > 0
        finally:
            daemon.stop()

    def test_uptime_zero_after_stop(self):
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        daemon.stop()
        assert daemon.uptime_seconds == 0.0
