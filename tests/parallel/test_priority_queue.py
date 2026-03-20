"""
Unit tests for the PriorityQueue.

Tests thread-safe priority queue operations including enqueue, dequeue,
peek, reorder, and concurrent access patterns.
"""

from __future__ import annotations

import threading
import unittest
from pathlib import Path

import pytest

from file_organizer.parallel.priority_queue import PriorityQueue, QueueItem


@pytest.mark.unit
class TestQueueItem(unittest.TestCase):
    """Test cases for QueueItem dataclass."""

    def test_create_with_defaults(self) -> None:
        """Test creating a QueueItem with default values."""
        item = QueueItem(id="item-1", path=Path("/tmp/test.txt"))
        self.assertEqual(item.id, "item-1")
        self.assertEqual(item.path, Path("/tmp/test.txt"))
        self.assertEqual(item.priority, 0)
        self.assertEqual(item.metadata, {})
        self.assertIsInstance(item.enqueued_at, float)

    def test_create_with_all_fields(self) -> None:
        """Test creating a QueueItem with all fields specified."""
        item = QueueItem(
            id="item-2",
            path=Path("/tmp/doc.pdf"),
            priority=5,
            metadata={"type": "document"},
            enqueued_at=100.0,
        )
        self.assertEqual(item.priority, 5)
        self.assertEqual(item.metadata, {"type": "document"})
        self.assertEqual(item.enqueued_at, 100.0)

    def test_metadata_isolation(self) -> None:
        """Test that default metadata dicts are independent."""
        item1 = QueueItem(id="a", path=Path("/a"))
        item2 = QueueItem(id="b", path=Path("/b"))
        item1.metadata["key"] = "value"
        self.assertNotIn("key", item2.metadata)


