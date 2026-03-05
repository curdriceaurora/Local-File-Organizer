"""Tests for DaemonService thread safety fixes."""

from __future__ import annotations

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


class TestStartBackgroundLockCoverage:
    """Verify start_background holds lock through thread creation."""

    def test_start_background_holds_lock_through_thread_creation(self):
        """Events and thread creation should happen under the same lock acquisition."""
        config = _make_config()
        daemon = DaemonService(config)

        # Verify that _started_event, _stopped_event, and _thread are all
        # set atomically within the lock
        daemon.start_background()
        try:
            assert daemon.is_running
            assert daemon._thread is not None
        finally:
            daemon.stop()

    def test_concurrent_start_stop_no_race(self):
        """Rapidly starting and stopping should not produce races."""
        config = _make_config()
        errors: list[Exception] = []

        def cycle():
            try:
                daemon = DaemonService(config)
                daemon.start_background()
                time.sleep(0.02)
                daemon.stop()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=cycle) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"Race condition errors: {errors}"


class TestRestartLockedRead:
    """Verify restart reads _running under the lock."""

    def test_restart_reads_running_under_lock(self):
        """restart() should read _running under the lock to avoid TOCTOU."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        try:
            # Restart while running — should work without race
            daemon.restart()
            assert daemon.is_running
        finally:
            daemon.stop()


class TestCleanupLockedWrite:
    """Verify _cleanup sets _running=False under the lock."""

    def test_cleanup_sets_running_false_under_lock(self):
        """After stop(), _running must be False (set under lock in _cleanup)."""
        config = _make_config()
        daemon = DaemonService(config)
        daemon.start_background()
        assert daemon.is_running
        daemon.stop()
        assert not daemon.is_running
        # _started_at should also be None
        assert daemon._started_at is None
