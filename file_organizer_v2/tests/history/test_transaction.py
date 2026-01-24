"""
Tests for transaction context manager.
"""

import tempfile
from pathlib import Path

import pytest

from file_organizer.history.models import OperationStatus, OperationType
from file_organizer.history.tracker import OperationHistory
from file_organizer.history.transaction import OperationTransaction


class TestOperationTransaction:
    """Test suite for OperationTransaction."""

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

    def test_context_manager_commit(self, history):
        """Test that transaction commits on successful exit."""
        with OperationTransaction(history) as txn:
            txn.log_move(Path('/test/source'), Path('/test/dest'))

        # Verify transaction was committed
        transaction = history.get_transaction(txn.transaction_id)
        assert transaction is not None
        assert transaction.status.value == 'completed'

    def test_context_manager_rollback_on_exception(self, history):
        """Test that transaction rolls back on exception."""
        try:
            with OperationTransaction(history) as txn:
                txn.log_move(Path('/test/source'), Path('/test/dest'))
                raise ValueError("Test error")
        except ValueError:
            pass

        # Verify transaction was rolled back
        transaction = history.get_transaction(txn.transaction_id)
        assert transaction.status.value == 'failed'

        # Verify operations were marked as rolled back
        operations = history.get_operations(transaction_id=txn.transaction_id)
        assert all(op.status == OperationStatus.ROLLED_BACK for op in operations)

    def test_log_operation(self, history):
        """Test logging operation within transaction."""
        with OperationTransaction(history) as txn:
            operation_id = txn.log_operation(
                operation_type=OperationType.MOVE,
                source_path=Path('/test/source'),
                destination_path=Path('/test/dest')
            )

            assert operation_id > 0

        # Verify operation was logged with transaction ID
        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].transaction_id == txn.transaction_id

    def test_log_move(self, history):
        """Test log_move convenience method."""
        with OperationTransaction(history) as txn:
            txn.log_move(Path('/test/source'), Path('/test/dest'))

        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].operation_type == OperationType.MOVE
        assert operations[0].source_path == Path('/test/source')
        assert operations[0].destination_path == Path('/test/dest')

    def test_log_rename(self, history):
        """Test log_rename convenience method."""
        with OperationTransaction(history) as txn:
            txn.log_rename(Path('/test/old'), Path('/test/new'))

        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].operation_type == OperationType.RENAME

    def test_log_delete(self, history):
        """Test log_delete convenience method."""
        with OperationTransaction(history) as txn:
            txn.log_delete(Path('/test/file'))

        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].operation_type == OperationType.DELETE
        assert operations[0].destination_path is None

    def test_log_copy(self, history):
        """Test log_copy convenience method."""
        with OperationTransaction(history) as txn:
            txn.log_copy(Path('/test/source'), Path('/test/dest'))

        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].operation_type == OperationType.COPY

    def test_log_create(self, history):
        """Test log_create convenience method."""
        with OperationTransaction(history) as txn:
            txn.log_create(Path('/test/new_file'))

        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].operation_type == OperationType.CREATE

    def test_log_failed_operation(self, history):
        """Test logging failed operation."""
        with OperationTransaction(history) as txn:
            txn.log_failed_operation(
                operation_type=OperationType.MOVE,
                source_path=Path('/test/source'),
                error_message="Permission denied"
            )

        operations = history.get_operations()
        assert len(operations) == 1
        assert operations[0].status == OperationStatus.FAILED
        assert operations[0].error_message == "Permission denied"

    def test_multiple_operations_in_transaction(self, history):
        """Test logging multiple operations in a single transaction."""
        with OperationTransaction(history) as txn:
            txn.log_move(Path('/test/file1'), Path('/test/dest1'))
            txn.log_rename(Path('/test/file2'), Path('/test/file2_new'))
            txn.log_delete(Path('/test/file3'))

        # Verify all operations share the same transaction ID
        operations = history.get_operations()
        assert len(operations) == 3
        assert all(op.transaction_id == txn.transaction_id for op in operations)

        # Verify transaction operation count
        transaction = history.get_transaction(txn.transaction_id)
        assert transaction.operation_count == 3

    def test_manual_commit(self, history):
        """Test manual commit of transaction."""
        with OperationTransaction(history) as txn:
            txn.log_move(Path('/test/source'), Path('/test/dest'))
            result = txn.commit()
            assert result is True

        # Should still be committed after exit
        transaction = history.get_transaction(txn.transaction_id)
        assert transaction.status.value == 'completed'

    def test_manual_rollback(self, history):
        """Test manual rollback of transaction."""
        with OperationTransaction(history) as txn:
            txn.log_move(Path('/test/source'), Path('/test/dest'))
            result = txn.rollback()
            assert result is True

        # Should remain rolled back after exit
        transaction = history.get_transaction(txn.transaction_id)
        assert transaction.status.value == 'failed'

    def test_cannot_commit_twice(self, history):
        """Test that committing twice returns False."""
        with OperationTransaction(history) as txn:
            txn.log_move(Path('/test/source'), Path('/test/dest'))
            assert txn.commit() is True
            assert txn.commit() is False  # Second commit should fail

    def test_cannot_rollback_after_commit(self, history):
        """Test that rolling back after commit returns False."""
        with OperationTransaction(history) as txn:
            txn.log_move(Path('/test/source'), Path('/test/dest'))
            assert txn.commit() is True
            assert txn.rollback() is False  # Rollback should fail

    def test_cannot_commit_after_rollback(self, history):
        """Test that committing after rollback returns False."""
        with OperationTransaction(history) as txn:
            txn.log_move(Path('/test/source'), Path('/test/dest'))
            assert txn.rollback() is True
            assert txn.commit() is False  # Commit should fail

    def test_get_transaction_id(self, history):
        """Test getting transaction ID."""
        txn = OperationTransaction(history)
        assert txn.get_transaction_id() is None  # Before entering context

        with txn:
            transaction_id = txn.get_transaction_id()
            assert transaction_id is not None
            assert len(transaction_id) > 0

    def test_transaction_metadata(self, history):
        """Test transaction with metadata."""
        metadata = {'batch_name': 'test_batch', 'user': 'test_user'}

        with OperationTransaction(history, metadata=metadata) as txn:
            txn.log_move(Path('/test/source'), Path('/test/dest'))

        transaction = history.get_transaction(txn.transaction_id)
        assert transaction.metadata == metadata

    def test_log_operation_outside_context(self, history):
        """Test that logging operation outside context raises error."""
        txn = OperationTransaction(history)

        with pytest.raises(RuntimeError):
            txn.log_operation(OperationType.MOVE, Path('/test/source'))

    def test_nested_transactions_not_supported(self, history):
        """Test that nested transactions each get their own ID."""
        with OperationTransaction(history) as txn1:
            txn1.log_move(Path('/test/file1'), Path('/test/dest1'))

            with OperationTransaction(history) as txn2:
                txn2.log_move(Path('/test/file2'), Path('/test/dest2'))

                # Should have different transaction IDs
                assert txn1.transaction_id != txn2.transaction_id

        # Both should be committed
        txn1_record = history.get_transaction(txn1.transaction_id)
        txn2_record = history.get_transaction(txn2.transaction_id)
        assert txn1_record.status.value == 'completed'
        assert txn2_record.status.value == 'completed'
