"""
Unit tests for HistoryViewer.

Tests history viewing and filtering functionality.
"""

import unittest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from io import StringIO
import sys

from file_organizer.history.tracker import OperationHistory
from file_organizer.history.models import OperationType, OperationStatus
from file_organizer.undo.viewer import HistoryViewer


class TestHistoryViewer(unittest.TestCase):
    """Test cases for HistoryViewer."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "test_history.db"
        self.history = OperationHistory(db_path=self.db_path)
        self.viewer = HistoryViewer(history=self.history)

        # Create test files and log operations
        self.source1 = self.test_dir / "file1.txt"
        self.dest1 = self.test_dir / "dest1.txt"
        self.source1.write_text("content1")
        shutil.move(str(self.source1), str(self.dest1))
        self.op1_id = self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=self.source1,
            destination_path=self.dest1
        )

        self.source2 = self.test_dir / "file2.txt"
        self.dest2 = self.test_dir / "dest2.txt"
        self.source2.write_text("content2")
        self.source2.rename(self.dest2)
        self.op2_id = self.history.log_operation(
            operation_type=OperationType.RENAME,
            source_path=self.source2,
            destination_path=self.dest2
        )

    def tearDown(self):
        """Clean up test fixtures."""
        self.viewer.close()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_show_recent_operations(self):
        """Test showing recent operations."""
        # Capture output
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        self.viewer.show_recent_operations(limit=10)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("operations", output.lower())
        self.assertIn("file1.txt", output)
        self.assertIn("file2.txt", output)

    def test_show_operation_details(self):
        """Test showing details of specific operation."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        self.viewer.show_operation_details(self.op1_id)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn(str(self.op1_id), output)
        self.assertIn("move", output.lower())
        self.assertIn("file1.txt", output)

    def test_show_transaction_details(self):
        """Test showing transaction details."""
        # Create transaction
        txn_id = self.history.start_transaction(metadata={"test": "txn"})
        file3 = self.test_dir / "file3.txt"
        dest3 = self.test_dir / "dest3.txt"
        file3.write_text("content3")
        shutil.move(str(file3), str(dest3))
        self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=file3,
            destination_path=dest3,
            transaction_id=txn_id
        )
        self.history.commit_transaction(txn_id)

        old_stdout = sys.stdout
        sys.stdout = StringIO()

        self.viewer.show_transaction_details(txn_id)

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn(txn_id, output)
        self.assertIn("file3.txt", output)

    def test_filter_operations_by_type(self):
        """Test filtering operations by type."""
        operations = self.viewer.filter_operations(operation_type="move")

        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0].operation_type, OperationType.MOVE)

    def test_filter_operations_by_status(self):
        """Test filtering operations by status."""
        operations = self.viewer.filter_operations(status="completed")

        self.assertEqual(len(operations), 2)
        self.assertTrue(all(op.status == OperationStatus.COMPLETED for op in operations))

    def test_search_by_path(self):
        """Test searching operations by path."""
        operations = self.viewer.search_by_path("file1.txt")

        self.assertGreater(len(operations), 0)
        self.assertTrue(any("file1.txt" in str(op.source_path) for op in operations))

    def test_display_filtered_operations(self):
        """Test displaying filtered operations."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        self.viewer.display_filtered_operations(operation_type="move")

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("found", output.lower())
        self.assertIn("file1.txt", output)

    def test_get_statistics(self):
        """Test getting statistics."""
        stats = self.viewer.get_statistics()

        self.assertEqual(stats['total_operations'], 2)
        self.assertEqual(stats['by_type']['move'], 1)
        self.assertEqual(stats['by_type']['rename'], 1)
        self.assertEqual(stats['by_status']['completed'], 2)

    def test_show_statistics(self):
        """Test showing statistics."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        self.viewer.show_statistics()

        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("Statistics", output)
        self.assertIn("Total operations: 2", output)

    def test_format_status(self):
        """Test status formatting."""
        completed = self.viewer._format_status(OperationStatus.COMPLETED)
        rolled_back = self.viewer._format_status(OperationStatus.ROLLED_BACK)
        failed = self.viewer._format_status(OperationStatus.FAILED)

        self.assertIn("✓", completed)
        self.assertIn("↶", rolled_back)
        self.assertIn("✗", failed)

    def test_format_datetime(self):
        """Test datetime formatting."""
        dt = datetime(2024, 1, 15, 14, 30, 45)
        formatted = self.viewer._format_datetime(dt)

        self.assertEqual(formatted, "2024-01-15 14:30:45")

    def test_parse_date_iso_format(self):
        """Test parsing ISO format date."""
        date_str = "2024-01-15T14:30:45Z"
        parsed = self.viewer._parse_date(date_str)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.month, 1)
        self.assertEqual(parsed.day, 15)

    def test_parse_date_simple_format(self):
        """Test parsing simple date format."""
        date_str = "2024-01-15"
        parsed = self.viewer._parse_date(date_str)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.month, 1)
        self.assertEqual(parsed.day, 15)

    def test_filter_operations_with_date_range(self):
        """Test filtering with date range."""
        # Use recent dates
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        tomorrow = today + timedelta(days=1)

        operations = self.viewer.filter_operations(
            since=yesterday.strftime("%Y-%m-%d"),
            until=tomorrow.strftime("%Y-%m-%d")
        )

        # Should include our test operations (logged today)
        self.assertGreater(len(operations), 0)


if __name__ == '__main__':
    unittest.main()
