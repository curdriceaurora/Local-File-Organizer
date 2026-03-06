"""Tests for pipeline orchestrator watch loop — executor-based processing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.pipeline.config import PipelineConfig
from file_organizer.pipeline.orchestrator import PipelineOrchestrator

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _patch_watch_loop_sleep():
    """Patch time.sleep in watch loop to speed up tests."""
    with patch("file_organizer.pipeline.orchestrator.time.sleep"):
        yield


@dataclass
class FakeEvent:
    """Minimal file-system event for testing."""

    path: Path
    is_directory: bool = False


def _sync_executor(pipeline: PipelineOrchestrator) -> MagicMock:
    """Replace the executor with one that calls functions synchronously.

    This makes tests deterministic by avoiding thread-pool timing issues.

    Args:
        pipeline: The orchestrator instance to configure.

    Returns:
        The mock executor configured with synchronous behavior.
    """
    mock_executor = MagicMock()

    def sync_submit(fn, *args, **kwargs):  # type: ignore[no-untyped-def]
        """Execute function synchronously instead of submitting to pool."""
        fn(*args, **kwargs)
        return MagicMock()

    mock_executor.submit.side_effect = sync_submit
    pipeline._executor = mock_executor
    return mock_executor


class TestWatchLoopProcessesFileEvents:
    def test_watch_loop_processes_file_events(self):
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)
        _sync_executor(pipeline)

        fake_event = FakeEvent(path=Path("/tmp/test.txt"))
        monitor = MagicMock()
        monitor.get_events.side_effect = [[fake_event], []]

        pipeline._monitor = monitor
        pipeline._running = True

        call_count = 0

        def stop_after_one(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                pipeline._running = False
            return MagicMock(success=True, category="test")

        with patch.object(pipeline, "process_file", side_effect=stop_after_one) as pf:
            pipeline._watch_loop()

        pf.assert_called_once_with(Path("/tmp/test.txt"))

    def test_watch_loop_skips_directory_events(self):
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)
        _sync_executor(pipeline)

        dir_event = FakeEvent(path=Path("/tmp/somedir"), is_directory=True)
        monitor = MagicMock()
        monitor.get_events.side_effect = [[dir_event], []]

        pipeline._monitor = monitor
        pipeline._running = True

        call_count = 0

        def count_and_stop(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                pipeline._running = False

        with (
            patch.object(pipeline, "process_file") as pf,
            patch("file_organizer.pipeline.orchestrator.time.sleep", side_effect=count_and_stop),
        ):
            pipeline._watch_loop()

        pf.assert_not_called()

    def test_watch_loop_handles_vanished_file(self):
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)
        _sync_executor(pipeline)

        fake_event = FakeEvent(path=Path("/tmp/vanished.txt"))
        monitor = MagicMock()
        monitor.get_events.side_effect = [[fake_event], []]

        pipeline._monitor = monitor
        pipeline._running = True

        call_count = 0

        def raise_fnf(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            pipeline._running = False
            raise FileNotFoundError("gone")

        with patch.object(pipeline, "process_file", side_effect=raise_fnf):
            # Should not crash — _process_watched_file catches FileNotFoundError
            pipeline._watch_loop()

    def test_watch_loop_handles_processing_error(self):
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)
        _sync_executor(pipeline)

        fake_event = FakeEvent(path=Path("/tmp/bad.txt"))
        monitor = MagicMock()
        monitor.get_events.side_effect = [[fake_event], []]

        pipeline._monitor = monitor
        pipeline._running = True

        call_count = 0

        def raise_runtime(*_args, **_kwargs):
            nonlocal call_count
            call_count += 1
            pipeline._running = False
            raise RuntimeError("boom")

        with patch.object(pipeline, "process_file", side_effect=raise_runtime):
            # Should not crash — exception is logged and loop continues
            pipeline._watch_loop()

    def test_watch_loop_stops_on_running_false(self):
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)

        monitor = MagicMock()
        monitor.get_events.return_value = []

        pipeline._monitor = monitor
        pipeline._running = False

        # Loop should exit immediately
        pipeline._watch_loop()


class TestWatchLoopExecutor:
    """Tests for the ThreadPoolExecutor integration in the watch loop."""

    def test_watch_loop_uses_executor_submit(self):
        """Verify _watch_loop submits work to the executor instead of calling directly."""
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)

        fake_event = FakeEvent(path=Path("/tmp/test.txt"))
        monitor = MagicMock()
        monitor.get_events.side_effect = [[fake_event], []]

        pipeline._monitor = monitor
        pipeline._running = True

        mock_executor = MagicMock()
        # submit doesn't call the function — just records it
        mock_executor.submit.return_value = MagicMock()
        pipeline._executor = mock_executor

        call_count = 0

        def stop_after_events(seconds):
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                pipeline._running = False

        with patch(
            "file_organizer.pipeline.orchestrator.time.sleep", side_effect=stop_after_events
        ):
            pipeline._watch_loop()

        # Verify submit was called with _process_watched_file and the path
        mock_executor.submit.assert_called_once_with(
            pipeline._process_watched_file, Path("/tmp/test.txt")
        )

    def test_executor_shutdown_on_stop(self):
        """Verify _executor.shutdown() is called during stop()."""
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)

        mock_executor = MagicMock()
        pipeline._executor = mock_executor
        pipeline._running = True

        pipeline.stop()

        mock_executor.shutdown.assert_called_once_with(wait=True)

    def test_executor_max_workers(self):
        """Verify max_workers matches config.max_concurrent."""
        config = PipelineConfig(max_concurrent=8)
        pipeline = PipelineOrchestrator(config)

        assert pipeline._executor._max_workers == 8

    def test_executor_default_max_workers(self):
        """Verify default max_workers is 4."""
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)

        assert pipeline._executor._max_workers == 4