@pytest.mark.unit
class TestPriorityQueue(unittest.TestCase):
    """Test cases for PriorityQueue."""

    def setUp(self) -> None:
        """Set up a fresh queue for each test."""
        self.queue = PriorityQueue()

    def _make_item(self, item_id: str, priority: int = 0) -> QueueItem:
        """Helper to create a QueueItem."""
        return QueueItem(
            id=item_id,
            path=Path(f"/tmp/{item_id}.txt"),
            priority=priority,
        )

    def test_empty_queue(self) -> None:
        """Test that a new queue is empty."""
        self.assertTrue(self.queue.is_empty)
        self.assertEqual(self.queue.size, 0)

    def test_enqueue_single(self) -> None:
        """Test enqueuing a single item."""
        item = self._make_item("item-1", priority=5)
        self.queue.enqueue(item)
        self.assertFalse(self.queue.is_empty)
        self.assertEqual(self.queue.size, 1)

    def test_dequeue_returns_highest_priority(self) -> None:
        """Test that dequeue returns the highest priority item."""
        self.queue.enqueue(self._make_item("low", priority=1))
        self.queue.enqueue(self._make_item("high", priority=10))
        self.queue.enqueue(self._make_item("mid", priority=5))

        result = self.queue.dequeue()
        self.assertIsNotNone(result)
        self.assertEqual(result.id, "high")
        self.assertEqual(result.priority, 10)

    def test_dequeue_fifo_on_equal_priority(self) -> None:
        """Test FIFO ordering for items with equal priority."""
        self.queue.enqueue(self._make_item("first", priority=5))
        self.queue.enqueue(self._make_item("second", priority=5))
        self.queue.enqueue(self._make_item("third", priority=5))

        result1 = self.queue.dequeue()
        result2 = self.queue.dequeue()
        result3 = self.queue.dequeue()

        self.assertEqual(result1.id, "first")
        self.assertEqual(result2.id, "second")
        self.assertEqual(result3.id, "third")

    def test_dequeue_empty_returns_none(self) -> None:
        """Test that dequeue on empty queue returns None."""
        result = self.queue.dequeue()
        self.assertIsNone(result)

    def test_peek_returns_highest_without_removing(self) -> None:
        """Test peek returns highest priority item without removing it."""
        self.queue.enqueue(self._make_item("low", priority=1))
        self.queue.enqueue(self._make_item("high", priority=10))

        result = self.queue.peek()
        self.assertIsNotNone(result)
        self.assertEqual(result.id, "high")
        # Item should still be in queue
        self.assertEqual(self.queue.size, 2)

    def test_peek_empty_returns_none(self) -> None:
        """Test peek on empty queue returns None."""
        self.assertIsNone(self.queue.peek())

    def test_enqueue_with_priority_override(self) -> None:
        """Test that priority parameter overrides item priority."""
        item = self._make_item("item-1", priority=1)
        self.queue.enqueue(item, priority=100)
        result = self.queue.peek()
        self.assertEqual(result.priority, 100)

    def test_reorder_existing_item(self) -> None:
        """Test reordering changes an item's priority."""
        self.queue.enqueue(self._make_item("a", priority=1))
        self.queue.enqueue(self._make_item("b", priority=10))

        # b is highest, reorder a to be higher
        result = self.queue.reorder("a", new_priority=20)
        self.assertTrue(result)

        top = self.queue.dequeue()
        self.assertEqual(top.id, "a")
        self.assertEqual(top.priority, 20)

    def test_reorder_nonexistent_returns_false(self) -> None:
        """Test reorder returns False for non-existent item."""
        result = self.queue.reorder("nonexistent", new_priority=5)
        self.assertFalse(result)

    def test_remove_existing_item(self) -> None:
        """Test removing an item from the queue."""
        self.queue.enqueue(self._make_item("a", priority=1))
        self.queue.enqueue(self._make_item("b", priority=5))

        result = self.queue.remove("a")
        self.assertTrue(result)
        self.assertEqual(self.queue.size, 1)

        top = self.queue.dequeue()
        self.assertEqual(top.id, "b")

    def test_remove_nonexistent_returns_false(self) -> None:
        """Test remove returns False for non-existent item."""
        result = self.queue.remove("nonexistent")
        self.assertFalse(result)

    def test_clear(self) -> None:
        """Test clearing the queue removes all items."""
        for i in range(10):
            self.queue.enqueue(self._make_item(f"item-{i}", priority=i))
        self.assertEqual(self.queue.size, 10)

        self.queue.clear()
        self.assertTrue(self.queue.is_empty)
        self.assertEqual(self.queue.size, 0)
        self.assertIsNone(self.queue.dequeue())

    def test_items_returns_sorted_active_items(self) -> None:
        """Test items returns all active items sorted by priority descending."""
        self.queue.enqueue(self._make_item("low", priority=1))
        self.queue.enqueue(self._make_item("high", priority=10))
        self.queue.enqueue(self._make_item("mid", priority=5))

        items = self.queue.items()
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].id, "high")
        self.assertEqual(items[1].id, "mid")
        self.assertEqual(items[2].id, "low")

    def test_enqueue_duplicate_id_replaces(self) -> None:
        """Test that enqueuing a duplicate id replaces the old entry."""
        self.queue.enqueue(self._make_item("a", priority=1))
        self.assertEqual(self.queue.size, 1)

        self.queue.enqueue(self._make_item("a", priority=10))
        self.assertEqual(self.queue.size, 1)

        top = self.queue.dequeue()
        self.assertEqual(top.id, "a")
        self.assertEqual(top.priority, 10)

    def test_full_drain(self) -> None:
        """Test dequeuing all items empties the queue."""
        for i in range(5):
            self.queue.enqueue(self._make_item(f"item-{i}", priority=i))

        results = []
        while not self.queue.is_empty:
            item = self.queue.dequeue()
            if item is not None:
                results.append(item.id)

        self.assertEqual(len(results), 5)
        self.assertTrue(self.queue.is_empty)
        # Highest priority first
        self.assertEqual(results[0], "item-4")

    def test_thread_safety_concurrent_enqueue_dequeue(self) -> None:
        """Test that concurrent enqueue and dequeue do not corrupt state."""
        errors: list[str] = []

        def producer(start: int) -> None:
            try:
                for i in range(50):
                    item = self._make_item(f"producer-{start}-{i}", priority=i)
                    self.queue.enqueue(item)
            except Exception as exc:
                errors.append(str(exc))

        def consumer(results: list[QueueItem]) -> None:
            try:
                for _ in range(50):
                    item = self.queue.dequeue()
                    if item is not None:
                        results.append(item)
            except Exception as exc:
                errors.append(str(exc))

        consumed: list[QueueItem] = []
        threads = [
            threading.Thread(target=producer, args=(0,)),
            threading.Thread(target=producer, args=(1,)),
            threading.Thread(target=consumer, args=(consumed,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        # Verify no items are corrupted
        for item in consumed:
            self.assertIsInstance(item, QueueItem)

    def test_thread_safety_concurrent_reorder(self) -> None:
        """Test that concurrent reorder operations are safe."""
        for i in range(20):
            self.queue.enqueue(self._make_item(f"item-{i}", priority=i))

        errors: list[str] = []

        def reorderer(offset: int) -> None:
            try:
                for i in range(20):
                    self.queue.reorder(f"item-{i}", new_priority=i + offset)
            except Exception as exc:
                errors.append(str(exc))

        threads = [
            threading.Thread(target=reorderer, args=(100,)),
            threading.Thread(target=reorderer, args=(200,)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        # Queue should still have 20 items
        self.assertEqual(self.queue.size, 20)


if __name__ == "__main__":
    unittest.main()
