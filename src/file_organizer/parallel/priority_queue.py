"""Priority queue for ordered file processing.

This module provides a thread-safe priority queue that orders items by
priority level (higher number = higher priority). It uses a min-heap
internally with negated priorities so that the highest priority items
are dequeued first.
"""

from __future__ import annotations

import heapq
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class QueueItem:
    """An item in the priority queue.

    Attributes:
        id: Unique identifier for the queue item.
        path: File path associated with this item.
        priority: Priority level (higher number = higher priority).
        metadata: Optional metadata dictionary for additional context.
        enqueued_at: Timestamp when the item was added to the queue.
    """

    id: str
    path: Path
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    enqueued_at: float = field(default_factory=time.monotonic)


class PriorityQueue:
    """Thread-safe priority queue for file processing tasks.

    Items with higher priority numbers are dequeued first. Among items
    with equal priority, earlier-enqueued items are dequeued first (FIFO).

    The implementation uses a min-heap with negated priorities and a
    monotonically increasing sequence counter for stable ordering.
    """

    def __init__(self) -> None:
        """Create an empty thread-safe priority queue."""
        self._heap: list[tuple[int, int, QueueItem]] = []
        self._lock = threading.Lock()
        self._counter = 0
        self._item_map: dict[str, tuple[int, int, QueueItem]] = {}

    @property
    def size(self) -> int:
        """Return the number of active items in the queue."""
        with self._lock:
            return len(self._item_map)

    @property
    def is_empty(self) -> bool:
        """Return True if the queue has no active items."""
        return self.size == 0

    def enqueue(self, item: QueueItem, priority: int | None = None) -> None:
        """Add an item to the queue.

        If *priority* is provided it overrides ``item.priority``.
        If an item with the same id already exists, it is replaced with
        the new priority and metadata.

        Args:
            item: The queue item to add.
            priority: Optional priority override. If ``None``,
                ``item.priority`` is used.
        """
        if priority is not None:
            item.priority = priority

        with self._lock:
            entry = (-item.priority, self._counter, item)
            self._counter += 1
            heapq.heappush(self._heap, entry)
            self._item_map[item.id] = entry

    def dequeue(self) -> QueueItem | None:
        """Remove and return the highest-priority item.

        Returns:
            The highest-priority :class:`QueueItem`, or ``None`` if the
            queue is empty.
        """
        with self._lock:
            return self._dequeue_locked()

    def _dequeue_locked(self) -> QueueItem | None:
        """Internal dequeue that assumes the lock is already held."""
        while self._heap:
            entry = heapq.heappop(self._heap)
            neg_priority, counter, item = entry

            # Check if this is the current valid entry for this item
            current_entry = self._item_map.get(item.id)
            if current_entry is not entry:
                continue

            del self._item_map[item.id]
            return item
        return None

    def peek(self) -> QueueItem | None:
        """Return the highest-priority item without removing it.

        Returns:
            The highest-priority :class:`QueueItem`, or ``None`` if the
            queue is empty.
        """
        with self._lock:
            while self._heap:
                entry = self._heap[0]
                neg_priority, counter, item = entry

                # Check validity against item map
                current_entry = self._item_map.get(item.id)
                if current_entry is not entry:
                    # Stale entry at top of heap, remove it
                    heapq.heappop(self._heap)
                    continue
                return item
            return None

    def reorder(self, item_id: str, new_priority: int) -> bool:
        """Change the priority of an existing item.

        The item is logically removed and re-inserted with the new priority.

        Args:
            item_id: The id of the item to reorder.
            new_priority: The new priority value.

        Returns:
            ``True`` if the item was found and reordered, ``False`` if the
            item is not in the queue.
        """
        with self._lock:
            if item_id not in self._item_map:
                return False

            old_entry = self._item_map[item_id]
            item = old_entry[2]
            item.priority = new_priority

            # Push new entry
            entry = (-new_priority, self._counter, item)
            self._counter += 1
            heapq.heappush(self._heap, entry)
            self._item_map[item_id] = entry
            return True

    def remove(self, item_id: str) -> bool:
        """Remove an item from the queue by id.

        Args:
            item_id: The id of the item to remove.

        Returns:
            ``True`` if the item was found and removed, ``False`` otherwise.
        """
        with self._lock:
            if item_id not in self._item_map:
                return False
            del self._item_map[item_id]
            return True

    def clear(self) -> None:
        """Remove all items from the queue."""
        with self._lock:
            self._heap.clear()
            self._item_map.clear()
            self._counter = 0

    def items(self) -> list[QueueItem]:
        """Return all active items sorted by priority (highest first).

        Returns:
            List of :class:`QueueItem` sorted by descending priority.
        """
        with self._lock:
            active = [entry[2] for entry in self._item_map.values()]
        return sorted(active, key=lambda item: -item.priority)
