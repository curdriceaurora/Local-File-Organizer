"""
Event queue for batching file system events.

Provides a thread-safe queue that collects FileEvent instances and
supports batch dequeuing for efficient processing.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from file_organizer._compat import StrEnum


class EventType(StrEnum):
    """Types of file system events."""

    CREATED = "created"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


@dataclass(frozen=True)
class FileEvent:
    """
    Represents a single file system event.

    Attributes:
        event_type: The type of file system event.
        path: The path of the affected file or directory.
        timestamp: When the event occurred.
        is_directory: Whether the event target is a directory.
        dest_path: Destination path for move events, None otherwise.
    """

    event_type: EventType
    path: Path
    timestamp: datetime
    is_directory: bool = False
    dest_path: Path | None = None


class EventQueue:
    """
    Thread-safe queue for file system events with batch dequeue support.

    Events are enqueued individually and can be dequeued in configurable
    batch sizes for efficient downstream processing.

    Attributes:
        max_size: Maximum number of events the queue can hold.
            When exceeded, oldest events are dropped. 0 means unlimited.
    """

    def __init__(self, max_size: int = 0) -> None:
        """
        Initialize the event queue.

        Args:
            max_size: Maximum queue capacity. 0 means unlimited.
        """
        self._queue: deque[FileEvent] = deque(maxlen=max_size if max_size > 0 else None)
        self._lock = threading.Lock()
        self._not_empty = threading.Condition(self._lock)

    def enqueue(self, event: FileEvent) -> None:
        """
        Add an event to the queue.

        Thread-safe. If the queue is at max capacity, the oldest event
        is silently dropped.

        Args:
            event: The file event to enqueue.
        """
        with self._not_empty:
            self._queue.append(event)
            self._not_empty.notify()

    def dequeue_batch(self, max_size: int = 10) -> list[FileEvent]:
        """
        Remove and return up to max_size events from the queue.

        Returns immediately with whatever events are available (may be
        fewer than max_size, or an empty list if the queue is empty).

        Args:
            max_size: Maximum number of events to return.

        Returns:
            A list of FileEvent instances, up to max_size.
        """
        with self._lock:
            batch: list[FileEvent] = []
            count = min(max_size, len(self._queue))
            for _ in range(count):
                batch.append(self._queue.popleft())
            return batch

    def dequeue_batch_blocking(
        self, max_size: int = 10, timeout: float | None = None
    ) -> list[FileEvent]:
        """
        Remove and return up to max_size events, blocking if empty.

        Waits until at least one event is available (or timeout expires),
        then returns up to max_size events.

        Args:
            max_size: Maximum number of events to return.
            timeout: Maximum seconds to wait. None means wait forever.

        Returns:
            A list of FileEvent instances. Empty list if timeout expired
            with no events available.
        """
        with self._not_empty:
            if len(self._queue) == 0:
                self._not_empty.wait(timeout=timeout)

            batch: list[FileEvent] = []
            count = min(max_size, len(self._queue))
            for _ in range(count):
                batch.append(self._queue.popleft())
            return batch

    def peek(self) -> FileEvent | None:
        """
        Return the next event without removing it.

        Returns:
            The next FileEvent, or None if the queue is empty.
        """
        with self._lock:
            if self._queue:
                return self._queue[0]
            return None

    def clear(self) -> int:
        """
        Remove all events from the queue.

        Returns:
            The number of events that were removed.
        """
        with self._lock:
            count = len(self._queue)
            self._queue.clear()
            return count

    @property
    def size(self) -> int:
        """Return the current number of events in the queue."""
        with self._lock:
            return len(self._queue)

    @property
    def is_empty(self) -> bool:
        """Return True if the queue contains no events."""
        with self._lock:
            return len(self._queue) == 0
