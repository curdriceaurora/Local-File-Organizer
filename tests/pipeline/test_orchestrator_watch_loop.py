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
        """_make_orchestrator."""
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
            """fake_get_events."""
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
            """fake_get_events."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [FakeEvent(path=Path("/tmp/somedir"), is_directory=True)]
            orch._running = False
            return []

        mock_monitor.get_events = fake_get_events

        with patch.object(orch, "process_file") as mock_process:
            orch._watch_loop()
            mock_process.assert_not_called()

    def test_watch_loop_handles_vanished_file(self):
        """FileNotFoundError from process_file should be caught, loop continues."""
        orch = self._make_orchestrator()
        orch._running = True
        mock_monitor = MagicMock()
        orch._monitor = mock_monitor

        call_count = 0

        def fake_get_events(max_size=None):
            """fake_get_events."""
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
            """fake_process."""
            process_calls.append(path)
            if "vanished" in str(path):
                raise FileNotFoundError(f"No such file: {path}")

        with patch.object(orch, "process_file", side_effect=fake_process):
            orch._watch_loop()

        # Both files attempted, loop didn't crash
        assert len(process_calls) == 2

    def test_watch_loop_handles_processing_error(self):
        """RuntimeError from process_file should be caught, loop continues."""
        orch = self._make_orchestrator()
        orch._running = True
        mock_monitor = MagicMock()
        orch._monitor = mock_monitor

        call_count = 0

        def fake_get_events(max_size=None):
            """fake_get_events."""
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [FakeEvent(path=Path("/tmp/bad.txt"))]
            orch._running = False
            return []

        mock_monitor.get_events = fake_get_events

        with patch.object(orch, "process_file", side_effect=RuntimeError("processing failed")):
            # Should not raise
            orch._watch_loop()

    def test_watch_loop_stops_on_running_false(self):
        """Loop should exit when _running is set to False."""
        orch = self._make_orchestrator()
        orch._running = False
        orch._monitor = MagicMock()

        # Should return immediately without calling get_events
        orch._watch_loop()
        orch._monitor.get_events.assert_not_called()


class TestWatchLoopExecutor:
    """Tests for ThreadPoolExecutor usage in watch loop."""

    def _make_orchestrator(self) -> PipelineOrchestrator:
        """_make_orchestrator."""
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
            """fake_get_events."""
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
            mock_submit.assert_called_once()
            assert mock_submit.call_args[0][0] == orch.process_file
            assert mock_submit.call_args[0][1] == Path("/tmp/test.txt")

    def test_executor_max_workers_matches_config(self):
        """Executor max_workers should match config.max_concurrent."""
        config = PipelineConfig(dry_run=True, max_concurrent=8)
        orch = PipelineOrchestrator(config)
        assert orch._executor._max_workers == 8

    def test_executor_shutdown_on_stop(self):
        """Executor should be shutdown when pipeline stops."""
        orch = self._make_orchestrator()
        orch._running = True
        orch._thread = MagicMock()

        with patch.object(orch._executor, "shutdown") as mock_shutdown:
            orch.stop()
            mock_shutdown.assert_called_once_with(wait=False)
