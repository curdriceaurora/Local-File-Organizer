"""
Unit tests for FileEventHandler.

Tests debouncing, pattern filtering, callback dispatch, and event queuing.
Uses real file operations via tmp_path where possible.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
)

from file_organizer.watcher.config import WatcherConfig
from file_organizer.watcher.handler import FileEventHandler
from file_organizer.watcher.queue import EventQueue, EventType, FileEvent


@pytest.fixture
def default_config() -> WatcherConfig:
    """Watcher config with short debounce for fast tests."""
    return WatcherConfig(
        debounce_seconds=0.0,
        exclude_patterns=["*.tmp", ".git", "__pycache__"],
    )


@pytest.fixture
def debounce_config() -> WatcherConfig:
    """Watcher config with a measurable debounce window."""
    return WatcherConfig(
        debounce_seconds=0.5,
        exclude_patterns=[],
    )


@pytest.fixture
def queue() -> EventQueue:
    """Fresh event queue."""
    return EventQueue()


class TestFileEventHandlerFiltering:
    """Tests for event filtering by pattern and file type."""

    def test_accepts_normal_file(self, default_config: WatcherConfig, queue: EventQueue) -> None:
        """Test that a normal file passes through filters."""
        handler = FileEventHandler(default_config, queue)
        event = FileCreatedEvent(src_path="/tmp/document.txt")
        handler.on_created(event)
        assert queue.size == 1

    def test_filters_tmp_files(self, default_config: WatcherConfig, queue: EventQueue) -> None:
        """Test that .tmp files are filtered out."""
        handler = FileEventHandler(default_config, queue)
        event = FileCreatedEvent(src_path="/tmp/scratch.tmp")
        handler.on_created(event)
        assert queue.size == 0

    def test_filters_git_directory(self, default_config: WatcherConfig, queue: EventQueue) -> None:
        """Test that .git directory contents are filtered."""
        handler = FileEventHandler(default_config, queue)
        event = FileModifiedEvent(src_path="/repo/.git/index")
        handler.on_modified(event)
        assert queue.size == 0

    def test_filters_pycache(self, default_config: WatcherConfig, queue: EventQueue) -> None:
        """Test that __pycache__ contents are filtered."""
        handler = FileEventHandler(default_config, queue)
        event = FileCreatedEvent(src_path="/project/__pycache__/module.cpython-312.pyc")
        handler.on_created(event)
        assert queue.size == 0

    def test_file_type_filter_allows_matching_extension(self, queue: EventQueue) -> None:
        """Test that file_types filter allows matching extensions."""
        config = WatcherConfig(
            debounce_seconds=0.0,
            exclude_patterns=[],
            file_types=[".txt", ".pdf"],
        )
        handler = FileEventHandler(config, queue)

        handler.on_created(FileCreatedEvent(src_path="/tmp/doc.txt"))
        handler.on_created(FileCreatedEvent(src_path="/tmp/report.pdf"))
        assert queue.size == 2

    def test_file_type_filter_rejects_non_matching(self, queue: EventQueue) -> None:
        """Test that file_types filter rejects non-matching extensions."""
        config = WatcherConfig(
            debounce_seconds=0.0,
            exclude_patterns=[],
            file_types=[".txt"],
        )
        handler = FileEventHandler(config, queue)

        handler.on_created(FileCreatedEvent(src_path="/tmp/image.png"))
        assert queue.size == 0

    def test_directory_events_pass_through(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that directory events are not filtered by file type."""
        config = WatcherConfig(
            debounce_seconds=0.0,
            exclude_patterns=[],
            file_types=[".txt"],
        )
        handler = FileEventHandler(config, queue)

        event = DirCreatedEvent(src_path="/tmp/newdir")
        handler.on_created(event)
        assert queue.size == 1
        queued = queue.dequeue_batch(1)
        assert queued[0].is_directory is True


