"""
Tests for operation tracker.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from file_organizer.history.tracker import OperationHistory
from file_organizer.history.models import OperationType, OperationStatus


class TestOperationHistory:
    """Test suite for OperationHistory."""

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
    def temp_file(self):
        """Create temporary file for testing."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            file_path = Path(f.name)
        yield file_path
        # Cleanup
        if file_path.exists():
            file_path.unlink()

    @pytest.fixture
    def history(self, temp_db_path):
        """Create OperationHistory instance."""
        hist = OperationHistory(temp_db_path)
        yield hist
        hist.close()

    def test_log_operation(self, history, temp_file):
        """Test logging an operation."""
        operation_id = history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=temp_file,
            destination_path=Path('/test/dest'),
            metadata={'test': 'data'}
        )

        assert operation_id > 0

        # Verify operation was logged
        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].operation_type == OperationType.MOVE
        assert operations[0].source_path == temp_file

    def test_log_operation_with_file_hash(self, history, temp_file):
        """Test that file hash is calculated for existing files."""
        operation_id = history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=temp_file
        )

        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].file_hash is not None
        # SHA256 hash should be 64 characters
        assert len(operations[0].file_hash) == 64

    def test_log_operation_with_metadata(self, history, temp_file):
        """Test that file metadata is collected."""
        operation_id = history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=temp_file
        )

        operations = history.get_operations()
        assert len(operations) == 1
        metadata = operations[0].metadata
        assert 'size' in metadata
        assert 'mode' in metadata
        assert 'mtime' in metadata
        assert metadata['is_file'] is True

    def test_start_transaction(self, history):
        """Test starting a transaction."""
        transaction_id = history.start_transaction(metadata={'test': 'data'})

        assert transaction_id is not None
        assert len(transaction_id) > 0  # UUID format

        # Verify transaction was created
        transaction = history.get_transaction(transaction_id)
        assert transaction is not None
        assert transaction.transaction_id == transaction_id

    def test_commit_transaction(self, history):
        """Test committing a transaction."""
        transaction_id = history.start_transaction()
        result = history.commit_transaction(transaction_id)

        assert result is True

        # Verify transaction status
        transaction = history.get_transaction(transaction_id)
        assert transaction.status.value == 'completed'
        assert transaction.completed_at is not None

    def test_rollback_transaction(self, history, temp_file):
        """Test rolling back a transaction."""
        transaction_id = history.start_transaction()

        # Log some operations in the transaction
        history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=temp_file,
            transaction_id=transaction_id
        )

        result = history.rollback_transaction(transaction_id)
        assert result is True

        # Verify transaction status
        transaction = history.get_transaction(transaction_id)
        assert transaction.status.value == 'failed'

        # Verify operations were marked as rolled back
        operations = history.get_operations(transaction_id=transaction_id)
        assert all(op.status == OperationStatus.ROLLED_BACK for op in operations)

    def test_get_operations_no_filters(self, history, temp_file):
        """Test getting operations without filters."""
        # Log multiple operations
        for i in range(3):
            history.log_operation(
                operation_type=OperationType.MOVE,
                source_path=Path(f'/test/path{i}')
            )

        operations = history.get_operations()
        assert len(operations) == 3

    def test_get_operations_by_type(self, history):
        """Test filtering operations by type."""
        # Log different operation types
        history.log_operation(OperationType.MOVE, Path('/test/path1'))
        history.log_operation(OperationType.RENAME, Path('/test/path2'))
        history.log_operation(OperationType.DELETE, Path('/test/path3'))

        # Filter by type
        move_ops = history.get_operations(operation_type=OperationType.MOVE)
        assert len(move_ops) == 1
        assert move_ops[0].operation_type == OperationType.MOVE

    def test_get_operations_by_transaction(self, history):
        """Test filtering operations by transaction ID."""
        transaction_id = history.start_transaction()

        # Log operations in transaction
        history.log_operation(
            OperationType.MOVE,
            Path('/test/path1'),
            transaction_id=transaction_id
        )
        history.log_operation(
            OperationType.MOVE,
            Path('/test/path2'),
            transaction_id=transaction_id
        )

        # Log operation outside transaction
        history.log_operation(OperationType.MOVE, Path('/test/path3'))

        # Filter by transaction
        txn_ops = history.get_operations(transaction_id=transaction_id)
        assert len(txn_ops) == 2

    def test_get_operations_by_status(self, history):
        """Test filtering operations by status."""
        # Log operations with different statuses
        history.log_operation(
            OperationType.MOVE,
            Path('/test/path1'),
            status=OperationStatus.COMPLETED
        )
        history.log_operation(
            OperationType.MOVE,
            Path('/test/path2'),
            status=OperationStatus.FAILED,
            error_message="Test error"
        )

        # Filter by status
        failed_ops = history.get_operations(status=OperationStatus.FAILED)
        assert len(failed_ops) == 1
        assert failed_ops[0].status == OperationStatus.FAILED

    def test_get_operations_by_date_range(self, history):
        """Test filtering operations by date range."""
        # Log operations with different timestamps
        now = datetime.utcnow()
        yesterday = now - timedelta(days=1)
        tomorrow = now + timedelta(days=1)

        history.log_operation(OperationType.MOVE, Path('/test/path1'))

        # Filter by date range
        ops = history.get_operations(
            start_date=yesterday,
            end_date=tomorrow
        )
        assert len(ops) == 1

    def test_get_operations_with_limit(self, history):
        """Test limiting number of operations returned."""
        # Log multiple operations
        for i in range(10):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        # Get with limit
        ops = history.get_operations(limit=5)
        assert len(ops) == 5

    def test_get_recent_operations(self, history):
        """Test getting recent operations."""
        # Log multiple operations
        for i in range(5):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        recent = history.get_recent_operations(limit=3)
        assert len(recent) == 3

    def test_get_transaction(self, history):
        """Test getting transaction by ID."""
        transaction_id = history.start_transaction(metadata={'test': 'data'})

        transaction = history.get_transaction(transaction_id)
        assert transaction is not None
        assert transaction.transaction_id == transaction_id
        assert transaction.metadata == {'test': 'data'}

    def test_get_nonexistent_transaction(self, history):
        """Test getting nonexistent transaction returns None."""
        transaction = history.get_transaction('nonexistent-id')
        assert transaction is None

    def test_transaction_operation_count(self, history):
        """Test that transaction operation count is updated."""
        transaction_id = history.start_transaction()

        # Log operations
        for i in range(3):
            history.log_operation(
                OperationType.MOVE,
                Path(f'/test/path{i}'),
                transaction_id=transaction_id
            )

        transaction = history.get_transaction(transaction_id)
        assert transaction.operation_count == 3

    def test_context_manager(self, temp_db_path):
        """Test OperationHistory as context manager."""
        with OperationHistory(temp_db_path) as history:
            history.log_operation(OperationType.MOVE, Path('/test/path'))

        # Should close cleanly

    def test_log_failed_operation(self, history):
        """Test logging a failed operation."""
        operation_id = history.log_operation(
            operation_type=OperationType.MOVE,
            source_path=Path('/test/source'),
            status=OperationStatus.FAILED,
            error_message="Permission denied"
        )

        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].status == OperationStatus.FAILED
        assert operations[0].error_message == "Permission denied"
