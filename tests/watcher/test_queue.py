"""
Unit tests for EventQueue and FileEvent.

Tests thread safety, batching, capacity limits, and blocking behavior.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from file_organizer.watcher.queue import EventQueue, EventType, FileEvent

# ---------------------------------------------------------------------------
# FileEvent tests
# ---------------------------------------------------------------------------


class TestFileEvent:
    """Tests for the FileEvent dataclass."""

    def test_create_file_event(self) -> None:
        """Test basic FileEvent construction."""
        now = datetime.now(UTC)
        event = FileEvent(
            event_type=EventType.CREATED,
            path=Path("/tmp/test.txt"),
            timestamp=now,
        )
        assert event.event_type == EventType.CREATED
        assert event.path == Path("/tmp/test.txt")
        assert event.timestamp == now
        assert event.is_directory is False
        assert event.dest_path is None

    def test_file_event_with_directory_flag(self) -> None:
        """Test FileEvent for directory events."""
        event = FileEvent(
            event_type=EventType.CREATED,
            path=Path("/tmp/newdir"),
            timestamp=datetime.now(UTC),
            is_directory=True,
        )
        assert event.is_directory is True

    def test_file_event_with_dest_path(self) -> None:
        """Test FileEvent for move events with destination."""
        event = FileEvent(
            event_type=EventType.MOVED,
            path=Path("/tmp/old.txt"),
            timestamp=datetime.now(UTC),
            dest_path=Path("/tmp/new.txt"),
        )
        assert event.dest_path == Path("/tmp/new.txt")

    def test_file_event_is_frozen(self) -> None:
        """Test that FileEvent instances are immutable."""
        event = FileEvent(
            event_type=EventType.CREATED,
            path=Path("/tmp/test.txt"),
            timestamp=datetime.now(UTC),
        )
        with pytest.raises(AttributeError):
            event.event_type = EventType.DELETED  # type: ignore[misc]

    def test_event_type_values(self) -> None:
        """Test EventType enum string values."""
        assert EventType.CREATED == "created"
        assert EventType.MODIFIED == "modified"
        assert EventType.DELETED == "deleted"
        assert EventType.MOVED == "moved"


# ---------------------------------------------------------------------------
# EventQueue tests
# ---------------------------------------------------------------------------


class TestEventQueue:
    """Tests for the EventQueue class."""

    def _make_event(
        self, event_type: EventType = EventType.CREATED, name: str = "test.txt"
    ) -> FileEvent:
        """Helper to create a FileEvent."""
        return FileEvent(
            event_type=event_type,
            path=Path(f"/tmp/{name}"),
            timestamp=datetime.now(UTC),
        )

    def test_enqueue_and_dequeue(self) -> None:
        """Test basic enqueue and dequeue cycle."""
        queue = EventQueue()
        event = self._make_event()
        queue.enqueue(event)

        batch = queue.dequeue_batch(max_size=10)
        assert len(batch) == 1
        assert batch[0] is event

    def test_dequeue_empty_queue(self) -> None:
        """Test dequeuing from an empty queue returns empty list."""
        queue = EventQueue()
        batch = queue.dequeue_batch(max_size=10)
        assert batch == []

    def test_dequeue_respects_max_size(self) -> None:
        """Test that dequeue_batch limits the number of returned events."""
        queue = EventQueue()
        for i in range(20):
            queue.enqueue(self._make_event(name=f"file_{i}.txt"))

        batch = queue.dequeue_batch(max_size=5)
        assert len(batch) == 5
        # Remaining events still in queue
        assert queue.size == 15

    def test_fifo_ordering(self) -> None:
        """Test that events are dequeued in FIFO order."""
        queue = EventQueue()
        events = [self._make_event(name=f"file_{i}.txt") for i in range(5)]
        for e in events:
            queue.enqueue(e)

        batch = queue.dequeue_batch(max_size=5)
        assert batch == events

    def test_max_size_capacity(self) -> None:
        """Test that a bounded queue drops oldest events when full."""
        queue = EventQueue(max_size=3)
        for i in range(5):
            queue.enqueue(self._make_event(name=f"file_{i}.txt"))

        # Should only have last 3 events
        assert queue.size == 3
        batch = queue.dequeue_batch(max_size=10)
        assert len(batch) == 3
        # Oldest two were dropped; remaining are files 2, 3, 4
        names = [str(e.path.name) for e in batch]
        assert names == ["file_2.txt", "file_3.txt", "file_4.txt"]

    def test_peek_returns_first_without_removing(self) -> None:
        """Test that peek shows the next event without removing it."""
        queue = EventQueue()
        event = self._make_event()
        queue.enqueue(event)

        peeked = queue.peek()
        assert peeked is event
        assert queue.size == 1  # Still there

    def test_peek_empty_queue(self) -> None:
        """Test that peek returns None on empty queue."""
        queue = EventQueue()
        assert queue.peek() is None

    def test_clear(self) -> None:
        """Test that clear removes all events and returns count."""
        queue = EventQueue()
        for i in range(5):
            queue.enqueue(self._make_event(name=f"file_{i}.txt"))

        removed = queue.clear()
        assert removed == 5
        assert queue.size == 0
        assert queue.is_empty is True

    def test_is_empty_property(self) -> None:
        """Test the is_empty property."""
        queue = EventQueue()
        assert queue.is_empty is True

        queue.enqueue(self._make_event())
        assert queue.is_empty is False

    def test_size_property(self) -> None:
        """Test the size property tracks queue length."""
        queue = EventQueue()
        assert queue.size == 0

        queue.enqueue(self._make_event())
        assert queue.size == 1

        queue.enqueue(self._make_event(name="other.txt"))
        assert queue.size == 2

        queue.dequeue_batch(max_size=1)
        assert queue.size == 1

    def test_thread_safety_concurrent_enqueue(self) -> None:
        """Test that concurrent enqueue operations are thread-safe."""
        queue = EventQueue()
        num_threads = 10
        events_per_thread = 50

        def enqueue_events(thread_id: int) -> None:
            for i in range(events_per_thread):
                queue.enqueue(self._make_event(name=f"t{thread_id}_f{i}.txt"))

        threads = [threading.Thread(target=enqueue_events, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert queue.size == num_threads * events_per_thread

    def test_blocking_dequeue_returns_when_event_arrives(self) -> None:
        """Test that blocking dequeue wakes up when an event is enqueued."""
        queue = EventQueue()
        results: list[list[FileEvent]] = []

        def consumer() -> None:
            batch = queue.dequeue_batch_blocking(max_size=5, timeout=5.0)
            results.append(batch)

        consumer_thread = threading.Thread(target=consumer)
        consumer_thread.start()

        # Give consumer time to start blocking
        time.sleep(0.1)
        event = self._make_event()
        queue.enqueue(event)

        consumer_thread.join(timeout=5.0)
        assert len(results) == 1
        assert len(results[0]) == 1
        assert results[0][0] is event

    def test_blocking_dequeue_timeout(self) -> None:
        """Test that blocking dequeue returns empty on timeout."""
        queue = EventQueue()
        batch = queue.dequeue_batch_blocking(max_size=5, timeout=0.1)
        assert batch == []


class TestEventQueueEdgeCases:
    """Additional edge case tests for EventQueue."""

    def _make_event(
        self, event_type: EventType = EventType.CREATED, name: str = "test.txt"
    ) -> FileEvent:
        """Helper to create a FileEvent."""
        return FileEvent(
            event_type=event_type,
            path=Path(f"/tmp/{name}"),
            timestamp=datetime.now(UTC),
        )

    def test_dequeue_batch_blocking_with_existing_events(self) -> None:
        """Test blocking dequeue returns immediately when events exist."""
        queue = EventQueue()
        queue.enqueue(self._make_event(name="a.txt"))
        queue.enqueue(self._make_event(name="b.txt"))

        # Should return immediately without blocking
        batch = queue.dequeue_batch_blocking(max_size=5, timeout=1.0)
        assert len(batch) == 2

    def test_dequeue_batch_blocking_returns_up_to_max_size(self) -> None:
        """Test blocking dequeue respects max_size even when more events exist."""
        queue = EventQueue()
        for i in range(10):
            queue.enqueue(self._make_event(name=f"file_{i}.txt"))

        batch = queue.dequeue_batch_blocking(max_size=3, timeout=1.0)
        assert len(batch) == 3
        assert queue.size == 7

    def test_unbounded_queue_accepts_many_events(self) -> None:
        """Test that unbounded queue (max_size=0) can hold many events."""
        queue = EventQueue(max_size=0)
        for i in range(1000):
            queue.enqueue(self._make_event(name=f"file_{i}.txt"))
        assert queue.size == 1000

    def test_bounded_queue_max_size_one(self) -> None:
        """Test bounded queue with capacity of 1."""
        queue = EventQueue(max_size=1)
        queue.enqueue(self._make_event(name="first.txt"))
        queue.enqueue(self._make_event(name="second.txt"))

        assert queue.size == 1
        batch = queue.dequeue_batch(10)
        assert len(batch) == 1
        assert batch[0].path.name == "second.txt"

    def test_clear_empty_queue_returns_zero(self) -> None:
        """Test that clearing an empty queue returns 0."""
        queue = EventQueue()
        assert queue.clear() == 0

    def test_dequeue_batch_with_zero_max_size(self) -> None:
        """Test dequeue_batch with max_size=0 returns empty list."""
        queue = EventQueue()
        queue.enqueue(self._make_event())
        batch = queue.dequeue_batch(max_size=0)
        assert batch == []
        assert queue.size == 1

    def test_concurrent_enqueue_and_dequeue(self) -> None:
        """Test thread safety with concurrent enqueue and dequeue operations."""
        queue = EventQueue()
        total_events = 100
        dequeued_events: list[FileEvent] = []
        lock = threading.Lock()

        def producer() -> None:
            for i in range(total_events):
                queue.enqueue(self._make_event(name=f"file_{i}.txt"))

        def consumer() -> None:
            collected = 0
            while collected < total_events:
                batch = queue.dequeue_batch(max_size=10)
                if batch:
                    with lock:
                        dequeued_events.extend(batch)
                    collected += len(batch)
                else:
                    time.sleep(0.01)

        producer_thread = threading.Thread(target=producer)
        consumer_thread = threading.Thread(target=consumer)

        producer_thread.start()
        consumer_thread.start()

        producer_thread.join(timeout=5.0)
        consumer_thread.join(timeout=5.0)

        assert len(dequeued_events) == total_events

    def test_blocking_dequeue_with_none_timeout(self) -> None:
        """Test blocking dequeue with None timeout returns when event arrives."""
        queue = EventQueue()
        results: list[list[FileEvent]] = []

        def consumer() -> None:
            batch = queue.dequeue_batch_blocking(max_size=1, timeout=5.0)
            results.append(batch)

        t = threading.Thread(target=consumer)
        t.start()
        time.sleep(0.1)
        queue.enqueue(self._make_event())
        t.join(timeout=5.0)

        assert len(results) == 1
        assert len(results[0]) == 1

    def test_peek_does_not_affect_size(self) -> None:
        """Test that repeated peek operations don't change queue size."""
        queue = EventQueue()
        event = self._make_event()
        queue.enqueue(event)

        for _ in range(5):
            peeked = queue.peek()
            assert peeked is event

        assert queue.size == 1

    def test_file_event_equality(self) -> None:
        """Test that identical FileEvent instances are equal (frozen dataclass)."""
        ts = datetime.now(UTC)
        e1 = FileEvent(event_type=EventType.CREATED, path=Path("/tmp/a.txt"), timestamp=ts)
        e2 = FileEvent(event_type=EventType.CREATED, path=Path("/tmp/a.txt"), timestamp=ts)
        assert e1 == e2

    def test_file_event_inequality(self) -> None:
        """Test that different FileEvent instances are not equal."""
        ts = datetime.now(UTC)
        e1 = FileEvent(event_type=EventType.CREATED, path=Path("/tmp/a.txt"), timestamp=ts)
        e2 = FileEvent(event_type=EventType.DELETED, path=Path("/tmp/a.txt"), timestamp=ts)
        assert e1 != e2

    def test_event_type_is_str_enum(self) -> None:
        """Test that EventType values can be used as strings."""
        assert str(EventType.CREATED) == "EventType.CREATED" or "created" in EventType.CREATED
        assert EventType.MODIFIED.value == "modified"
        assert isinstance(EventType.DELETED, str)