class TestFileEventHandlerDebounce:
    """Tests for debouncing behavior."""

    def test_rapid_events_debounced(
        self, debounce_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that rapid events on the same file are debounced."""
        handler = FileEventHandler(debounce_config, queue)

        # Fire multiple events rapidly on the same file
        for _ in range(5):
            handler.on_modified(FileModifiedEvent(src_path="/tmp/file.txt"))

        # Only the first should have gotten through
        assert queue.size == 1

    def test_events_after_debounce_window_pass(self, queue: EventQueue) -> None:
        """Test that events after debounce window are processed."""
        config = WatcherConfig(debounce_seconds=0.1, exclude_patterns=[])
        handler = FileEventHandler(config, queue)

        handler.on_modified(FileModifiedEvent(src_path="/tmp/file.txt"))
        assert queue.size == 1

        # Wait for debounce window to expire
        time.sleep(0.15)

        handler.on_modified(FileModifiedEvent(src_path="/tmp/file.txt"))
        assert queue.size == 2

    def test_different_files_not_debounced(
        self, debounce_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that events on different files are independent."""
        handler = FileEventHandler(debounce_config, queue)

        handler.on_created(FileCreatedEvent(src_path="/tmp/file_a.txt"))
        handler.on_created(FileCreatedEvent(src_path="/tmp/file_b.txt"))
        handler.on_created(FileCreatedEvent(src_path="/tmp/file_c.txt"))

        assert queue.size == 3

    def test_zero_debounce_allows_all(self, queue: EventQueue) -> None:
        """Test that zero debounce allows all events through."""
        config = WatcherConfig(debounce_seconds=0.0, exclude_patterns=[])
        handler = FileEventHandler(config, queue)

        for _ in range(10):
            handler.on_modified(FileModifiedEvent(src_path="/tmp/file.txt"))

        assert queue.size == 10

    def test_clear_debounce_state(self, debounce_config: WatcherConfig, queue: EventQueue) -> None:
        """Test that clearing debounce state allows immediate re-processing."""
        handler = FileEventHandler(debounce_config, queue)

        handler.on_modified(FileModifiedEvent(src_path="/tmp/file.txt"))
        assert queue.size == 1

        # This would be debounced
        handler.on_modified(FileModifiedEvent(src_path="/tmp/file.txt"))
        assert queue.size == 1

        # Clear debounce state
        handler.clear_debounce_state()

        # Now it should pass through again
        handler.on_modified(FileModifiedEvent(src_path="/tmp/file.txt"))
        assert queue.size == 2


class TestFileEventHandlerEventTypes:
    """Tests for correct handling of different event types."""

    def test_created_event(self, default_config: WatcherConfig, queue: EventQueue) -> None:
        """Test handling of file creation events."""
        handler = FileEventHandler(default_config, queue)
        handler.on_created(FileCreatedEvent(src_path="/tmp/new.txt"))

        events = queue.dequeue_batch(1)
        assert events[0].event_type == EventType.CREATED

    def test_modified_event(self, default_config: WatcherConfig, queue: EventQueue) -> None:
        """Test handling of file modification events."""
        handler = FileEventHandler(default_config, queue)
        handler.on_modified(FileModifiedEvent(src_path="/tmp/existing.txt"))

        events = queue.dequeue_batch(1)
        assert events[0].event_type == EventType.MODIFIED

    def test_deleted_event(self, default_config: WatcherConfig, queue: EventQueue) -> None:
        """Test handling of file deletion events."""
        handler = FileEventHandler(default_config, queue)
        handler.on_deleted(FileDeletedEvent(src_path="/tmp/gone.txt"))

        events = queue.dequeue_batch(1)
        assert events[0].event_type == EventType.DELETED

    def test_moved_event_with_dest(self, default_config: WatcherConfig, queue: EventQueue) -> None:
        """Test handling of file move events with destination path."""
        handler = FileEventHandler(default_config, queue)
        event = FileMovedEvent(src_path="/tmp/old.txt", dest_path="/tmp/new.txt")
        handler.on_moved(event)

        events = queue.dequeue_batch(1)
        assert events[0].event_type == EventType.MOVED
        assert events[0].dest_path == Path("/tmp/new.txt")

    def test_directory_deletion_event(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test handling of directory deletion events."""
        handler = FileEventHandler(default_config, queue)
        handler.on_deleted(DirDeletedEvent(src_path="/tmp/olddir"))

        events = queue.dequeue_batch(1)
        assert events[0].is_directory is True
        assert events[0].event_type == EventType.DELETED


class TestFileEventHandlerCallbacks:
    """Tests for callback registration and dispatch."""

    def test_created_callback_invoked(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that on_created callback fires."""
        handler = FileEventHandler(default_config, queue)
        callback = MagicMock()
        handler.register_callback(EventType.CREATED, callback)

        handler.on_created(FileCreatedEvent(src_path="/tmp/new.txt"))
        callback.assert_called_once()
        arg = callback.call_args[0][0]
        assert isinstance(arg, FileEvent)
        assert arg.event_type == EventType.CREATED

    def test_modified_callback_invoked(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that on_modified callback fires."""
        handler = FileEventHandler(default_config, queue)
        callback = MagicMock()
        handler.register_callback(EventType.MODIFIED, callback)

        handler.on_modified(FileModifiedEvent(src_path="/tmp/file.txt"))
        callback.assert_called_once()

    def test_deleted_callback_invoked(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that on_deleted callback fires."""
        handler = FileEventHandler(default_config, queue)
        callback = MagicMock()
        handler.register_callback(EventType.DELETED, callback)

        handler.on_deleted(FileDeletedEvent(src_path="/tmp/gone.txt"))
        callback.assert_called_once()

    def test_moved_callback_invoked(self, default_config: WatcherConfig, queue: EventQueue) -> None:
        """Test that on_moved callback fires."""
        handler = FileEventHandler(default_config, queue)
        callback = MagicMock()
        handler.register_callback(EventType.MOVED, callback)

        handler.on_moved(FileMovedEvent(src_path="/tmp/old.txt", dest_path="/tmp/new.txt"))
        callback.assert_called_once()

    def test_callback_error_does_not_crash(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that a failing callback does not prevent event queuing."""
        handler = FileEventHandler(default_config, queue)

        def bad_callback(event: FileEvent) -> None:
            raise RuntimeError("boom")

        handler.register_callback(EventType.CREATED, bad_callback)
        handler.on_created(FileCreatedEvent(src_path="/tmp/file.txt"))

        # Event should still be in the queue despite callback failure
        assert queue.size == 1

    def test_multiple_callbacks_all_invoked(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that multiple callbacks for the same event type all fire."""
        handler = FileEventHandler(default_config, queue)
        cb1 = MagicMock()
        cb2 = MagicMock()
        handler.register_callback(EventType.CREATED, cb1)
        handler.register_callback(EventType.CREATED, cb2)

        handler.on_created(FileCreatedEvent(src_path="/tmp/file.txt"))
        cb1.assert_called_once()
        cb2.assert_called_once()

    def test_pending_paths_tracking(
        self, debounce_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that pending_paths tracks debounced path count."""
        handler = FileEventHandler(debounce_config, queue)
        assert handler.pending_paths == 0

        handler.on_created(FileCreatedEvent(src_path="/tmp/a.txt"))
        handler.on_created(FileCreatedEvent(src_path="/tmp/b.txt"))
        assert handler.pending_paths == 2

        handler.clear_debounce_state()
        assert handler.pending_paths == 0


class TestFileEventHandlerMovedEdgeCases:
    """Tests for edge cases in on_moved handling."""

    def test_moved_event_without_dest_path_attr(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test move event when dest_path attribute is absent."""
        handler = FileEventHandler(default_config, queue)
        # Simulate a move event where dest_path is missing
        event = MagicMock(spec=FileMovedEvent)
        event.src_path = "/tmp/old.txt"
        # Remove dest_path attribute entirely
        del event.dest_path
        handler.on_moved(event)

        events = queue.dequeue_batch(1)
        assert len(events) == 1
        assert events[0].event_type == EventType.MOVED
        assert events[0].dest_path is None

    def test_moved_event_with_none_dest_path(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test move event when dest_path is explicitly None."""
        handler = FileEventHandler(default_config, queue)
        event = MagicMock(spec=FileMovedEvent)
        event.src_path = "/tmp/old.txt"
        event.dest_path = None
        handler.on_moved(event)

        events = queue.dequeue_batch(1)
        assert len(events) == 1
        assert events[0].dest_path is None

    def test_moved_directory_event(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that directory move events are classified correctly."""
        from watchdog.events import DirMovedEvent

        handler = FileEventHandler(default_config, queue)
        event = DirMovedEvent(src_path="/tmp/olddir", dest_path="/tmp/newdir")
        handler.on_moved(event)

        events = queue.dequeue_batch(1)
        assert len(events) == 1
        assert events[0].is_directory is True
        assert events[0].event_type == EventType.MOVED
        assert events[0].dest_path == Path("/tmp/newdir")


class TestFileEventHandlerDebounceThreadSafety:
    """Tests for debounce behavior under concurrent access."""

    def test_concurrent_debounce_same_file(self, queue: EventQueue) -> None:
        """Test that debouncing is thread-safe for the same file path."""
        config = WatcherConfig(debounce_seconds=1.0, exclude_patterns=[])
        handler = FileEventHandler(config, queue)
        errors: list[Exception] = []

        def fire_event() -> None:
            try:
                handler.on_modified(FileModifiedEvent(src_path="/tmp/shared.txt"))
            except Exception as e:
                errors.append(e)

        import threading

        threads = [threading.Thread(target=fire_event) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # Only one event should get through due to debouncing
        assert queue.size == 1

    def test_concurrent_debounce_different_files(self, queue: EventQueue) -> None:
        """Test debouncing with different files from concurrent threads."""
        config = WatcherConfig(debounce_seconds=1.0, exclude_patterns=[])
        handler = FileEventHandler(config, queue)

        import threading

        def fire_event(file_id: int) -> None:
            handler.on_created(FileCreatedEvent(src_path=f"/tmp/file_{file_id}.txt"))

        threads = [threading.Thread(target=fire_event, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each file should get through exactly once
        assert queue.size == 10


class TestFileEventHandlerEventTimestamps:
    """Tests for event timestamp correctness."""

    def test_queued_event_has_utc_timestamp(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that queued events have UTC timestamps."""
        from datetime import UTC

        handler = FileEventHandler(default_config, queue)
        handler.on_created(FileCreatedEvent(src_path="/tmp/test.txt"))

        events = queue.dequeue_batch(1)
        assert events[0].timestamp.tzinfo is not None
        assert events[0].timestamp.tzinfo in (UTC, UTC)

    def test_queued_event_path_is_pathlib(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that queued events have Path objects, not strings."""
        handler = FileEventHandler(default_config, queue)
        handler.on_created(FileCreatedEvent(src_path="/tmp/test.txt"))

        events = queue.dequeue_batch(1)
        assert isinstance(events[0].path, Path)


class TestFileEventHandlerCallbackEdgeCases:
    """Tests for callback dispatch edge cases."""

    def test_callback_receives_correct_dest_path_on_move(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that move callbacks receive the correct destination path."""
        handler = FileEventHandler(default_config, queue)
        received_events: list[FileEvent] = []
        handler.register_callback(EventType.MOVED, received_events.append)

        event = FileMovedEvent(src_path="/tmp/old.txt", dest_path="/tmp/new.txt")
        handler.on_moved(event)

        assert len(received_events) == 1
        assert received_events[0].dest_path == Path("/tmp/new.txt")

    def test_second_callback_runs_when_first_fails(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that subsequent callbacks fire even if an earlier one raises."""
        handler = FileEventHandler(default_config, queue)
        second_called = MagicMock()

        def bad_callback(event: FileEvent) -> None:
            raise ValueError("intentional error")

        handler.register_callback(EventType.CREATED, bad_callback)
        handler.register_callback(EventType.CREATED, second_called)

        handler.on_created(FileCreatedEvent(src_path="/tmp/file.txt"))

        second_called.assert_called_once()

    def test_no_callbacks_registered_no_error(
        self, default_config: WatcherConfig, queue: EventQueue
    ) -> None:
        """Test that events process cleanly when no callbacks are registered."""
        handler = FileEventHandler(default_config, queue)
        # No callbacks registered, should not raise
        handler.on_created(FileCreatedEvent(src_path="/tmp/file.txt"))
        assert queue.size == 1
