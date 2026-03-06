"""Unit tests for DaemonScheduler.

Tests task registration, cancellation, periodic execution,
background operation, error handling, and edge cases.
All time-sensitive operations are mocked for fast, deterministic tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.daemon.scheduler import DaemonScheduler, _ScheduledTask

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def scheduler() -> DaemonScheduler:
    """Create a DaemonScheduler instance and ensure cleanup."""
    sched = DaemonScheduler()
    yield sched
    sched.stop()


# ---------------------------------------------------------------------------
# _ScheduledTask dataclass tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScheduledTask:
    """Tests for the _ScheduledTask internal dataclass."""

    def test_default_last_run(self) -> None:
        """_ScheduledTask defaults last_run to 0.0."""

        def cb():
            return None

        task = _ScheduledTask(name="t", interval=5.0, callback=cb)

        assert task.name == "t"
        assert task.interval == 5.0
        assert task.callback is cb
        assert task.last_run == 0.0

    def test_custom_last_run(self) -> None:
        """_ScheduledTask accepts a custom last_run value."""
        task = _ScheduledTask(name="t", interval=1.0, callback=lambda: None, last_run=99.9)
        assert task.last_run == 99.9


# ---------------------------------------------------------------------------
# DaemonScheduler.__init__ tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInit:
    """Tests for DaemonScheduler initialization."""

    def test_initial_state(self) -> None:
        """A fresh scheduler starts empty and not running."""
        sched = DaemonScheduler()

        assert sched.task_count == 0
        assert sched.task_names == []
        assert sched.is_running is False


# ---------------------------------------------------------------------------
# schedule_task tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
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
        cb_old = MagicMock()
        cb_new = MagicMock()
        scheduler.schedule_task("health", 10.0, cb_old)
        scheduler.schedule_task("health", 20.0, cb_new)

        assert scheduler.task_count == 1
        # The replacement should have the new callback
        assert scheduler._tasks["health"].callback is cb_new
        assert scheduler._tasks["health"].interval == 20.0

    def test_invalid_interval_zero_raises(self, scheduler: DaemonScheduler) -> None:
        """schedule_task raises ValueError for zero interval."""
        with pytest.raises(ValueError, match="positive"):
            scheduler.schedule_task("bad", 0, lambda: None)

    def test_invalid_interval_negative_raises(self, scheduler: DaemonScheduler) -> None:
        """schedule_task raises ValueError for negative interval."""
        with pytest.raises(ValueError, match="positive"):
            scheduler.schedule_task("bad", -1.0, lambda: None)

    def test_schedule_task_logs_debug(self, scheduler: DaemonScheduler) -> None:
        """schedule_task emits a debug log message."""
        with patch("file_organizer.daemon.scheduler.logger") as mock_logger:
            scheduler.schedule_task("test_task", 5.0, lambda: None)
            mock_logger.debug.assert_called_once()
            args = mock_logger.debug.call_args
            assert "test_task" in str(args)


# ---------------------------------------------------------------------------
# cancel_task tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCancelTask:
    """Tests for DaemonScheduler.cancel_task."""

    def test_cancel_existing_task(self, scheduler: DaemonScheduler) -> None:
        """cancel_task removes the task and returns True."""
        scheduler.schedule_task("health", 10.0, lambda: None)

        assert scheduler.cancel_task("health") is True
        assert scheduler.task_count == 0
        assert "health" not in scheduler.task_names

    def test_cancel_nonexistent_returns_false(self, scheduler: DaemonScheduler) -> None:
        """cancel_task returns False when the task does not exist."""
        assert scheduler.cancel_task("ghost") is False

    def test_cancel_one_of_many(self, scheduler: DaemonScheduler) -> None:
        """cancel_task only removes the specified task."""
        scheduler.schedule_task("a", 1.0, lambda: None)
        scheduler.schedule_task("b", 2.0, lambda: None)
        scheduler.schedule_task("c", 3.0, lambda: None)

        result = scheduler.cancel_task("b")

        assert result is True
        assert scheduler.task_count == 2
        assert set(scheduler.task_names) == {"a", "c"}

    def test_cancel_task_logs_debug(self, scheduler: DaemonScheduler) -> None:
        """cancel_task emits a debug log when successful."""
        scheduler.schedule_task("x", 1.0, lambda: None)
        with patch("file_organizer.daemon.scheduler.logger") as mock_logger:
            scheduler.cancel_task("x")
            mock_logger.debug.assert_called_once()
            assert "x" in str(mock_logger.debug.call_args)


# ---------------------------------------------------------------------------
# Properties tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProperties:
    """Tests for scheduler properties."""

    def test_is_running_initially_false(self, scheduler: DaemonScheduler) -> None:
        """is_running is False before run() is called."""
        assert scheduler.is_running is False

    def test_task_names_returns_list(self, scheduler: DaemonScheduler) -> None:
        """task_names returns a list, not a reference to internal dict keys."""
        scheduler.schedule_task("a", 1.0, lambda: None)
        names = scheduler.task_names
        assert isinstance(names, list)
        # Modifying the returned list should not affect internal state
        names.append("fake")
        assert "fake" not in scheduler.task_names

    def test_task_count_matches_names(self, scheduler: DaemonScheduler) -> None:
        """task_count is consistent with task_names length."""
        assert scheduler.task_count == len(scheduler.task_names)
        scheduler.schedule_task("a", 1.0, lambda: None)
        scheduler.schedule_task("b", 2.0, lambda: None)
        assert scheduler.task_count == len(scheduler.task_names)
        assert scheduler.task_count == 2


# ---------------------------------------------------------------------------
# _tick tests (core scheduling logic)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTick:
    """Tests for DaemonScheduler._tick (internal scheduling tick)."""

    def test_tick_fires_ready_task(self, scheduler: DaemonScheduler) -> None:
        """_tick fires a task whose interval has elapsed."""
        cb = MagicMock()
        scheduler.schedule_task("t", 1.0, cb)

        # last_run defaults to 0.0; monotonic returns large enough value
        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=100.0):
            scheduler._tick()

        cb.assert_called_once()

    def test_tick_skips_task_not_ready(self, scheduler: DaemonScheduler) -> None:
        """_tick does not fire a task whose interval has not elapsed."""
        cb = MagicMock()
        scheduler.schedule_task("t", 10.0, cb)
        # Set last_run to recent
        scheduler._tasks["t"].last_run = 99.0

        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=100.0):
            scheduler._tick()

        cb.assert_not_called()

    def test_tick_fires_task_at_exact_interval(self, scheduler: DaemonScheduler) -> None:
        """_tick fires a task when exactly interval seconds have passed."""
        cb = MagicMock()
        scheduler.schedule_task("t", 5.0, cb)
        scheduler._tasks["t"].last_run = 95.0

        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=100.0):
            scheduler._tick()

        cb.assert_called_once()

    def test_tick_updates_last_run_on_success(self, scheduler: DaemonScheduler) -> None:
        """_tick updates last_run to current time after successful callback."""
        cb = MagicMock()
        scheduler.schedule_task("t", 1.0, cb)

        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=42.0):
            scheduler._tick()

        assert scheduler._tasks["t"].last_run == 42.0

    def test_tick_handles_callback_exception(self, scheduler: DaemonScheduler) -> None:
        """_tick catches callback exceptions and continues."""
        cb = MagicMock(side_effect=RuntimeError("boom"))
        scheduler.schedule_task("failing", 1.0, cb)

        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=100.0):
            # Should not raise
            scheduler._tick()

        cb.assert_called_once()

    def test_tick_updates_last_run_on_exception(self, scheduler: DaemonScheduler) -> None:
        """_tick updates last_run even when callback raises, preventing tight loops."""
        cb = MagicMock(side_effect=ValueError("oops"))
        scheduler.schedule_task("failing", 1.0, cb)

        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=77.0):
            scheduler._tick()

        assert scheduler._tasks["failing"].last_run == 77.0

    def test_tick_logs_exception(self, scheduler: DaemonScheduler) -> None:
        """_tick logs exceptions from task callbacks."""
        cb = MagicMock(side_effect=RuntimeError("boom"))
        scheduler.schedule_task("failing", 1.0, cb)

        with (
            patch("file_organizer.daemon.scheduler.time.monotonic", return_value=100.0),
            patch("file_organizer.daemon.scheduler.logger") as mock_logger,
        ):
            scheduler._tick()

        mock_logger.exception.assert_called_once()
        assert "failing" in str(mock_logger.exception.call_args)

    def test_tick_multiple_tasks_selective(self, scheduler: DaemonScheduler) -> None:
        """_tick fires only tasks whose intervals have elapsed."""
        ready_cb = MagicMock()
        not_ready_cb = MagicMock()

        scheduler.schedule_task("ready", 5.0, ready_cb)
        scheduler.schedule_task("not_ready", 100.0, not_ready_cb)

        # ready: last_run=0.0, interval=5.0, now=10.0 -> fires
        # not_ready: last_run=5.0, interval=100.0, now=10.0 -> skips
        scheduler._tasks["not_ready"].last_run = 5.0

        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=10.0):
            scheduler._tick()

        ready_cb.assert_called_once()
        not_ready_cb.assert_not_called()

    def test_tick_no_tasks(self, scheduler: DaemonScheduler) -> None:
        """_tick does nothing when no tasks are registered."""
        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=100.0):
            scheduler._tick()  # Should not raise


# ---------------------------------------------------------------------------
# Helper to make run() terminate quickly
# ---------------------------------------------------------------------------


def _make_run_terminate_after(scheduler: DaemonScheduler, iterations: int):
    """Replace _stop_event.wait so run() terminates after N loop iterations.

    Returns a callable that should be used as the side_effect for
    _stop_event.wait, or monkey-patches it directly.
    """
    call_count = {"n": 0}

    def fake_wait(timeout=None):
        call_count["n"] += 1
        if call_count["n"] >= iterations:
            scheduler._stop_event.set()
        return scheduler._stop_event.is_set()

    scheduler._stop_event.wait = fake_wait  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# run() tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRun:
    """Tests for DaemonScheduler.run (blocking event loop)."""

    def test_run_sets_running_flag(self, scheduler: DaemonScheduler) -> None:
        """run() sets is_running True during execution and clears on exit."""
        running_during = {"was_running": False}

        original_tick = scheduler._tick

        def spy_tick():
            running_during["was_running"] = scheduler.is_running
            original_tick()

        _make_run_terminate_after(scheduler, 2)

        with patch.object(scheduler, "_tick", side_effect=spy_tick):
            scheduler.run()

        assert running_during["was_running"] is True
        assert scheduler.is_running is False

    def test_run_calls_tick_in_loop(self, scheduler: DaemonScheduler) -> None:
        """run() calls _tick on each iteration of the loop."""
        tick_count = {"n": 0}

        def counting_tick():
            tick_count["n"] += 1

        _make_run_terminate_after(scheduler, 3)

        with patch.object(scheduler, "_tick", side_effect=counting_tick):
            scheduler.run()

        # _tick should have been called at least twice (loop iterates before stop)
        assert tick_count["n"] >= 2

    def test_run_logs_start_and_stop(self, scheduler: DaemonScheduler) -> None:
        """run() logs scheduler start and stop."""
        _make_run_terminate_after(scheduler, 1)

        with (
            patch.object(scheduler, "_tick"),
            patch("file_organizer.daemon.scheduler.logger") as mock_logger,
        ):
            scheduler.run()

        # Should have logged start and stop info messages
        info_calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("started" in c.lower() for c in info_calls)
        assert any("stopped" in c.lower() for c in info_calls)

    def test_run_clears_running_on_exception(self, scheduler: DaemonScheduler) -> None:
        """run() clears _running even if an exception propagates out."""
        _make_run_terminate_after(scheduler, 100)  # won't reach this

        with (
            patch.object(scheduler, "_tick", side_effect=KeyboardInterrupt("abort")),
            pytest.raises(KeyboardInterrupt),
        ):
            scheduler.run()

        assert scheduler.is_running is False

    def test_run_clears_stop_event_at_start(self, scheduler: DaemonScheduler) -> None:
        """run() clears the stop event so a previous stop() doesn't prevent starting."""
        scheduler._stop_event.set()

        _make_run_terminate_after(scheduler, 1)

        with patch.object(scheduler, "_tick"):
            scheduler.run()

        # It ran successfully despite the pre-set event
        assert scheduler.is_running is False


