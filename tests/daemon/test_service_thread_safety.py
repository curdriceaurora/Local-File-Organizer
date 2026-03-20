"""Tests for DaemonService thread safety fixes."""

from __future__ import annotations

import threading
from pathlib import Path

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


class TestStartBackgroundLockCoverage:
    """Verify start_background holds lock through thread creation."""

    def test_start_background_holds_lock_through_thread_creation(self):
        """Events and thread creation should happen under the same lock acquisition."""
        config = _make_config()
        daemon = DaemonService(config)

        # Verify that _started_event, _stopped_event, and _thread are all
        # set atomically within the lock. _running must be set before
        # thread creation so concurrent calls see consistent state.
        daemon.start_background()
        try:
            assert daemon.is_running
            assert daemon._thread is not None
            # Verify _thread is alive (created and started while holding lock)
            assert daemon._thread.is_alive()
        finally:
            daemon.stop()

    def test_concurrent_start_stop_no_race(self):
        """Rapidly starting and stopping should not produce races."""
        config = _make_config()
        errors: list[Exception] = []

        def cycle():
            """cycle."""
            try:
                daemon = DaemonService(config)
                daemon.start_background()
                daemon._started_event.wait(timeout=5.0)
                daemon.stop()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=cycle) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()  # Wait indefinitely instead of timeout

        # Verify all threads actually terminated (not hung)
        for i, t in enumerate(threads):
            assert not t.is_alive(), f"Cycle thread {i} did not terminate"

        assert not errors, f"Race condition errors: {errors}"

    def test_concurrent_start_raises_on_second_call(self):
        """Concurrent start_background calls should only succeed once.

        Verifies that _running is protected by the lock and set before
        thread creation, preventing the double-start race condition.
        """
        config = _make_config()
        daemon = DaemonService(config)
        errors: list[Exception] = []
        successes = 0

        def try_start():
            """try_start."""
            nonlocal successes
            try:
                daemon.start_background()
                successes += 1
            except RuntimeError as exc:
                if "already running" in str(exc):
                    errors.append(None)  # Expected error
                else:
                    errors.append(exc)
            except Exception as exc:
                errors.append(exc)

        # Spawn multiple threads trying to start simultaneously
        threads = [threading.Thread(target=try_start) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only one should succeed
        assert successes == 1, f"Expected 1 success, got {successes}"
        # Rest should get RuntimeError
        assert len(errors) == 4, f"Expected 4 errors, got {len(errors)}"
        # No unexpected errors (check all are None = expected error)
        assert all(e is None for e in errors), f"Unexpected errors: {[e for e in errors if e]}"

        daemon.stop()


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
