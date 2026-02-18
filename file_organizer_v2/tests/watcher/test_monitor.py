"""
Unit tests for FileMonitor.

Tests directory watching, event collection, dynamic directory management,
and integration with real file operations using tmp_path fixtures.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from file_organizer.watcher.config import WatcherConfig
from file_organizer.watcher.monitor import FileMonitor
from file_organizer.watcher.queue import EventType


@pytest.fixture
def watch_dir(tmp_path: Path) -> Path:
    """Create a temporary directory to watch."""
    d = tmp_path / "watched"
    d.mkdir()
    return d


@pytest.fixture
def monitor(watch_dir: Path) -> FileMonitor:
    """Create a FileMonitor configured for the temp watch directory."""
    config = WatcherConfig(
        watch_directories=[watch_dir],
        recursive=True,
        debounce_seconds=0.0,
        exclude_patterns=["*.tmp", ".git"],
    )
    mon = FileMonitor(config)
    yield mon
    if mon.is_running:
        mon.stop()


def _wait_for_event_matching(
    monitor: FileMonitor,
    predicate: callable,
    timeout: float = 3.0,
    poll_interval: float = 0.05,
) -> list:
    """
    Continuously drain events and accumulate them until at least one
    matches the predicate or timeout expires.

    Args:
        monitor: The FileMonitor to drain events from.
        predicate: Function that takes a list of all accumulated events
            and returns True when satisfied.
        timeout: Maximum time in seconds to wait.
        poll_interval: Seconds between polls.

    Returns:
        All accumulated events.
    """
    all_events = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        batch = monitor.get_events(max_size=100)
        all_events.extend(batch)
        if predicate(all_events):
            return all_events
        time.sleep(poll_interval)
    return all_events


class TestFileMonitorLifecycle:
    """Tests for start/stop lifecycle."""

    def test_start_and_stop(self, monitor: FileMonitor) -> None:
        """Test basic start and stop cycle."""
        assert monitor.is_running is False
        monitor.start()
        assert monitor.is_running is True
        monitor.stop()
        assert monitor.is_running is False

    def test_double_start_raises(self, monitor: FileMonitor) -> None:
        """Test that starting an already running monitor raises RuntimeError."""
        monitor.start()
        with pytest.raises(RuntimeError, match="already running"):
            monitor.start()

    def test_stop_when_not_running_is_safe(self, monitor: FileMonitor) -> None:
        """Test that stopping a non-running monitor is a no-op."""
        monitor.stop()  # Should not raise
        assert monitor.is_running is False

    def test_start_with_nonexistent_directory_raises(self, tmp_path: Path) -> None:
        """Test that starting with a missing directory raises FileNotFoundError."""
        config = WatcherConfig(
            watch_directories=[tmp_path / "does_not_exist"],
            debounce_seconds=0.0,
        )
        mon = FileMonitor(config)
        with pytest.raises(FileNotFoundError):
            mon.start()

    def test_watched_directories_after_start(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that watched_directories reports correct directories."""
        monitor.start()
        dirs = monitor.watched_directories
        assert len(dirs) == 1
        assert dirs[0] == watch_dir.resolve()


