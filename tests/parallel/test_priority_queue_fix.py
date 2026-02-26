import unittest
from pathlib import Path
import pytest

from file_organizer.parallel.priority_queue import PriorityQueue, QueueItem


@pytest.mark.unit
class TestPriorityQueueFix(unittest.TestCase):
    def test_reorder_duplicate_processing_bug(self):
        """
        Verify that reordering an item does not cause it to be processed twice.
        Regression test for Issue #291.
        """
        pq = PriorityQueue()
        item_id = "test_item"
        item = QueueItem(id=item_id, path=Path("/tmp/test"), priority=10)

        # 1. Enqueue item with priority 10
        pq.enqueue(item)

        # 2. Reorder item to priority 20
        # This pushes a new entry (priority 20) to the heap.
        # The old entry (priority 10) remains in the heap.
        res = pq.reorder(item_id, 20)
        self.assertTrue(res, "Reorder should succeed")

        # 3. Dequeue -> Should get priority 20
        first = pq.dequeue()
        self.assertIsNotNone(first)
        self.assertEqual(first.priority, 20, "Should dequeue the updated priority item first")

        # 4. Dequeue again -> Should NOT get the old stale entry
        second = pq.dequeue()
        self.assertIsNone(second, "Should not dequeue the stale entry")


if __name__ == "__main__":
    unittest.main()
