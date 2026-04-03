"""
Unit tests for FileMonitor.

Tests directory watching, event collection, dynamic directory management,
and integration with real file operations using tmp_path fixtures.
"""

from __future__ import annotations

import threading
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
) -> list:
    """
    Continuously drain events and accumulate them until at least one
    matches the predicate or timeout expires.

    Uses get_events_blocking to avoid polling with time.sleep.

    Args:
        monitor: The FileMonitor to drain events from.
        predicate: Function that takes a list of all accumulated events
            and returns True when satisfied.
        timeout: Maximum time in seconds to wait.

    Returns:
        All accumulated events.
    """
    all_events = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        batch = monitor.get_events_blocking(max_size=100, timeout=min(0.1, remaining))
        all_events.extend(batch)
        if predicate(all_events):
            return all_events
    return all_events


def _drain_startup_events(monitor: FileMonitor) -> None:
    """Drain any events emitted during observer startup without sleeping.

    Polls with a short timeout until a 0.1 s quiet window passes, indicating
    the observer has settled.  The inner timeout is clamped to a non-negative
    value so it stays valid as the deadline approaches.
    """
    deadline = time.monotonic() + 1.0
    quiet_since: float | None = None
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        batch = monitor.get_events_blocking(max_size=100, timeout=min(0.05, remaining))
        if batch:
            quiet_since = None
        else:
            if quiet_since is None:
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= 0.1:
                break


@pytest.mark.unit
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