class TestFileMonitorFileDetection:
    """Tests for detecting real file system changes."""

    def test_detect_file_creation(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that creating a file generates a CREATED event."""
        monitor.start()
        # Drain any initial events from observer startup
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        (watch_dir / "new_file.txt").write_text("hello")

        events = _wait_for_event_matching(
            monitor,
            lambda evts: any(
                e.event_type == EventType.CREATED and e.path.name == "new_file.txt" for e in evts
            ),
        )
        created = [
            e for e in events if e.event_type == EventType.CREATED and e.path.name == "new_file.txt"
        ]
        assert len(created) >= 1

    def test_detect_file_modification(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that modifying a file generates a MODIFIED event."""
        test_file = watch_dir / "existing.txt"
        test_file.write_text("original")

        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        test_file.write_text("updated content")

        events = _wait_for_event_matching(
            monitor,
            lambda evts: any(e.event_type == EventType.MODIFIED for e in evts),
        )
        modified = [e for e in events if e.event_type == EventType.MODIFIED]
        assert len(modified) >= 1

    def test_detect_file_deletion(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that deleting a file generates a DELETED event."""
        test_file = watch_dir / "to_delete.txt"
        test_file.write_text("temporary")

        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        test_file.unlink()

        events = _wait_for_event_matching(
            monitor,
            lambda evts: any(e.event_type == EventType.DELETED for e in evts),
        )
        deleted = [e for e in events if e.event_type == EventType.DELETED]
        assert len(deleted) >= 1

    def test_detect_subdirectory_file(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that files in subdirectories are detected with recursive=True."""
        subdir = watch_dir / "subdir"
        subdir.mkdir()

        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        (subdir / "nested.txt").write_text("nested content")

        events = _wait_for_event_matching(
            monitor,
            lambda evts: any(
                e.event_type == EventType.CREATED and "nested.txt" in str(e.path) for e in evts
            ),
        )
        nested = [
            e for e in events if e.event_type == EventType.CREATED and "nested.txt" in str(e.path)
        ]
        assert len(nested) >= 1

    def test_filtered_files_not_detected(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that filtered files do not appear in events."""
        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        (watch_dir / "scratch.tmp").write_text("temporary")
        # Also create an allowed file so we know events are working
        (watch_dir / "allowed.txt").write_text("allowed")

        events = _wait_for_event_matching(
            monitor,
            lambda evts: any(e.path.name == "allowed.txt" for e in evts),
        )
        # Should not see .tmp files (non-directory file events)
        tmp_events = [e for e in events if e.path.suffix == ".tmp" and not e.is_directory]
        assert len(tmp_events) == 0

    def test_multiple_files_batched(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that multiple file creations are collected as a batch."""
        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        filenames = {f"batch_{i}.txt" for i in range(5)}
        for name in filenames:
            (watch_dir / name).write_text("content")

        events = _wait_for_event_matching(
            monitor,
            lambda evts: filenames.issubset({e.path.name for e in evts}),
            timeout=5.0,
        )
        found_names = {e.path.name for e in events}
        assert filenames.issubset(found_names)

    def test_event_count_property(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that event_count reflects pending events."""
        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)  # Drain startup events

        assert monitor.event_count == 0
        (watch_dir / "file.txt").write_text("data")

        # Wait until at least one event is queued
        deadline = time.monotonic() + 3.0
        while monitor.event_count == 0 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert monitor.event_count >= 1

    def test_get_events_with_default_batch_size(
        self, monitor: FileMonitor, watch_dir: Path
    ) -> None:
        """Test get_events uses config batch_size by default."""
        monitor.config.batch_size = 3
        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        for i in range(10):
            (watch_dir / f"file_{i}.txt").write_text(f"content {i}")

        # Wait for events to arrive
        deadline = time.monotonic() + 5.0
        while monitor.event_count < 10 and time.monotonic() < deadline:
            time.sleep(0.05)

        batch = monitor.get_events()
        assert len(batch) <= 3

    def test_get_events_blocking_returns_on_event(
        self, monitor: FileMonitor, watch_dir: Path
    ) -> None:
        """Test that blocking get returns when events arrive."""
        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        (watch_dir / "blocking_test.txt").write_text("hello")
        events = monitor.get_events_blocking(max_size=10, timeout=3.0)
        assert len(events) >= 1

    def test_get_events_blocking_timeout(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that blocking get returns empty on timeout when no events."""
        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        events = monitor.get_events_blocking(max_size=10, timeout=0.1)
        assert events == []


class TestFileMonitorDynamicDirectories:
    """Tests for dynamically adding/removing watch directories."""

    def test_add_directory_while_running(self, monitor: FileMonitor, tmp_path: Path) -> None:
        """Test adding a new directory to a running monitor."""
        monitor.start()
        time.sleep(0.1)

        new_dir = tmp_path / "extra"
        new_dir.mkdir()
        monitor.add_directory(new_dir)

        assert len(monitor.watched_directories) == 2

        # Drain any initial events
        time.sleep(0.2)
        monitor.get_events(max_size=100)

        (new_dir / "extra_file.txt").write_text("extra content")

        events = _wait_for_event_matching(
            monitor,
            lambda evts: any("extra_file.txt" in str(e.path) for e in evts),
        )
        paths = [str(e.path) for e in events]
        assert any("extra_file.txt" in p for p in paths)

    def test_add_directory_before_start(self, tmp_path: Path) -> None:
        """Test adding a directory before the monitor starts."""
        config = WatcherConfig(debounce_seconds=0.0, exclude_patterns=[])
        mon = FileMonitor(config)

        new_dir = tmp_path / "prestart"
        new_dir.mkdir()
        mon.add_directory(new_dir)

        assert new_dir in mon.config.watch_directories

    def test_add_duplicate_directory_raises(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that adding an already-watched directory raises ValueError."""
        monitor.start()
        with pytest.raises(ValueError, match="already watched"):
            monitor.add_directory(watch_dir)

    def test_add_nonexistent_directory_raises(self, monitor: FileMonitor, tmp_path: Path) -> None:
        """Test that adding a non-existent directory raises FileNotFoundError."""
        monitor.start()
        with pytest.raises(FileNotFoundError):
            monitor.add_directory(tmp_path / "nope")

    def test_remove_directory(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test removing a directory from monitoring."""
        monitor.start()
        monitor.remove_directory(watch_dir)

        assert len(monitor.watched_directories) == 0

    def test_remove_nonexistent_directory_raises(
        self, monitor: FileMonitor, tmp_path: Path
    ) -> None:
        """Test that removing a non-watched directory raises ValueError."""
        monitor.start()
        with pytest.raises(ValueError, match="not being watched"):
            monitor.remove_directory(tmp_path / "unknown")


class TestFileMonitorCallbacks:
    """Tests for callback registration via monitor interface."""

    def test_on_created_callback(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that on_created callback fires for new files."""
        received_events: list = []
        monitor.on_created(lambda e: received_events.append(e))
        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)  # Drain startup events
        received_events.clear()

        (watch_dir / "callback_test.txt").write_text("hello")

        deadline = time.monotonic() + 3.0
        while not received_events and time.monotonic() < deadline:
            time.sleep(0.05)

        assert len(received_events) >= 1

    def test_on_deleted_callback(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that on_deleted callback fires for removed files."""
        test_file = watch_dir / "to_remove.txt"
        test_file.write_text("bye")

        received_events: list = []
        monitor.on_deleted(lambda e: received_events.append(e))
        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)  # Drain startup events
        received_events.clear()

        test_file.unlink()

        deadline = time.monotonic() + 3.0
        while not received_events and time.monotonic() < deadline:
            time.sleep(0.05)

        assert len(received_events) >= 1

    def test_on_modified_callback(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that on_modified callback fires for changed files."""
        test_file = watch_dir / "to_modify.txt"
        test_file.write_text("original")

        received_events: list = []
        monitor.on_modified(lambda e: received_events.append(e))
        monitor.start()
        time.sleep(0.2)
        monitor.get_events(max_size=100)
        received_events.clear()

        test_file.write_text("modified")

        deadline = time.monotonic() + 3.0
        while not received_events and time.monotonic() < deadline:
            time.sleep(0.05)

        assert len(received_events) >= 1
