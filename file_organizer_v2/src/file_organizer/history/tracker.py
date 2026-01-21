"""
Operation tracker for logging file operations.

This module provides the main interface for tracking file operations
and managing operation history.
"""

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List
import json

from .database import DatabaseManager
from .models import Operation, OperationType, OperationStatus, Transaction, TransactionStatus

logger = logging.getLogger(__name__)


class OperationHistory:
    """
    Main interface for operation history tracking.

    This class provides methods to log file operations, manage transactions,
    and query operation history.
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize operation history tracker.

        Args:
            db_path: Path to SQLite database file.
                    Defaults to ~/.file_organizer/history.db
        """
        self.db = DatabaseManager(db_path)
        self.db.initialize()
        logger.info("Operation history tracker initialized")

    def log_operation(
        self,
        operation_type: OperationType,
        source_path: Path,
        destination_path: Optional[Path] = None,
        metadata: Optional[Dict[str, Any]] = None,
        transaction_id: Optional[str] = None,
        status: OperationStatus = OperationStatus.COMPLETED,
        error_message: Optional[str] = None
    ) -> int:
        """
        Log a file operation to the database.

        Args:
            operation_type: Type of operation (move, rename, delete, copy)
            source_path: Source file path
            destination_path: Destination file path (for move/rename/copy)
            metadata: Additional metadata about the operation
            transaction_id: ID of the transaction this operation belongs to
            status: Current status of the operation
            error_message: Error message if operation failed

        Returns:
            Operation ID
        """
        timestamp = datetime.utcnow()

        # Calculate file hash if source file exists
        file_hash = None
        if source_path.exists() and source_path.is_file():
            try:
                file_hash = self._calculate_file_hash(source_path)
            except Exception as e:
                logger.warning(f"Failed to calculate file hash for {source_path}: {e}")

        # Collect metadata
        if metadata is None:
            metadata = {}

        # Add file metadata if source exists
        if source_path.exists():
            try:
                stat = source_path.stat()
                metadata.update({
                    'size': stat.st_size,
                    'mode': stat.st_mode,
                    'mtime': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    'is_file': source_path.is_file(),
                    'is_dir': source_path.is_dir()
                })
            except Exception as e:
                logger.warning(f"Failed to collect metadata for {source_path}: {e}")

        # Convert metadata to JSON
        metadata_json = json.dumps(metadata)

        # Insert operation into database
        query = """
        INSERT INTO operations (
            operation_type, timestamp, source_path, destination_path,
            file_hash, metadata, transaction_id, status, error_message
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            operation_type.value if isinstance(operation_type, OperationType) else operation_type,
            timestamp.isoformat() + 'Z',
            str(source_path),
            str(destination_path) if destination_path else None,
            file_hash,
            metadata_json,
            transaction_id,
            status.value if isinstance(status, OperationStatus) else status,
            error_message
        )

        with self.db.transaction() as conn:
            cursor = conn.execute(query, params)
            operation_id = cursor.lastrowid

            # Update transaction operation count if in a transaction
            if transaction_id:
                conn.execute(
                    "UPDATE transactions SET operation_count = operation_count + 1 WHERE transaction_id = ?",
                    (transaction_id,)
                )

        logger.debug(f"Logged operation {operation_id}: {operation_type.value} {source_path}")
        return operation_id

    def start_transaction(self, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Start a new transaction for batch operations.

        Args:
            metadata: Additional metadata about the transaction

        Returns:
            Transaction ID
        """
        import uuid
        transaction_id = str(uuid.uuid4())
        started_at = datetime.utcnow()

        metadata_json = json.dumps(metadata or {})

        query = """
        INSERT INTO transactions (transaction_id, started_at, status, metadata)
        VALUES (?, ?, ?, ?)
        """

        params = (
            transaction_id,
            started_at.isoformat() + 'Z',
            TransactionStatus.IN_PROGRESS.value,
            metadata_json
        )

        self.db.execute_query(query, params)
        self.db.get_connection().commit()

        logger.info(f"Started transaction {transaction_id}")
        return transaction_id

    def commit_transaction(self, transaction_id: str) -> bool:
        """
        Commit a transaction, marking it as completed.

        Args:
            transaction_id: Transaction ID to commit

        Returns:
            True if successful, False otherwise
        """
        completed_at = datetime.utcnow()

        query = """
        UPDATE transactions
        SET status = ?, completed_at = ?
        WHERE transaction_id = ?
        """

        params = (
            TransactionStatus.COMPLETED.value,
            completed_at.isoformat() + 'Z',
            transaction_id
        )

        try:
            self.db.execute_query(query, params)
            self.db.get_connection().commit()
            logger.info(f"Committed transaction {transaction_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to commit transaction {transaction_id}: {e}")
            return False

    def rollback_transaction(self, transaction_id: str) -> bool:
        """
        Rollback a transaction, marking all its operations as rolled back.

        Args:
            transaction_id: Transaction ID to rollback

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.db.transaction() as conn:
                # Update transaction status
                conn.execute(
                    "UPDATE transactions SET status = ?, completed_at = ? WHERE transaction_id = ?",
                    (TransactionStatus.FAILED.value, datetime.utcnow().isoformat() + 'Z', transaction_id)
                )

                # Update all operations in this transaction
                conn.execute(
                    "UPDATE operations SET status = ? WHERE transaction_id = ?",
                    (OperationStatus.ROLLED_BACK.value, transaction_id)
                )

            logger.info(f"Rolled back transaction {transaction_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to rollback transaction {transaction_id}: {e}")
            return False

    def get_operations(
        self,
        operation_type: Optional[OperationType] = None,
        transaction_id: Optional[str] = None,
        status: Optional[OperationStatus] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None
    ) -> List[Operation]:
        """
        Query operations with optional filters.

        Args:
            operation_type: Filter by operation type
            transaction_id: Filter by transaction ID
            status: Filter by status
            start_date: Filter by start date (inclusive)
            end_date: Filter by end date (inclusive)
            limit: Maximum number of results

        Returns:
            List of operations matching the filters
        """
        query = "SELECT * FROM operations WHERE 1=1"
        params = []

        if operation_type:
            query += " AND operation_type = ?"
            params.append(operation_type.value if isinstance(operation_type, OperationType) else operation_type)

        if transaction_id:
            query += " AND transaction_id = ?"
            params.append(transaction_id)

        if status:
            query += " AND status = ?"
            params.append(status.value if isinstance(status, OperationStatus) else status)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat() + 'Z')

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat() + 'Z')

        query += " ORDER BY timestamp DESC"

        if limit:
            # Validate and use parameter placeholder for LIMIT
            limit_value = int(limit)
            if limit_value < 0:
                raise ValueError("limit must be non-negative")
            query += " LIMIT ?"
            params.append(limit_value)

        rows = self.db.fetch_all(query, tuple(params) if params else None)
        return [Operation.from_row(row) for row in rows]

    def get_transaction(self, transaction_id: str) -> Optional[Transaction]:
        """
        Get transaction by ID.

        Args:
            transaction_id: Transaction ID

        Returns:
            Transaction object or None if not found
        """
        query = "SELECT * FROM transactions WHERE transaction_id = ?"
        row = self.db.fetch_one(query, (transaction_id,))

        if row:
            return Transaction.from_row(row)
        return None

    def get_recent_operations(self, limit: int = 100) -> List[Operation]:
        """
        Get most recent operations.

        Args:
            limit: Maximum number of operations to return

        Returns:
            List of recent operations
        """
        return self.get_operations(limit=limit)

    def _calculate_file_hash(self, file_path: Path) -> str:
        """
        Calculate SHA256 hash of a file.

        Args:
            file_path: Path to file

        Returns:
            SHA256 hash as hex string
        """
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            # Read file in chunks to handle large files
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def close(self) -> None:
        """Close database connection."""
        self.db.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
