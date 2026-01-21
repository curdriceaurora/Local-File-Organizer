"""
Export utilities for operation history.

This module provides functionality to export operation history
to various formats (JSON, CSV).
"""

import json
import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .database import DatabaseManager
from .models import Operation, Transaction, OperationType, OperationStatus, TransactionStatus

logger = logging.getLogger(__name__)


class HistoryExporter:
    """
    Exports operation history to various formats.

    This class provides methods to export operations and transactions
    to JSON and CSV formats.
    """

    def __init__(self, db: DatabaseManager):
        """
        Initialize history exporter.

        Args:
            db: Database manager instance
        """
        self.db = db
        logger.info("History exporter initialized")

    def export_to_json(
        self,
        output_path: Path,
        operation_type: Optional[OperationType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        include_transactions: bool = True
    ) -> Dict[str, int]:
        """
        Export operations to JSON file.

        Args:
            output_path: Path to output JSON file
            operation_type: Filter by operation type (optional)
            start_date: Filter by start date (optional)
            end_date: Filter by end date (optional)
            include_transactions: Whether to include transaction details

        Returns:
            Dictionary with export statistics
        """
        logger.info(f"Exporting operations to JSON: {output_path}")

        # Build query
        query = "SELECT * FROM operations WHERE 1=1"
        params = []

        if operation_type:
            query += " AND operation_type = ?"
            params.append(operation_type.value if isinstance(operation_type, OperationType) else operation_type)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat() + 'Z')

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat() + 'Z')

        query += " ORDER BY timestamp DESC"

        # Fetch operations
        rows = self.db.fetch_all(query, tuple(params) if params else None)
        operations = [Operation.from_row(row).to_dict() for row in rows]

        # Build export data
        export_data = {
            'export_date': datetime.utcnow().isoformat() + 'Z',
            'operation_count': len(operations),
            'operations': operations
        }

        # Include transactions if requested
        if include_transactions:
            # Get unique transaction IDs
            transaction_ids = set(op.get('transaction_id') for op in operations if op.get('transaction_id'))

            if transaction_ids:
                placeholders = ','.join('?' * len(transaction_ids))
                txn_query = f"SELECT * FROM transactions WHERE transaction_id IN ({placeholders})"
                txn_rows = self.db.fetch_all(txn_query, tuple(transaction_ids))
                transactions = [Transaction.from_row(row).to_dict() for row in txn_rows]
                export_data['transactions'] = transactions
                export_data['transaction_count'] = len(transactions)

        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(export_data, f, indent=2)

        logger.info(f"Exported {len(operations)} operations to {output_path}")
        return {
            'operations_exported': len(operations),
            'transactions_exported': len(export_data.get('transactions', []))
        }

    def export_to_csv(
        self,
        output_path: Path,
        operation_type: Optional[OperationType] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """
        Export operations to CSV file.

        Args:
            output_path: Path to output CSV file
            operation_type: Filter by operation type (optional)
            start_date: Filter by start date (optional)
            end_date: Filter by end date (optional)

        Returns:
            Number of operations exported
        """
        logger.info(f"Exporting operations to CSV: {output_path}")

        # Build query
        query = "SELECT * FROM operations WHERE 1=1"
        params = []

        if operation_type:
            query += " AND operation_type = ?"
            params.append(operation_type.value if isinstance(operation_type, OperationType) else operation_type)

        if start_date:
            query += " AND timestamp >= ?"
            params.append(start_date.isoformat() + 'Z')

        if end_date:
            query += " AND timestamp <= ?"
            params.append(end_date.isoformat() + 'Z')

        query += " ORDER BY timestamp DESC"

        # Fetch operations
        rows = self.db.fetch_all(query, tuple(params) if params else None)

        if not rows:
            logger.warning("No operations to export")
            return 0

        # Define CSV columns
        columns = [
            'id', 'operation_type', 'timestamp', 'source_path', 'destination_path',
            'file_hash', 'transaction_id', 'status', 'error_message', 'created_at',
            'file_size', 'file_type', 'is_file', 'is_dir'
        ]

        # Write to CSV
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()

            for row in rows:
                operation = Operation.from_row(row)
                csv_row = {
                    'id': operation.id,
                    'operation_type': operation.operation_type.value if isinstance(operation.operation_type, OperationType) else operation.operation_type,
                    'timestamp': operation.timestamp.isoformat() if isinstance(operation.timestamp, datetime) else operation.timestamp,
                    'source_path': str(operation.source_path),
                    'destination_path': str(operation.destination_path) if operation.destination_path else '',
                    'file_hash': operation.file_hash or '',
                    'transaction_id': operation.transaction_id or '',
                    'status': operation.status.value if isinstance(operation.status, OperationStatus) else operation.status,
                    'error_message': operation.error_message or '',
                    'created_at': operation.created_at.isoformat() if operation.created_at and isinstance(operation.created_at, datetime) else operation.created_at or '',
                    'file_size': operation.metadata.get('size', ''),
                    'file_type': 'file' if operation.metadata.get('is_file') else 'dir' if operation.metadata.get('is_dir') else '',
                    'is_file': operation.metadata.get('is_file', ''),
                    'is_dir': operation.metadata.get('is_dir', '')
                }
                writer.writerow(csv_row)

        logger.info(f"Exported {len(rows)} operations to {output_path}")
        return len(rows)

    def export_transactions_to_csv(self, output_path: Path) -> int:
        """
        Export transactions to CSV file.

        Args:
            output_path: Path to output CSV file

        Returns:
            Number of transactions exported
        """
        logger.info(f"Exporting transactions to CSV: {output_path}")

        # Fetch all transactions
        query = "SELECT * FROM transactions ORDER BY started_at DESC"
        rows = self.db.fetch_all(query)

        if not rows:
            logger.warning("No transactions to export")
            return 0

        # Define CSV columns
        columns = [
            'transaction_id', 'started_at', 'completed_at',
            'operation_count', 'status'
        ]

        # Write to CSV
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()

            for row in rows:
                transaction = Transaction.from_row(row)
                csv_row = {
                    'transaction_id': transaction.transaction_id,
                    'started_at': transaction.started_at.isoformat() if isinstance(transaction.started_at, datetime) else transaction.started_at,
                    'completed_at': transaction.completed_at.isoformat() if transaction.completed_at and isinstance(transaction.completed_at, datetime) else transaction.completed_at or '',
                    'operation_count': transaction.operation_count,
                    'status': transaction.status.value if isinstance(transaction.status, TransactionStatus) else transaction.status
                }
                writer.writerow(csv_row)

        logger.info(f"Exported {len(rows)} transactions to {output_path}")
        return len(rows)

    def export_statistics(self, output_path: Path) -> bool:
        """
        Export database statistics to JSON file.

        Args:
            output_path: Path to output JSON file

        Returns:
            True if successful
        """
        logger.info(f"Exporting statistics to JSON: {output_path}")

        stats = {}

        # Overall counts
        stats['total_operations'] = self.db.get_operation_count()
        stats['database_size_mb'] = self.db.get_database_size() / (1024 * 1024)

        # Count by operation type
        for op_type in OperationType:
            query = "SELECT COUNT(*) as count FROM operations WHERE operation_type = ?"
            result = self.db.fetch_one(query, (op_type.value,))
            stats[f'operations_{op_type.value}'] = result['count'] if result else 0

        # Count by status
        for status in OperationStatus:
            query = "SELECT COUNT(*) as count FROM operations WHERE status = ?"
            result = self.db.fetch_one(query, (status.value,))
            stats[f'operations_{status.value}'] = result['count'] if result else 0

        # Transaction counts
        query = "SELECT COUNT(*) as count FROM transactions"
        result = self.db.fetch_one(query)
        stats['total_transactions'] = result['count'] if result else 0

        # Date range
        query = "SELECT MIN(timestamp) as oldest, MAX(timestamp) as newest FROM operations"
        result = self.db.fetch_one(query)
        if result:
            stats['oldest_operation'] = result['oldest']
            stats['newest_operation'] = result['newest']

        # Export date
        stats['export_date'] = datetime.utcnow().isoformat() + 'Z'

        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(stats, f, indent=2)

        logger.info(f"Exported statistics to {output_path}")
        return True
