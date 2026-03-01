"""
Unit tests for HistoryViewer.

Tests history viewing and filtering functionality.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

import pytest

from file_organizer.history.models import OperationStatus, OperationType
from file_organizer.history.tracker import OperationHistory
from file_organizer.undo.viewer import HistoryViewer


@pytest.mark.unit
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
            operation_type=OperationType.MOVE, source_path=self.source1, destination_path=self.dest1
        )

        self.source2 = self.test_dir / "file2.txt"
        self.dest2 = self.test_dir / "dest2.txt"
        self.source2.write_text("content2")
        self.source2.rename(self.dest2)
        self.op2_id = self.history.log_operation(
            operation_type=OperationType.RENAME,
            source_path=self.source2,
            destination_path=self.dest2,
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
            transaction_id=txn_id,
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

        self.assertEqual(stats["total_operations"], 2)
        self.assertEqual(stats["by_type"]["move"], 1)
        self.assertEqual(stats["by_type"]["rename"], 1)
        self.assertEqual(stats["by_status"]["completed"], 2)

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
        dt = datetime(2024, 1, 15, 14, 30, 45, tzinfo=UTC)
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
        # Use UTC dates to match stored timestamps
        today = datetime.now(tz=UTC)
        yesterday = today - timedelta(days=2)
        tomorrow = today + timedelta(days=2)

        operations = self.viewer.filter_operations(
            since=yesterday.strftime("%Y-%m-%d"), until=tomorrow.strftime("%Y-%m-%d")
        )

        # Should include our test operations (logged today)
        self.assertGreater(len(operations), 0)


    # --- Extended coverage tests ---

    def test_show_recent_operations_empty(self):
        """Test show_recent_operations with no operations."""
        empty_dir = self.test_dir / "empty_db"
        empty_dir.mkdir()
        empty_history = OperationHistory(db_path=empty_dir / "empty.db")
        empty_viewer = HistoryViewer(history=empty_history)

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        empty_viewer.show_recent_operations()
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("No operations found", output)
        empty_viewer.close()

    def test_show_operation_details_not_found(self):
        """Test show_operation_details with non-existent operation."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        self.viewer.show_operation_details(999999)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("999999", output)
        self.assertIn("not found", output)

    def test_show_operation_details_with_metadata(self):
        """Test show_operation_details displays metadata."""
        file4 = self.test_dir / "file4.txt"
        dest4 = self.test_dir / "dest4.txt"
        file4.write_text("content4")
        shutil.move(str(file4), str(dest4))
        op_id = self.history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=file4,
            destination_path=dest4,
            metadata={"reason": "organize", "priority": "high"},
        )

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        self.viewer.show_operation_details(op_id)
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("Metadata", output)
        self.assertIn("reason", output)
        self.assertIn("organize", output)

    def test_show_transaction_details_not_found(self):
        """Test show_transaction_details with non-existent transaction."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        self.viewer.show_transaction_details("nonexistent-txn-id")
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("nonexistent-txn-id", output)
        self.assertIn("not found", output)

    def test_filter_operations_invalid_type(self):
        """Test filter_operations with invalid operation type."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        operations = self.viewer.filter_operations(operation_type="invalid_type")
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertEqual(operations, [])
        self.assertIn("Invalid operation type", output)

    def test_filter_operations_invalid_status(self):
        """Test filter_operations with invalid status."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        operations = self.viewer.filter_operations(status="invalid_status")
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertEqual(operations, [])
        self.assertIn("Invalid status", output)

    def test_display_filtered_operations_with_search(self):
        """Test display_filtered_operations with search parameter."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        self.viewer.display_filtered_operations(search="file1.txt")
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("file1.txt", output)
        self.assertIn("operations found affecting path", output)

    def test_display_filtered_operations_search_no_results(self):
        """Test display_filtered_operations with search that returns nothing."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        self.viewer.display_filtered_operations(search="nonexistent_file.xyz")
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("No operations found affecting path", output)

    def test_display_filtered_operations_no_matching_filters(self):
        """Test display_filtered_operations with no matching results."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        self.viewer.display_filtered_operations(operation_type="create")
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIn("No operations found matching the filters", output)

    def test_parse_date_slash_format(self):
        """Test parsing date with Y/m/d format."""
        parsed = self.viewer._parse_date("2024/06/15")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.month, 6)
        self.assertEqual(parsed.day, 15)

    def test_parse_date_dmy_dash_format(self):
        """Test parsing date with d-m-Y format."""
        parsed = self.viewer._parse_date("15-06-2024")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.month, 6)
        self.assertEqual(parsed.day, 15)

    def test_parse_date_dmy_slash_format(self):
        """Test parsing date with d/m/Y format."""
        parsed = self.viewer._parse_date("15/06/2024")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2024)
        self.assertEqual(parsed.month, 6)
        self.assertEqual(parsed.day, 15)

    def test_parse_date_datetime_with_seconds(self):
        """Test parsing date with Y-m-d H:M:S format."""
        parsed = self.viewer._parse_date("2024-01-15 14:30:45")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.hour, 14)
        self.assertEqual(parsed.minute, 30)
        self.assertEqual(parsed.second, 45)

    def test_parse_date_datetime_without_seconds(self):
        """Test parsing date with Y-m-d H:M format."""
        parsed = self.viewer._parse_date("2024-01-15 14:30")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.hour, 14)
        self.assertEqual(parsed.minute, 30)

    def test_parse_date_invalid_format(self):
        """Test parsing date with unparseable format."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        parsed = self.viewer._parse_date("not-a-date")
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout

        self.assertIsNone(parsed)
        self.assertIn("Warning", output)
        self.assertIn("Could not parse date", output)

    def test_format_path_with_destination(self):
        """Test _format_path with destination path."""
        operations = self.history.get_operations(limit=10)
        move_op = next(
            (op for op in operations if op.destination_path is not None), None
        )
        self.assertIsNotNone(move_op)

        formatted = self.viewer._format_path(move_op)
        self.assertIn("→", formatted)

    def test_format_path_without_destination(self):
        """Test _format_path without destination (e.g., delete)."""
        from unittest.mock import MagicMock

        mock_op = MagicMock()
        mock_op.source_path = Path("/some/dir/file.txt")
        mock_op.destination_path = None

        formatted = self.viewer._format_path(mock_op)
        self.assertEqual(formatted, "file.txt")
        self.assertNotIn("→", formatted)

    def test_context_manager(self):
        """Test HistoryViewer context manager."""
        db_path = self.test_dir / "ctx_test.db"
        history = OperationHistory(db_path=db_path)
        with HistoryViewer(history=history) as viewer:
            self.assertIsNotNone(viewer)

    def test_format_datetime_short(self):
        """Test short datetime formatting."""
        dt = datetime(2024, 3, 20, 10, 5, 30, tzinfo=UTC)
        formatted = self.viewer._format_datetime_short(dt)
        self.assertEqual(formatted, "2024-03-20 10:05:30")


if __name__ == "__main__":
    unittest.main()
