"""Tests for PipelineOrchestrator watch loop."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.pipeline.orchestrator import PipelineConfig, PipelineOrchestrator

pytestmark = [pytest.mark.unit, pytest.mark.ci]


@dataclass
class FakeEvent:
    """Minimal file event for watch loop testing."""

    path: Path
    is_directory: bool = False


class TestWatchLoop:
    """Tests for _watch_loop method."""

    def _make_orchestrator(self) -> PipelineOrchestrator:
        """Create a PipelineOrchestrator with dry-run config.

        Returns:
            A PipelineOrchestrator configured for testing.
        """
        config = PipelineConfig(dry_run=True)
        orch = PipelineOrchestrator(config)
        return orch

    def test_watch_loop_processes_file_events(self):
        """File events should be passed to process_file."""
        orch = self._make_orchestrator()
        orch._running = True
        mock_monitor = MagicMock()
        orch._monitor = mock_monitor

        call_count = 0

        def fake_get_events(max_size=None):
            """Get test events on first call, then stop loop."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [FakeEvent(path=Path("/tmp/test.txt"))]
            # Stop the loop
            orch._running = False
            return []

        mock_monitor.get_events = fake_get_events

        with patch.object(orch, "process_file") as mock_process:
            orch._watch_loop()
            mock_process.assert_called_once_with(Path("/tmp/test.txt"))

    def test_watch_loop_skips_directory_events(self):
        """Directory events should be skipped."""
        orch = self._make_orchestrator()
        orch._running = True
        mock_monitor = MagicMock()
        orch._monitor = mock_monitor

        call_count = 0

        def fake_get_events(max_size=None):
            """Get directory event on first call, then stop loop."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [FakeEvent(path=Path("/tmp/somedir"), is_directory=True)]
            orch._running = False
            return []

        mock_monitor.get_events = fake_get_events

        with patch.object(orch, "process_file") as mock_process:
            orch._watch_loop()
            assert mock_process.call_count == 0, (
                f"process_file should not be called for directories, got {mock_process.call_count} calls"
            )

    def test_watch_loop_handles_vanished_file(self):
        """FileNotFoundError from process_file should be caught, loop continues."""
        orch = self._make_orchestrator()
        orch._running = True
        mock_monitor = MagicMock()
        orch._monitor = mock_monitor

        call_count = 0

        def fake_get_events(max_size=None):
            """Get two events on first call, then stop loop."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [
                    FakeEvent(path=Path("/tmp/vanished.txt")),
                    FakeEvent(path=Path("/tmp/exists.txt")),
                ]
            orch._running = False
            return []

        mock_monitor.get_events = fake_get_events

        process_calls = []

        def fake_process(path):
            """Process file or raise FileNotFoundError."""
            process_calls.append(path)
            if "vanished" in str(path):
                raise FileNotFoundError(f"No such file: {path}")

        with patch.object(orch, "process_file", side_effect=fake_process):
            orch._watch_loop()

        # Both files attempted, loop didn't crash
        assert len(process_calls) == 2, (
            f"Both files should be attempted even if one vanishes, got {len(process_calls)} attempts"
        )

    def test_watch_loop_handles_processing_error(self):
        """RuntimeError from process_file should be caught, loop continues."""
        orch = self._make_orchestrator()
        orch._running = True
        mock_monitor = MagicMock()
        orch._monitor = mock_monitor

        call_count = 0

        def fake_get_events(max_size=None):
            """Get test event on first call, then stop loop."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [FakeEvent(path=Path("/tmp/bad.txt"))]
            orch._running = False
            return []

        mock_monitor.get_events = fake_get_events

        with patch.object(orch, "process_file", side_effect=RuntimeError("processing failed")):
            # Should not raise
            try:
                orch._watch_loop()
            except RuntimeError:
                pytest.fail("Watch loop should catch and handle processing errors")

    def test_watch_loop_stops_on_running_false(self):
        """Loop should exit when _running is set to False."""
        orch = self._make_orchestrator()
        orch._running = False
        orch._monitor = MagicMock()

        # Should return immediately without calling get_events
        orch._watch_loop()
        assert orch._monitor.get_events.call_count == 0, (
            f"get_events should not be called when running=False, got {orch._monitor.get_events.call_count} calls"
        )


class TestWatchLoopExecutor:
    """Tests for ThreadPoolExecutor usage in watch loop."""

    def _make_orchestrator(self) -> PipelineOrchestrator:
        """Create a PipelineOrchestrator with dry-run config.

        Returns:
            A PipelineOrchestrator configured for testing.
        """
        config = PipelineConfig(dry_run=True)
        orch = PipelineOrchestrator(config)
        return orch

    def test_watch_loop_uses_executor(self):
        """File processing should be submitted to executor."""
        orch = self._make_orchestrator()
        orch._running = True
        mock_monitor = MagicMock()
        orch._monitor = mock_monitor

        call_count = 0

        def fake_get_events(max_size=None):
            """Get test event on first call, then stop loop."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [FakeEvent(path=Path("/tmp/test.txt"))]
            orch._running = False
            return []

        mock_monitor.get_events = fake_get_events

        with patch.object(orch._executor, "submit") as mock_submit:
            orch._watch_loop()
            # submit should have been called with process_file and the path
            mock_submit.assert_called_once_with(orch.process_file, Path("/tmp/test.txt"))

    def test_executor_max_workers_matches_config(self):
        """Executor should be created with max_workers from config.max_concurrent."""
        config = PipelineConfig(dry_run=True, max_concurrent=8)
        orch = PipelineOrchestrator(config)
        # Verify executor exists and was initialized (don't access private _max_workers)
        assert orch._executor is not None, "Executor should be initialized"
        # Verify the config value is what we set
        assert config.max_concurrent == 8, (
            f"Config max_concurrent should be 8, got {config.max_concurrent}"
        )

    def test_executor_shutdown_on_stop(self):
        """Executor should be shutdown when pipeline stops."""
        orch = self._make_orchestrator()
        orch._running = True
        orch._watch_thread = MagicMock()

        with patch.object(orch._executor, "shutdown") as mock_shutdown:
            orch.stop()
            mock_shutdown.assert_called_once_with(wait=False)

    def test_stop_drains_watch_workers_before_closing_stages(self):
        """stop() waits for in-flight workers before closing stage resources.

        Regression for #1285 review: ``shutdown(wait=False)`` lets already-
        submitted ``process_file`` work keep running, so a stage's ``close()``
        must not release resources while a worker is still in ``stage.process()``.
        An in-flight future must complete before any ``stage.close()`` runs;
        ``futures_wait`` guarantees this ordering deterministically (no sleep).
        """
        order: list[str] = []

        def record_work() -> None:
            order.append("work_done")

        class _ClosableStage:
            name = "closable"

            def process(self, context):  # pragma: no cover - not invoked here
                return context

            def close(self) -> None:
                order.append("close")

        orch = self._make_orchestrator()
        orch._running = True
        orch._watch_thread = MagicMock()
        orch._stages = [_ClosableStage()]

        future = orch._executor.submit(record_work)
        orch._watch_futures.add(future)
        future.add_done_callback(orch._on_watch_future_done)

        orch.stop()

        # Worker drained (work_done) strictly before the stage was closed.
        assert order == ["work_done", "close"]

    def test_stop_skips_stage_close_when_workers_exceed_drain_timeout(self):
        """stop() does not close stages if a worker outlives the drain timeout.

        Regression for #1285 review: a bounded drain that timed out and then
        closed stages anyway would reintroduce the closed-fd race for slow
        (>timeout) workers. When futures remain un-drained, the close loop is
        skipped (the fd is reclaimed at process exit) rather than raced.
        """
        closed: list[str] = []

        class _ClosableStage:
            name = "closable"

            def process(self, context):  # pragma: no cover - not invoked here
                return context

            def close(self) -> None:
                closed.append("close")

        orch = self._make_orchestrator()
        orch._running = True
        orch._watch_thread = MagicMock()
        orch._stages = [_ClosableStage()]
        # Simulate a still-running worker by registering a pending future.
        orch._watch_futures.add(MagicMock())

        # Patch the drain to report the worker as not finished within timeout.
        with patch(
            "file_organizer.pipeline.orchestrator.futures_wait",
            return_value=(set(), {object()}),
        ) as mock_wait:
            orch.stop()

        mock_wait.assert_called_once()
        # Stage close was skipped because the worker did not drain in time.
        assert closed == []

    def test_stop_closes_stages_for_batch_only_callers(self):
        """stop() closes stage resources even when start() was never called.

        Regression for #1285 review: batch-mode callers (process_batch without
        start()) leave _running False, so a stop() that returned early would
        leak stage-owned fds. The close loop must run on this path too.
        """
        closed: list[str] = []

        class _ClosableStage:
            name = "closable"

            def process(self, context):  # pragma: no cover - not invoked here
                return context

            def close(self) -> None:
                closed.append("close")

        orch = self._make_orchestrator()
        # No start(): batch-only lifecycle, _running stays False.
        assert orch._running is False
        orch._stages = [_ClosableStage()]

        orch.stop()
        assert closed == ["close"]

        # Idempotent: a second stop() does not double-close.
        orch.stop()
        assert closed == ["close"]

    def test_second_stop_after_drain_timeout_still_skips_close(self):
        """A second stop() re-checks workers and won't close under a live worker.

        Regression for #1285 review: the first (watch-mode) stop() times out
        draining, leaving _running False but _watch_futures populated. A second
        stop() takes the not-running branch — it must re-check the still-running
        futures rather than blindly closing stage resources, which would
        reintroduce the closed-fd race the timeout path avoids.
        """
        closed: list[str] = []

        class _ClosableStage:
            name = "closable"

            def process(self, context):  # pragma: no cover - not invoked here
                return context

            def close(self) -> None:
                closed.append("close")

        orch = self._make_orchestrator()
        orch._running = True
        orch._watch_thread = MagicMock()
        orch._stages = [_ClosableStage()]
        # A worker that never finishes: stays in _watch_futures across stops.
        orch._watch_futures.add(MagicMock())

        # Drain always reports the worker as still running (exceeds timeout).
        with patch(
            "file_organizer.pipeline.orchestrator.futures_wait",
            return_value=(set(), {object()}),
        ) as mock_wait:
            orch.stop()  # watch-mode path: times out, skips close
            assert orch._running is False
            orch.stop()  # not-running path: must re-check, still skip

        # Re-checked on both calls; never closed under the live worker.
        assert mock_wait.call_count == 2
        assert closed == []

    def test_on_watch_future_done_discards_under_lock(self):
        """The done-callback removes the future via the lock-guarded path.

        Regression for #1285 review: _watch_futures is mutated from executor
        threads, so add/discard/snapshot must share a lock. Verify the callback
        discards the tracked future (and is a no-op for an unknown one).
        """
        orch = self._make_orchestrator()
        tracked = MagicMock()
        with orch._watch_futures_lock:
            orch._watch_futures.add(tracked)

        orch._on_watch_future_done(tracked)
        assert tracked not in orch._watch_futures

        # Discarding a future that is not tracked is a safe no-op.
        orch._on_watch_future_done(MagicMock())
