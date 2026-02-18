"""
Unit tests for DaemonScheduler.

Tests task registration, cancellation, periodic execution,
background operation, and error handling.
"""

from __future__ import annotations

import threading
import time

import pytest

from file_organizer.daemon.scheduler import DaemonScheduler


@pytest.fixture
def scheduler() -> DaemonScheduler:
    """Create a DaemonScheduler instance and ensure cleanup."""
    sched = DaemonScheduler()
    yield sched
    sched.stop()


class TestScheduleTask:
    """Tests for DaemonScheduler.schedule_task."""

    def test_register_single_task(self, scheduler: DaemonScheduler) -> None:
        """schedule_task adds a task to the registry."""
        scheduler.schedule_task("health", 10.0, lambda: None)

        assert scheduler.task_count == 1
        assert "health" in scheduler.task_names

    def test_register_multiple_tasks(self, scheduler: DaemonScheduler) -> None:
        """schedule_task supports registering multiple tasks."""
        scheduler.schedule_task("health", 10.0, lambda: None)
        scheduler.schedule_task("stats", 60.0, lambda: None)
        scheduler.schedule_task("cleanup", 300.0, lambda: None)

        assert scheduler.task_count == 3
        assert set(scheduler.task_names) == {"health", "stats", "cleanup"}

    def test_replace_existing_task(self, scheduler: DaemonScheduler) -> None:
        """schedule_task replaces a task with the same name."""
        called = []
        scheduler.schedule_task("health", 10.0, lambda: called.append("old"))
        scheduler.schedule_task("health", 20.0, lambda: called.append("new"))

        assert scheduler.task_count == 1

    def test_invalid_interval_raises(self, scheduler: DaemonScheduler) -> None:
        """schedule_task raises ValueError for non-positive interval."""
        with pytest.raises(ValueError, match="positive"):
            scheduler.schedule_task("bad", 0, lambda: None)

        with pytest.raises(ValueError, match="positive"):
            scheduler.schedule_task("bad", -1.0, lambda: None)


class TestCancelTask:
    """Tests for DaemonScheduler.cancel_task."""

    def test_cancel_existing_task(self, scheduler: DaemonScheduler) -> None:
        """cancel_task removes the task and returns True."""
        scheduler.schedule_task("health", 10.0, lambda: None)

        assert scheduler.cancel_task("health") is True
        assert scheduler.task_count == 0

    def test_cancel_nonexistent_returns_false(self, scheduler: DaemonScheduler) -> None:
        """cancel_task returns False when the task does not exist."""
        assert scheduler.cancel_task("ghost") is False


class TestRunAndStop:
    """Tests for the scheduler event loop lifecycle."""

    def test_run_in_background_starts(self, scheduler: DaemonScheduler) -> None:
        """run_in_background starts the event loop in a thread."""
        scheduler.run_in_background()
        time.sleep(0.05)

        assert scheduler.is_running is True

    def test_stop_after_background_run(self, scheduler: DaemonScheduler) -> None:
        """stop() terminates the background event loop."""
        scheduler.run_in_background()
        time.sleep(0.05)

        scheduler.stop()
        time.sleep(0.05)

        assert scheduler.is_running is False

    def test_double_run_raises(self, scheduler: DaemonScheduler) -> None:
        """run_in_background raises when already running."""
        scheduler.run_in_background()
        time.sleep(0.05)

        with pytest.raises(RuntimeError, match="already running"):
            scheduler.run_in_background()

    def test_stop_idempotent(self, scheduler: DaemonScheduler) -> None:
        """stop() is safe to call when not running."""
        scheduler.stop()  # Should not raise
        scheduler.stop()  # Still safe

    def test_task_executes_on_schedule(self, scheduler: DaemonScheduler) -> None:
        """A scheduled task fires when its interval elapses."""
        counter = {"value": 0}
        lock = threading.Lock()

        def increment() -> None:
            with lock:
                counter["value"] += 1

        scheduler.schedule_task("counter", 0.05, increment)
        scheduler.run_in_background()

        # Wait long enough for several firings
        time.sleep(0.5)
        scheduler.stop()

        with lock:
            # Should have fired multiple times
            assert counter["value"] >= 2

    def test_task_exception_does_not_crash_scheduler(self, scheduler: DaemonScheduler) -> None:
        """A task that raises does not stop the scheduler."""
        healthy_calls = {"value": 0}
        lock = threading.Lock()

        def failing_task() -> None:
            raise RuntimeError("boom")

        def healthy_task() -> None:
            with lock:
                healthy_calls["value"] += 1

        scheduler.schedule_task("failing", 0.05, failing_task)
        scheduler.schedule_task("healthy", 0.05, healthy_task)
        scheduler.run_in_background()

        time.sleep(0.4)
        scheduler.stop()

        with lock:
            assert healthy_calls["value"] >= 2
        assert scheduler.is_running is False
