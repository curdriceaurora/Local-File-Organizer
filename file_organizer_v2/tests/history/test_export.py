"""
Tests for history export functionality.
"""

import pytest
import tempfile
import json
import csv
from pathlib import Path
from datetime import datetime
from file_organizer.history.tracker import OperationHistory
from file_organizer.history.export import HistoryExporter
from file_organizer.history.models import OperationType


class TestHistoryExporter:
    """Test suite for HistoryExporter."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database path."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = Path(f.name)
        yield db_path
        # Cleanup
        if db_path.exists():
            db_path.unlink()
        # Clean up WAL and SHM files
        for suffix in ['-wal', '-shm']:
            wal_file = Path(str(db_path) + suffix)
            if wal_file.exists():
                wal_file.unlink()

    @pytest.fixture
    def history(self, temp_db_path):
        """Create OperationHistory instance."""
        hist = OperationHistory(temp_db_path)
        yield hist
        hist.close()

    @pytest.fixture
    def exporter(self, history):
        """Create HistoryExporter instance."""
        return HistoryExporter(history.db)

    @pytest.fixture
    def temp_output_dir(self):
        """Create temporary output directory."""
        import tempfile
        temp_dir = Path(tempfile.mkdtemp())
        yield temp_dir
        # Cleanup
        import shutil
        if temp_dir.exists():
            shutil.rmtree(temp_dir)

    def test_export_to_json(self, history, exporter, temp_output_dir):
        """Test exporting operations to JSON."""
        # Add some operations
        for i in range(5):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        output_path = temp_output_dir / 'export.json'
        stats = exporter.export_to_json(output_path)

        assert stats['operations_exported'] == 5
        assert output_path.exists()

        # Verify JSON structure
        with open(output_path, 'r') as f:
            data = json.load(f)

        assert 'export_date' in data
        assert 'operation_count' in data
        assert 'operations' in data
        assert len(data['operations']) == 5

    def test_export_to_json_with_transactions(self, history, exporter, temp_output_dir):
        """Test exporting operations with transaction details."""
        # Create transaction with operations
        txn_id = history.start_transaction()
        history.log_operation(
            OperationType.MOVE,
            Path('/test/path1'),
            transaction_id=txn_id
        )
        history.log_operation(
            OperationType.MOVE,
            Path('/test/path2'),
            transaction_id=txn_id
        )
        history.commit_transaction(txn_id)

        output_path = temp_output_dir / 'export.json'
        stats = exporter.export_to_json(output_path, include_transactions=True)

        # Verify transactions are included
        with open(output_path, 'r') as f:
            data = json.load(f)

        assert 'transactions' in data
        assert len(data['transactions']) == 1
        assert data['transactions'][0]['transaction_id'] == txn_id

    def test_export_to_json_filter_by_type(self, history, exporter, temp_output_dir):
        """Test exporting with operation type filter."""
        # Add different operation types
        history.log_operation(OperationType.MOVE, Path('/test/path1'))
        history.log_operation(OperationType.RENAME, Path('/test/path2'))
        history.log_operation(OperationType.DELETE, Path('/test/path3'))

        output_path = temp_output_dir / 'export.json'
        stats = exporter.export_to_json(output_path, operation_type=OperationType.MOVE)

        assert stats['operations_exported'] == 1

        with open(output_path, 'r') as f:
            data = json.load(f)

        assert all(op['operation_type'] == 'move' for op in data['operations'])

    def test_export_to_csv(self, history, exporter, temp_output_dir):
        """Test exporting operations to CSV."""
        # Add some operations
        for i in range(5):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        output_path = temp_output_dir / 'export.csv'
        count = exporter.export_to_csv(output_path)

        assert count == 5
        assert output_path.exists()

        # Verify CSV structure
        with open(output_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5
        assert 'id' in rows[0]
        assert 'operation_type' in rows[0]
        assert 'source_path' in rows[0]

    def test_export_to_csv_filter_by_type(self, history, exporter, temp_output_dir):
        """Test CSV export with operation type filter."""
        # Add different operation types
        history.log_operation(OperationType.MOVE, Path('/test/path1'))
        history.log_operation(OperationType.RENAME, Path('/test/path2'))
        history.log_operation(OperationType.DELETE, Path('/test/path3'))

        output_path = temp_output_dir / 'export.csv'
        count = exporter.export_to_csv(output_path, operation_type=OperationType.MOVE)

        assert count == 1

        with open(output_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]['operation_type'] == 'move'

    def test_export_to_csv_empty(self, history, exporter, temp_output_dir):
        """Test CSV export with no operations."""
        output_path = temp_output_dir / 'export.csv'
        count = exporter.export_to_csv(output_path)

        assert count == 0

    def test_export_transactions_to_csv(self, history, exporter, temp_output_dir):
        """Test exporting transactions to CSV."""
        # Create transactions
        for i in range(3):
            txn_id = history.start_transaction()
            history.log_operation(
                OperationType.MOVE,
                Path(f'/test/path{i}'),
                transaction_id=txn_id
            )
            history.commit_transaction(txn_id)

        output_path = temp_output_dir / 'transactions.csv'
        count = exporter.export_transactions_to_csv(output_path)

        assert count == 3
        assert output_path.exists()

        # Verify CSV structure
        with open(output_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 3
        assert 'transaction_id' in rows[0]
        assert 'started_at' in rows[0]
        assert 'operation_count' in rows[0]

    def test_export_statistics(self, history, exporter, temp_output_dir):
        """Test exporting database statistics."""
        # Add various operations
        history.log_operation(OperationType.MOVE, Path('/test/path1'))
        history.log_operation(OperationType.RENAME, Path('/test/path2'))
        history.log_operation(OperationType.DELETE, Path('/test/path3'))

        output_path = temp_output_dir / 'stats.json'
        result = exporter.export_statistics(output_path)

        assert result is True
        assert output_path.exists()

        # Verify statistics structure
        with open(output_path, 'r') as f:
            stats = json.load(f)

        assert 'total_operations' in stats
        assert 'database_size_mb' in stats
        assert 'operations_move' in stats
        assert 'operations_rename' in stats
        assert 'operations_delete' in stats
        assert 'export_date' in stats
        assert stats['total_operations'] == 3

    def test_export_creates_parent_directory(self, history, exporter, temp_output_dir):
        """Test that export creates parent directories if needed."""
        # Add operation
        history.log_operation(OperationType.MOVE, Path('/test/path'))

        # Use nested path that doesn't exist
        output_path = temp_output_dir / 'nested' / 'dir' / 'export.json'
        exporter.export_to_json(output_path)

        assert output_path.exists()
        assert output_path.parent.exists()

    def test_export_date_range_filter(self, history, exporter, temp_output_dir):
        """Test exporting with date range filter."""
        # Add operations (will have current timestamp)
        for i in range(5):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        # Export with date range that includes current time
        from datetime import timedelta
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        output_path = temp_output_dir / 'export.json'
        stats = exporter.export_to_json(
            output_path,
            start_date=yesterday,
            end_date=tomorrow
        )

        assert stats['operations_exported'] == 5