# ---------------------------------------------------------------------------
# run_in_background tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRunInBackground:
    """Tests for DaemonScheduler.run_in_background."""

    def test_starts_daemon_thread(self, scheduler: DaemonScheduler) -> None:
        """run_in_background creates and starts a daemon thread."""
        with patch("file_organizer.daemon.scheduler.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            scheduler.run_in_background()

            mock_thread_cls.assert_called_once_with(
                target=scheduler.run,
                name="daemon-scheduler",
                daemon=True,
            )
            mock_thread.start.assert_called_once()
            assert scheduler._thread is mock_thread

    def test_raises_if_already_running(self, scheduler: DaemonScheduler) -> None:
        """run_in_background raises RuntimeError if already running."""
        scheduler._running = True

        with pytest.raises(RuntimeError, match="already running"):
            scheduler.run_in_background()

    def test_double_run_raises(self, scheduler: DaemonScheduler) -> None:
        """run_in_background raises when called twice if first is still running."""
        with patch("file_organizer.daemon.scheduler.threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread

            scheduler.run_in_background()
            # Simulate the run() method setting _running
            scheduler._running = True

            with pytest.raises(RuntimeError, match="already running"):
                scheduler.run_in_background()


# ---------------------------------------------------------------------------
# stop() tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStop:
    """Tests for DaemonScheduler.stop."""

    def test_stop_sets_event(self, scheduler: DaemonScheduler) -> None:
        """stop() sets the internal stop event."""
        scheduler.stop()
        assert scheduler._stop_event.is_set()

    def test_stop_joins_thread(self, scheduler: DaemonScheduler) -> None:
        """stop() joins the background thread with timeout."""
        mock_thread = MagicMock()
        scheduler._thread = mock_thread

        scheduler.stop()

        mock_thread.join.assert_called_once_with(timeout=5.0)
        assert scheduler._thread is None

    def test_stop_without_thread(self, scheduler: DaemonScheduler) -> None:
        """stop() works safely when no thread exists."""
        scheduler._thread = None
        scheduler.stop()  # Should not raise
        assert scheduler._stop_event.is_set()

    def test_stop_idempotent(self, scheduler: DaemonScheduler) -> None:
        """stop() is safe to call multiple times."""
        scheduler.stop()
        scheduler.stop()
        assert scheduler._stop_event.is_set()

    def test_stop_clears_thread_reference(self, scheduler: DaemonScheduler) -> None:
        """stop() sets _thread to None after joining."""
        mock_thread = MagicMock()
        scheduler._thread = mock_thread

        scheduler.stop()

        assert scheduler._thread is None

    def test_stop_logs_debug(self, scheduler: DaemonScheduler) -> None:
        """stop() emits a debug log message."""
        with patch("file_organizer.daemon.scheduler.logger") as mock_logger:
            scheduler.stop()
            mock_logger.debug.assert_called()


# ---------------------------------------------------------------------------
# Integration-style tests (still fast, using controlled loop termination)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIntegration:
    """Higher-level tests that exercise multiple components together."""

    def test_schedule_run_stop_cycle(self, scheduler: DaemonScheduler) -> None:
        """Full lifecycle: schedule, run, verify execution, stop."""
        cb = MagicMock()
        scheduler.schedule_task("job", 0.01, cb)

        _make_run_terminate_after(scheduler, 2)

        # Use real _tick but mock time.monotonic to always trigger
        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=1000.0):
            scheduler.run()

        cb.assert_called()
        assert scheduler.is_running is False

    def test_cancel_during_run(self, scheduler: DaemonScheduler) -> None:
        """A task can be cancelled while the scheduler is running."""
        cb_keep = MagicMock()
        cb_cancel = MagicMock()

        scheduler.schedule_task("keep", 1.0, cb_keep)
        scheduler.schedule_task("cancel_me", 1.0, cb_cancel)

        tick_count = {"n": 0}
        original_tick = scheduler._tick

        def tick_then_cancel():
            tick_count["n"] += 1
            if tick_count["n"] == 1:
                scheduler.cancel_task("cancel_me")
            original_tick()

        _make_run_terminate_after(scheduler, 3)

        with (
            patch.object(scheduler, "_tick", side_effect=tick_then_cancel),
            patch("file_organizer.daemon.scheduler.time.monotonic", return_value=1000.0),
        ):
            scheduler.run()

        assert "cancel_me" not in scheduler.task_names

    def test_exception_in_one_task_doesnt_block_others(self, scheduler: DaemonScheduler) -> None:
        """A failing task does not prevent other tasks from running."""
        failing_cb = MagicMock(side_effect=RuntimeError("fail"))
        good_cb = MagicMock()

        scheduler.schedule_task("failing", 1.0, failing_cb)
        scheduler.schedule_task("good", 1.0, good_cb)

        with patch("file_organizer.daemon.scheduler.time.monotonic", return_value=1000.0):
            scheduler._tick()

        failing_cb.assert_called_once()
        good_cb.assert_called_once()
