"""
History cleanup and maintenance utilities.

This module provides functionality for managing operation history size,
including automatic cleanup, manual purging, and database maintenance.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from pathlib import Path

from .database import DatabaseManager
from .models import OperationStatus, TransactionStatus

logger = logging.getLogger(__name__)


class HistoryCleanupConfig:
    """
    Configuration for history cleanup policies.

    Attributes:
        max_operations: Maximum number of operations to keep (default: 10,000)
        max_age_days: Maximum age of operations in days (default: 90)
        max_size_mb: Maximum database size in MB (default: 100)
        auto_cleanup_enabled: Whether to run cleanup automatically (default: True)
        cleanup_batch_size: Number of operations to delete per batch (default: 1000)
    """

    def __init__(
        self,
        max_operations: int = 10000,
        max_age_days: int = 90,
        max_size_mb: int = 100,
        auto_cleanup_enabled: bool = True,
        cleanup_batch_size: int = 1000
    ):
        self.max_operations = max_operations
        self.max_age_days = max_age_days
        self.max_size_mb = max_size_mb
        self.auto_cleanup_enabled = auto_cleanup_enabled
        self.cleanup_batch_size = cleanup_batch_size


class HistoryCleanup:
    """
    Manages cleanup and maintenance of operation history.

    This class provides methods to automatically clean up old operations,
    manage database size, and perform maintenance tasks.
    """

    def __init__(self, db: DatabaseManager, config: Optional[HistoryCleanupConfig] = None):
        """
        Initialize history cleanup manager.

        Args:
            db: Database manager instance
            config: Cleanup configuration. Uses defaults if not provided.
        """
        self.db = db
        self.config = config or HistoryCleanupConfig()
        logger.info("History cleanup manager initialized")

    def should_cleanup(self) -> bool:
        """
        Check if cleanup should be performed based on current state.

        Returns:
            True if cleanup is needed, False otherwise
        """
        if not self.config.auto_cleanup_enabled:
            return False

        # Check operation count
        operation_count = self.db.get_operation_count()
        if operation_count >= self.config.max_operations:
            logger.info(f"Cleanup needed: {operation_count} operations exceeds limit of {self.config.max_operations}")
            return True

        # Check database size
        db_size_mb = self.db.get_database_size() / (1024 * 1024)
        if db_size_mb >= self.config.max_size_mb:
            logger.info(f"Cleanup needed: {db_size_mb:.2f}MB exceeds limit of {self.config.max_size_mb}MB")
            return True

        return False

    def cleanup_old_operations(self, max_age_days: Optional[int] = None) -> int:
        """
        Delete operations older than the specified age.

        Args:
            max_age_days: Maximum age in days. Uses config default if not specified.

        Returns:
            Number of operations deleted
        """
        if max_age_days is None:
            max_age_days = self.config.max_age_days

        cutoff_date = datetime.utcnow() - timedelta(days=max_age_days)
        cutoff_str = cutoff_date.isoformat() + 'Z'

        logger.info(f"Cleaning up operations older than {max_age_days} days (before {cutoff_str})")

        # Delete old operations
        query = "DELETE FROM operations WHERE timestamp < ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(query, (cutoff_str,))
            deleted_count = cursor.rowcount

        # Clean up orphaned transactions
        self._cleanup_orphaned_transactions()

        logger.info(f"Deleted {deleted_count} old operations")
        return deleted_count

    def cleanup_by_count(self, max_operations: Optional[int] = None) -> int:
        """
        Keep only the most recent N operations, delete older ones.

        Args:
            max_operations: Maximum number of operations to keep. Uses config default if not specified.

        Returns:
            Number of operations deleted
        """
        if max_operations is None:
            max_operations = self.config.max_operations

        current_count = self.db.get_operation_count()
        if current_count <= max_operations:
            logger.info(f"No cleanup needed: {current_count} operations within limit of {max_operations}")
            return 0

        operations_to_delete = current_count - max_operations
        logger.info(f"Cleaning up {operations_to_delete} operations to maintain limit of {max_operations}")

        # Get the timestamp of the Nth most recent operation
        query = """
        SELECT timestamp FROM operations
        ORDER BY timestamp DESC
        LIMIT 1 OFFSET ?
        """
        result = self.db.fetch_one(query, (max_operations,))

        if result is None:
            logger.warning("Could not determine cutoff timestamp")
            return 0

        cutoff_timestamp = result['timestamp']

        # Delete operations older than the cutoff
        delete_query = "DELETE FROM operations WHERE timestamp < ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(delete_query, (cutoff_timestamp,))
            deleted_count = cursor.rowcount

        # Clean up orphaned transactions
        self._cleanup_orphaned_transactions()

        logger.info(f"Deleted {deleted_count} operations")
        return deleted_count

    def cleanup_by_size(self, max_size_mb: Optional[int] = None) -> int:
        """
        Delete old operations until database is under size limit.

        Args:
            max_size_mb: Maximum database size in MB. Uses config default if not specified.

        Returns:
            Number of operations deleted
        """
        if max_size_mb is None:
            max_size_mb = self.config.max_size_mb

        current_size_mb = self.db.get_database_size() / (1024 * 1024)

        if current_size_mb <= max_size_mb:
            logger.info(f"No cleanup needed: {current_size_mb:.2f}MB within limit of {max_size_mb}MB")
            return 0

        logger.info(f"Database size {current_size_mb:.2f}MB exceeds limit of {max_size_mb}MB, cleaning up...")

        total_deleted = 0
        batch_size = self.config.cleanup_batch_size

        # Delete operations in batches until size is acceptable
        while current_size_mb > max_size_mb:
            # Get oldest operations
            query = """
            SELECT id FROM operations
            ORDER BY timestamp ASC
            LIMIT ?
            """
            rows = self.db.fetch_all(query, (batch_size,))

            if not rows:
                break

            # Delete the batch
            ids = [row['id'] for row in rows]
            placeholders = ','.join('?' * len(ids))
            delete_query = f"DELETE FROM operations WHERE id IN ({placeholders})"

            with self.db.transaction() as conn:
                cursor = conn.execute(delete_query, ids)
                deleted = cursor.rowcount
                total_deleted += deleted

            # Vacuum to reclaim space
            self.db.vacuum()

            # Check new size
            current_size_mb = self.db.get_database_size() / (1024 * 1024)
            logger.info(f"Deleted {deleted} operations, current size: {current_size_mb:.2f}MB")

        # Clean up orphaned transactions
        self._cleanup_orphaned_transactions()

        logger.info(f"Cleanup complete: deleted {total_deleted} operations, final size: {current_size_mb:.2f}MB")
        return total_deleted

    def cleanup_failed_operations(self, older_than_days: int = 7) -> int:
        """
        Delete failed operations older than specified days.

        Args:
            older_than_days: Only delete failed operations older than this many days

        Returns:
            Number of operations deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        cutoff_str = cutoff_date.isoformat() + 'Z'

        logger.info(f"Cleaning up failed operations older than {older_than_days} days")

        query = "DELETE FROM operations WHERE status = ? AND timestamp < ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(query, (OperationStatus.FAILED.value, cutoff_str))
            deleted_count = cursor.rowcount

        logger.info(f"Deleted {deleted_count} failed operations")
        return deleted_count

    def cleanup_rolled_back_operations(self, older_than_days: int = 7) -> int:
        """
        Delete rolled back operations older than specified days.

        Args:
            older_than_days: Only delete rolled back operations older than this many days

        Returns:
            Number of operations deleted
        """
        cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
        cutoff_str = cutoff_date.isoformat() + 'Z'

        logger.info(f"Cleaning up rolled back operations older than {older_than_days} days")

        query = "DELETE FROM operations WHERE status = ? AND timestamp < ?"
        with self.db.transaction() as conn:
            cursor = conn.execute(query, (OperationStatus.ROLLED_BACK.value, cutoff_str))
            deleted_count = cursor.rowcount

        logger.info(f"Deleted {deleted_count} rolled back operations")
        return deleted_count

    def _cleanup_orphaned_transactions(self) -> int:
        """
        Delete transactions that have no associated operations.

        Returns:
            Number of transactions deleted
        """
        query = """
        DELETE FROM transactions
        WHERE transaction_id NOT IN (
            SELECT DISTINCT transaction_id FROM operations WHERE transaction_id IS NOT NULL
        )
        """
        with self.db.transaction() as conn:
            cursor = conn.execute(query)
            deleted_count = cursor.rowcount

        if deleted_count > 0:
            logger.info(f"Deleted {deleted_count} orphaned transactions")

        return deleted_count

    def auto_cleanup(self) -> Dict[str, int]:
        """
        Perform automatic cleanup based on configuration.

        This method checks if cleanup is needed and performs the necessary
        cleanup operations to maintain configured limits.

        Returns:
            Dictionary with cleanup statistics
        """
        if not self.should_cleanup():
            logger.debug("Auto cleanup not needed")
            return {'deleted_operations': 0, 'deleted_transactions': 0}

        logger.info("Starting auto cleanup...")

        stats = {
            'deleted_operations': 0,
            'deleted_transactions': 0
        }

        # Clean by age
        deleted = self.cleanup_old_operations()
        stats['deleted_operations'] += deleted

        # Clean by count if still over limit
        if self.db.get_operation_count() > self.config.max_operations:
            deleted = self.cleanup_by_count()
            stats['deleted_operations'] += deleted

        # Clean by size if still over limit
        db_size_mb = self.db.get_database_size() / (1024 * 1024)
        if db_size_mb > self.config.max_size_mb:
            deleted = self.cleanup_by_size()
            stats['deleted_operations'] += deleted

        # Clean orphaned transactions
        deleted = self._cleanup_orphaned_transactions()
        stats['deleted_transactions'] = deleted

        # Vacuum to reclaim space
        self.db.vacuum()

        logger.info(f"Auto cleanup complete: {stats}")
        return stats

    def clear_all(self, confirm: bool = False) -> bool:
        """
        Delete all operations and transactions from the database.

        Args:
            confirm: Must be True to actually delete data

        Returns:
            True if data was deleted, False otherwise
        """
        if not confirm:
            logger.warning("clear_all() called without confirm=True, aborting")
            return False

        logger.warning("Clearing all history data...")

        with self.db.transaction() as conn:
            conn.execute("DELETE FROM operations")
            conn.execute("DELETE FROM transactions")

        # Vacuum to reclaim space
        self.db.vacuum()

        logger.info("All history data cleared")
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about the current history database.

        Returns:
            Dictionary with various statistics
        """
        stats = {}

        # Operation counts
        stats['total_operations'] = self.db.get_operation_count()
        stats['database_size_mb'] = self.db.get_database_size() / (1024 * 1024)

        # Count by status
        for status in [OperationStatus.COMPLETED, OperationStatus.FAILED, OperationStatus.ROLLED_BACK]:
            query = "SELECT COUNT(*) as count FROM operations WHERE status = ?"
            result = self.db.fetch_one(query, (status.value,))
            stats[f'operations_{status.value}'] = result['count'] if result else 0

        # Transaction counts
        query = "SELECT COUNT(*) as count FROM transactions"
        result = self.db.fetch_one(query)
        stats['total_transactions'] = result['count'] if result else 0

        # Count by transaction status
        for status in [TransactionStatus.COMPLETED, TransactionStatus.FAILED]:
            query = "SELECT COUNT(*) as count FROM transactions WHERE status = ?"
            result = self.db.fetch_one(query, (status.value,))
            stats[f'transactions_{status.value}'] = result['count'] if result else 0

        # Oldest and newest operations
        query = "SELECT MIN(timestamp) as oldest, MAX(timestamp) as newest FROM operations"
        result = self.db.fetch_one(query)
        if result:
            stats['oldest_operation'] = result['oldest']
            stats['newest_operation'] = result['newest']

        return stats
