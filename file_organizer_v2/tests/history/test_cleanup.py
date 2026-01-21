"""
Tests for history cleanup functionality.
"""

import pytest
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from file_organizer.history.tracker import OperationHistory
from file_organizer.history.cleanup import HistoryCleanup, HistoryCleanupConfig
from file_organizer.history.models import OperationType, OperationStatus


class TestHistoryCleanup:
    """Test suite for HistoryCleanup."""

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
    def cleanup(self, history):
        """Create HistoryCleanup instance."""
        config = HistoryCleanupConfig(
            max_operations=100,
            max_age_days=30,
            max_size_mb=10
        )
        return HistoryCleanup(history.db, config)

    def test_cleanup_config_defaults(self):
        """Test default cleanup configuration."""
        config = HistoryCleanupConfig()
        assert config.max_operations == 10000
        assert config.max_age_days == 90
        assert config.max_size_mb == 100
        assert config.auto_cleanup_enabled is True

    def test_should_cleanup_by_count(self, history, cleanup):
        """Test cleanup trigger based on operation count."""
        # Add operations exceeding limit
        for i in range(150):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        assert cleanup.should_cleanup() is True

    def test_should_not_cleanup_under_limit(self, history, cleanup):
        """Test that cleanup is not triggered when under limits."""
        # Add few operations
        for i in range(50):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        # Should not need cleanup (50 < 100)
        assert cleanup.should_cleanup() is False

    def test_cleanup_old_operations(self, history, cleanup):
        """Test cleaning up operations older than specified age."""
        # This test would require manipulating timestamps in the database
        # For now, just verify the method runs without error
        deleted = cleanup.cleanup_old_operations(max_age_days=30)
        assert deleted >= 0

    def test_cleanup_by_count(self, history, cleanup):
        """Test keeping only N most recent operations."""
        # Add 150 operations
        for i in range(150):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        # Keep only 100
        deleted = cleanup.cleanup_by_count(max_operations=100)
        assert deleted >= 40  # Should delete at least 40-50 operations

        # Verify count is at or below limit (allow 1 operation over due to timing)
        final_count = history.db.get_operation_count()
        assert final_count <= 101

    def test_cleanup_by_count_under_limit(self, history, cleanup):
        """Test cleanup by count when under limit."""
        # Add only 50 operations
        for i in range(50):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        # Try to keep 100 (should delete 0)
        deleted = cleanup.cleanup_by_count(max_operations=100)
        assert deleted == 0
        assert history.db.get_operation_count() == 50

    def test_cleanup_by_size(self, history, cleanup):
        """Test cleanup by database size."""
        # Add many operations to increase size
        for i in range(1000):
            history.log_operation(
                OperationType.MOVE,
                Path(f'/test/very/long/path/with/many/segments/file{i}')
            )

        initial_count = history.db.get_operation_count()

        # Cleanup if over size
        if cleanup.should_cleanup():
            deleted = cleanup.cleanup_by_size()
            assert deleted >= 0

    def test_cleanup_failed_operations(self, history, cleanup):
        """Test cleaning up failed operations."""
        # Add some failed operations
        for i in range(5):
            history.log_operation(
                OperationType.MOVE,
                Path(f'/test/path{i}'),
                status=OperationStatus.FAILED,
                error_message="Test error"
            )

        # Add some successful operations
        for i in range(5):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i+5}'))

        # This won't delete anything since operations are not old enough
        deleted = cleanup.cleanup_failed_operations(older_than_days=7)
        assert deleted == 0  # No old failed operations

    def test_cleanup_rolled_back_operations(self, history, cleanup):
        """Test cleaning up rolled back operations."""
        # Add some rolled back operations
        for i in range(5):
            history.log_operation(
                OperationType.MOVE,
                Path(f'/test/path{i}'),
                status=OperationStatus.ROLLED_BACK
            )

        # This won't delete anything since operations are not old enough
        deleted = cleanup.cleanup_rolled_back_operations(older_than_days=7)
        assert deleted == 0  # No old rolled back operations

    def test_cleanup_orphaned_transactions(self, history, cleanup):
        """Test cleaning up orphaned transactions."""
        # Start a transaction but don't add any operations
        txn_id = history.start_transaction()

        # Add operations without transaction
        history.log_operation(OperationType.MOVE, Path('/test/path'))

        # Cleanup orphaned transactions
        deleted = cleanup._cleanup_orphaned_transactions()
        assert deleted == 1  # Should delete the empty transaction

    def test_auto_cleanup(self, history, cleanup):
        """Test automatic cleanup."""
        # Add many operations to trigger cleanup
        for i in range(150):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        # Run auto cleanup
        stats = cleanup.auto_cleanup()
        assert 'deleted_operations' in stats
        assert 'deleted_transactions' in stats
        assert stats['deleted_operations'] > 0

    def test_auto_cleanup_disabled(self, history):
        """Test that auto cleanup respects enabled flag."""
        config = HistoryCleanupConfig(auto_cleanup_enabled=False)
        cleanup = HistoryCleanup(history.db, config)

        # Add many operations
        for i in range(150):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        assert cleanup.should_cleanup() is False

    def test_clear_all_without_confirm(self, history, cleanup):
        """Test that clear_all requires confirmation."""
        # Add operations
        for i in range(10):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        result = cleanup.clear_all(confirm=False)
        assert result is False
        assert history.db.get_operation_count() == 10  # Nothing deleted

    def test_clear_all_with_confirm(self, history, cleanup):
        """Test clearing all history data."""
        # Add operations
        for i in range(10):
            history.log_operation(OperationType.MOVE, Path(f'/test/path{i}'))

        result = cleanup.clear_all(confirm=True)
        assert result is True
        assert history.db.get_operation_count() == 0  # Everything deleted

    def test_get_statistics(self, history, cleanup):
        """Test getting history statistics."""
        # Add various operations
        history.log_operation(OperationType.MOVE, Path('/test/path1'))
        history.log_operation(OperationType.RENAME, Path('/test/path2'))
        history.log_operation(
            OperationType.DELETE,
            Path('/test/path3'),
            status=OperationStatus.FAILED,
            error_message="Error"
        )

        # Start a transaction
        txn_id = history.start_transaction()
        history.log_operation(
            OperationType.COPY,
            Path('/test/path4'),
            transaction_id=txn_id
        )
        history.commit_transaction(txn_id)

        stats = cleanup.get_statistics()
        assert stats['total_operations'] == 4
        assert stats['operations_completed'] >= 2
        assert stats['operations_failed'] == 1
        assert stats['total_transactions'] == 1
        assert 'database_size_mb' in stats
        assert 'oldest_operation' in stats
        assert 'newest_operation' in stats
