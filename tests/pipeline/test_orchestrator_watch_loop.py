"""Tests for pipeline orchestrator watch loop TOCTOU fix."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.pipeline.config import PipelineConfig
from file_organizer.pipeline.orchestrator import PipelineOrchestrator

pytestmark = pytest.mark.unit


@dataclass
class FakeEvent:
    """Minimal file-system event for testing."""

    path: Path
    is_directory: bool = False


class TestWatchLoopProcessesFileEvents:
    def test_watch_loop_processes_file_events(self):
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)

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
            # Should not crash
            pipeline._watch_loop()

    def test_watch_loop_handles_processing_error(self):
        config = PipelineConfig()
        pipeline = PipelineOrchestrator(config)

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