@pytest.mark.unit
class TestFileMonitorFileDetection:
    """Tests for detecting real file system changes."""

    def test_detect_file_creation(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that creating a file generates a CREATED event."""
        monitor.start()
        _drain_startup_events(monitor)

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
        _drain_startup_events(monitor)

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
        _drain_startup_events(monitor)

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
        _drain_startup_events(monitor)

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
        _drain_startup_events(monitor)

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
        _drain_startup_events(monitor)

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
        _drain_startup_events(monitor)

        assert monitor.event_count == 0

        arrived = threading.Event()
        monitor.on_created(lambda _: arrived.set())
        monitor.on_modified(lambda _: arrived.set())

        (watch_dir / "file.txt").write_text("data")

        assert arrived.wait(timeout=3.0), "event did not arrive within 3 s"
        assert monitor.event_count >= 1

    def test_get_events_with_default_batch_size(
        self, monitor: FileMonitor, watch_dir: Path
    ) -> None:
        """Test get_events uses config batch_size by default."""
        monitor.config.batch_size = 3
        arrived = threading.Event()
        count: list[int] = [0]
        count_lock = threading.Lock()

        def _track(_e: object) -> None:
            with count_lock:
                count[0] += 1
                if count[0] >= 10:
                    arrived.set()

        monitor.on_created(_track)
        monitor.on_modified(_track)
        monitor.start()
        _drain_startup_events(monitor)

        for i in range(10):
            (watch_dir / f"file_{i}.txt").write_text(f"content {i}")

        assert arrived.wait(timeout=5.0), "10 events did not arrive within 5 s"
        batch = monitor.get_events()
        assert len(batch) == 3

    def test_get_events_blocking_returns_on_event(
        self, monitor: FileMonitor, watch_dir: Path
    ) -> None:
        """Test that blocking get returns when events arrive."""
        monitor.start()
        _drain_startup_events(monitor)

        (watch_dir / "blocking_test.txt").write_text("hello")
        events = monitor.get_events_blocking(max_size=10, timeout=3.0)
        assert len(events) >= 1

    def test_get_events_blocking_timeout(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that blocking get returns empty on timeout when no events."""
        monitor.start()
        _drain_startup_events(monitor)

        events = monitor.get_events_blocking(max_size=10, timeout=0.1)
        assert events == []


@pytest.mark.unit
class TestFileMonitorDynamicDirectories:
    """Tests for dynamically adding/removing watch directories."""

    def test_add_directory_while_running(self, monitor: FileMonitor, tmp_path: Path) -> None:
        """Test adding a new directory to a running monitor."""
        monitor.start()

        new_dir = tmp_path / "extra"
        new_dir.mkdir()
        monitor.add_directory(new_dir)

        assert len(monitor.watched_directories) == 2

        # Drain any initial events
        _drain_startup_events(monitor)

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


@pytest.mark.unit
class TestFileMonitorCallbacks:
    """Tests for callback registration via monitor interface."""

    def test_on_created_callback(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that on_created callback fires for new files."""
        received_events: list = []
        fired = threading.Event()

        def _cb(e: object) -> None:
            received_events.append(e)
            fired.set()

        monitor.on_created(_cb)
        monitor.start()
        _drain_startup_events(monitor)
        received_events.clear()
        fired.clear()

        (watch_dir / "callback_test.txt").write_text("hello")

        assert fired.wait(timeout=3.0), "on_created callback did not fire within 3 s"
        assert len(received_events) >= 1

    def test_on_deleted_callback(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that on_deleted callback fires for removed files."""
        test_file = watch_dir / "to_remove.txt"
        test_file.write_text("bye")

        received_events: list = []
        fired = threading.Event()

        def _cb(e: object) -> None:
            received_events.append(e)
            fired.set()

        monitor.on_deleted(_cb)
        monitor.start()
        _drain_startup_events(monitor)
        received_events.clear()
        fired.clear()

        test_file.unlink()

        assert fired.wait(timeout=3.0), "on_deleted callback did not fire within 3 s"
        assert len(received_events) >= 1

    def test_on_modified_callback(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that on_modified callback fires for changed files."""
        test_file = watch_dir / "to_modify.txt"
        test_file.write_text("original")

        received_events: list = []
        fired = threading.Event()

        def _cb(e: object) -> None:
            received_events.append(e)
            fired.set()

        monitor.on_modified(_cb)
        monitor.start()
        _drain_startup_events(monitor)
        received_events.clear()
        fired.clear()

        test_file.write_text("modified")

        assert fired.wait(timeout=3.0), "on_modified callback did not fire within 3 s"
        assert len(received_events) >= 1


class TestFileMonitorOnMovedCallback:
    """Tests for on_moved callback registration."""

    def test_on_moved_callback_registers(self, monitor: FileMonitor, watch_dir: Path) -> None:
        """Test that on_moved callback is registered with the handler."""
        received_events: list = []

        def _cb(e: object) -> None:
            received_events.append(e)

        monitor.on_moved(_cb)
        # Verify the callback was registered (handler stores per-type lists)
        assert _cb in monitor.handler._on_moved_callbacks


class TestFileMonitorRemoveDirectoryEdgeCases:
    """Tests for remove_directory edge cases."""

    def test_remove_directory_path_not_in_config(
        self, monitor: FileMonitor, watch_dir: Path
    ) -> None:
        """Removing a watched dir when path was not in config.watch_directories.

        Covers the except ValueError: pass branch at lines 187-188.
        """
        monitor.start()
        # Manually clear config dirs so path won't be found in list
        monitor.config.watch_directories.clear()
        # Should succeed (the ValueError from list.remove is caught)
        monitor.remove_directory(watch_dir)
        assert len(monitor.watched_directories) == 0

    def test_remove_directory_when_not_running(self, tmp_path: Path) -> None:
        """Removing a directory when monitor is not running.

        Covers the branch at 176->182 where _running is False.
        """
        watch_dir = tmp_path / "watched"
        watch_dir.mkdir()
        config = WatcherConfig(
            watch_directories=[watch_dir],
            recursive=True,
            debounce_seconds=0.0,
        )
        mon = FileMonitor(config)
        # Manually add to _watches to simulate state
        path_key = str(watch_dir.resolve())
        mon._watches[path_key] = None  # type: ignore[assignment]
        mon.remove_directory(watch_dir)
        assert path_key not in mon._watches


class TestFileMonitorAddDirectoryEdgeCases:
    """Tests for add_directory edge cases."""

    def test_add_directory_before_start_already_in_config(self, tmp_path: Path) -> None:
        """Adding a directory before start when path is already in config.

        Covers the branch at 155->158 where path is already in watch_directories.
        """
        watch_dir = tmp_path / "watched"
        watch_dir.mkdir()
        config = WatcherConfig(
            watch_directories=[watch_dir],
            recursive=True,
            debounce_seconds=0.0,
        )
        mon = FileMonitor(config)
        before = [d.resolve() for d in mon.config.watch_directories]
        mon.add_directory(watch_dir)
        after = [d.resolve() for d in mon.config.watch_directories]
        assert after == before


class TestFileMonitorObserverFallback:
    """Tests for FSEvents fallback to PollingObserver."""

    def test_observer_type_property(self, monitor: FileMonitor) -> None:
        """Test that observer_type property reports correct observer type."""
        assert monitor.observer_type == "none"
        monitor.start()
        # Should be either 'native' or 'polling' depending on platform
        assert monitor.observer_type in ("native", "polling")
        monitor.stop()
        # Type is preserved after stop
        assert monitor.observer_type in ("native", "polling")

    def test_fallback_to_polling_observer(self, watch_dir: Path) -> None:
        """Test that monitor falls back to PollingObserver when native fails.

        This test mocks Observer.__init__ to raise an exception to simulate
        FSEvents/Inotify unavailability, then verifies fallback to polling.
        """
        from unittest.mock import patch

        from watchdog.observers.polling import PollingObserver

        config = WatcherConfig(
            watch_directories=[watch_dir],
            recursive=True,
            debounce_seconds=0.0,
        )
        mon = FileMonitor(config)

        # Mock Observer to raise an exception (simulating FSEvents failure)
        with patch(
            "file_organizer.watcher.monitor.Observer",
            side_effect=OSError("FSEvents unavailable"),
        ):
            mon.start()
            # Should have fallen back to polling
            assert mon.observer_type == "polling"
            assert isinstance(mon._observer, PollingObserver)
            # Monitor should still be running
            assert mon.is_running is True
            mon.stop()

    def test_polling_observer_detects_files(self, watch_dir: Path) -> None:
        """Test that PollingObserver detects file changes.

        This test forces use of PollingObserver and verifies it can still
        detect file system events, albeit with polling delays.
        """
        from unittest.mock import patch

        config = WatcherConfig(
            watch_directories=[watch_dir],
            recursive=True,
            debounce_seconds=0.0,
            batch_size=10,
        )
        mon = FileMonitor(config)

        # Force use of polling observer
        with patch(
            "file_organizer.watcher.monitor.Observer",
            side_effect=OSError("FSEvents unavailable"),
        ):
            mon.start()
            assert mon.observer_type == "polling"

            # Drain any startup events
            _drain_startup_events(mon)

            # Create a file
            test_file = watch_dir / "polling_test.txt"
            test_file.write_text("test content")

            # Wait for event (polling takes a bit longer)
            events = _wait_for_event_matching(
                mon,
                lambda evts: any(
                    e.event_type == EventType.CREATED and e.path.name == "polling_test.txt"
                    for e in evts
                ),
                timeout=5.0,  # Give polling observer more time
            )
            created = [
                e
                for e in events
                if e.event_type == EventType.CREATED and e.path.name == "polling_test.txt"
            ]
            assert len(created) >= 1
            mon.stop()
