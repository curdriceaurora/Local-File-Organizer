"""
History viewer for displaying operation history.

This module provides CLI-friendly formatting and filtering
for viewing operation history.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from ..history.tracker import OperationHistory
from ..history.models import Operation, OperationType, OperationStatus, Transaction

logger = logging.getLogger(__name__)


class HistoryViewer:
    """
    CLI viewer for operation history.

    This class provides methods to display operation history with
    various filters and formatting options.
    """

    def __init__(self, history: Optional[OperationHistory] = None):
        """
        Initialize history viewer.

        Args:
            history: Operation history tracker
        """
        self.history = history or OperationHistory()

    def show_recent_operations(self, limit: int = 10) -> None:
        """
        Display recent operations.

        Args:
            limit: Maximum number of operations to show
        """
        operations = self.history.get_recent_operations(limit=limit)

        if not operations:
            print("No operations found.")
            return

        print(f"\n{len(operations)} most recent operations:\n")
        self._print_operations_table(operations)

    def show_transaction_details(self, transaction_id: str) -> None:
        """
        Display details of a specific transaction.

        Args:
            transaction_id: Transaction ID
        """
        transaction = self.history.get_transaction(transaction_id)

        if not transaction:
            print(f"Transaction {transaction_id} not found.")
            return

        print(f"\nTransaction: {transaction_id}")
        print(f"Status: {transaction.status.value}")
        print(f"Started: {self._format_datetime(transaction.started_at)}")
        if transaction.completed_at:
            print(f"Completed: {self._format_datetime(transaction.completed_at)}")
        print(f"Operations: {transaction.operation_count}")

        if transaction.metadata:
            print(f"\nMetadata:")
            for key, value in transaction.metadata.items():
                print(f"  {key}: {value}")

        # Show operations in this transaction
        operations = self.history.get_operations(transaction_id=transaction_id)
        if operations:
            print(f"\nOperations in this transaction:\n")
            self._print_operations_table(operations)

    def show_operation_details(self, operation_id: int) -> None:
        """
        Display details of a specific operation.

        Args:
            operation_id: Operation ID
        """
        operations = self.history.get_operations(limit=1000)
        operation = next((op for op in operations if op.id == operation_id), None)

        if not operation:
            print(f"Operation {operation_id} not found.")
            return

        print(f"\nOperation {operation.id}:")
        print(f"Type: {operation.operation_type.value}")
        print(f"Status: {operation.status.value}")
        print(f"Timestamp: {self._format_datetime(operation.timestamp)}")
        print(f"Source: {operation.source_path}")
        if operation.destination_path:
            print(f"Destination: {operation.destination_path}")
        if operation.file_hash:
            print(f"File Hash: {operation.file_hash[:16]}...")
        if operation.transaction_id:
            print(f"Transaction: {operation.transaction_id}")
        if operation.error_message:
            print(f"Error: {operation.error_message}")

        if operation.metadata:
            print(f"\nMetadata:")
            for key, value in operation.metadata.items():
                if key != 'metadata':  # Skip nested metadata field
                    print(f"  {key}: {value}")

    def filter_operations(
        self,
        operation_type: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100
    ) -> List[Operation]:
        """
        Filter operations with various criteria.

        Args:
            operation_type: Filter by operation type (move, rename, delete, copy, create)
            status: Filter by status (completed, rolled_back, failed)
            since: Filter by start date (ISO format or human-readable)
            until: Filter by end date (ISO format or human-readable)
            limit: Maximum number of results

        Returns:
            List of filtered operations
        """
        # Parse operation type
        op_type = None
        if operation_type:
            try:
                op_type = OperationType(operation_type.lower())
            except ValueError:
                print(f"Invalid operation type: {operation_type}")
                return []

        # Parse status
        op_status = None
        if status:
            try:
                op_status = OperationStatus(status.lower())
            except ValueError:
                print(f"Invalid status: {status}")
                return []

        # Parse dates
        start_date = self._parse_date(since) if since else None
        end_date = self._parse_date(until) if until else None

        # Query operations
        operations = self.history.get_operations(
            operation_type=op_type,
            status=op_status,
            start_date=start_date,
            end_date=end_date,
            limit=limit
        )

        return operations

    def search_by_path(self, path: str) -> List[Operation]:
        """
        Search for operations affecting a specific path.

        Args:
            path: Path to search for (can be partial)

        Returns:
            List of operations affecting this path
        """
        # Get all operations (with reasonable limit)
        operations = self.history.get_operations(limit=10000)

        # Filter by path
        matching_ops = []
        for op in operations:
            source_match = path in str(op.source_path)
            dest_match = op.destination_path and path in str(op.destination_path)
            if source_match or dest_match:
                matching_ops.append(op)

        return matching_ops

    def display_filtered_operations(
        self,
        operation_type: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100
    ) -> None:
        """
        Display filtered operations.

        Args:
            operation_type: Filter by operation type
            status: Filter by status
            since: Filter by start date
            until: Filter by end date
            search: Search by path
            limit: Maximum number of results
        """
        # Apply path search if specified
        if search:
            operations = self.search_by_path(search)
            if not operations:
                print(f"No operations found affecting path: {search}")
                return
            print(f"\n{len(operations)} operations found affecting path '{search}':\n")
        else:
            operations = self.filter_operations(
                operation_type=operation_type,
                status=status,
                since=since,
                until=until,
                limit=limit
            )
            if not operations:
                print("No operations found matching the filters.")
                return
            print(f"\n{len(operations)} operations found:\n")

        self._print_operations_table(operations)

    def _print_operations_table(self, operations: List[Operation]) -> None:
        """
        Print operations in a formatted table.

        Args:
            operations: List of operations to display
        """
        # Calculate column widths
        id_width = max(len(str(op.id)) for op in operations) if operations else 3
        id_width = max(id_width, 3)

        # Print header
        print(f"{'ID':<{id_width}} | {'Type':<8} | {'Status':<12} | {'Time':<19} | {'Path'}")
        print(f"{'-' * id_width}-+-{'-' * 8}-+-{'-' * 12}-+-{'-' * 19}-+-{'-' * 40}")

        # Print operations
        for op in operations:
            op_id = str(op.id) if op.id else "?"
            op_type = op.operation_type.value[:8]
            status = self._format_status(op.status)
            timestamp = self._format_datetime_short(op.timestamp)
            path = self._format_path(op)

            print(f"{op_id:<{id_width}} | {op_type:<8} | {status:<12} | {timestamp:<19} | {path}")

    def _format_status(self, status: OperationStatus) -> str:
        """Format status with color indicators."""
        status_str = status.value
        if status == OperationStatus.COMPLETED:
            return f"✓ {status_str}"
        elif status == OperationStatus.ROLLED_BACK:
            return f"↶ {status_str}"
        elif status == OperationStatus.FAILED:
            return f"✗ {status_str}"
        else:
            return status_str

    def _format_path(self, operation: Operation) -> str:
        """Format path for display."""
        if operation.destination_path:
            return f"{operation.source_path.name} → {operation.destination_path.name}"
        else:
            return str(operation.source_path.name)

    def _format_datetime(self, dt: datetime) -> str:
        """Format datetime for display."""
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _format_datetime_short(self, dt: datetime) -> str:
        """Format datetime in short format."""
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """
        Parse date string to datetime.

        Args:
            date_str: Date string (ISO format or common formats)

        Returns:
            Datetime object or None if parsing fails
        """
        # Try ISO format
        try:
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except ValueError:
            pass

        # Try common formats
        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        print(f"Warning: Could not parse date: {date_str}")
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get statistics about operation history.

        Returns:
            Dictionary with statistics
        """
        all_ops = self.history.get_operations(limit=100000)

        stats = {
            'total_operations': len(all_ops),
            'by_type': {},
            'by_status': {},
            'latest_operation': None,
            'oldest_operation': None
        }

        # Count by type
        for op_type in OperationType:
            count = sum(1 for op in all_ops if op.operation_type == op_type)
            stats['by_type'][op_type.value] = count

        # Count by status
        for status in OperationStatus:
            count = sum(1 for op in all_ops if op.status == status)
            stats['by_status'][status.value] = count

        # Get latest and oldest
        if all_ops:
            stats['latest_operation'] = all_ops[0]  # Already sorted DESC
            stats['oldest_operation'] = all_ops[-1]

        return stats

    def show_statistics(self) -> None:
        """Display operation history statistics."""
        stats = self.get_statistics()

        print("\nOperation History Statistics:")
        print(f"Total operations: {stats['total_operations']}")

        print("\nBy type:")
        for op_type, count in stats['by_type'].items():
            print(f"  {op_type}: {count}")

        print("\nBy status:")
        for status, count in stats['by_status'].items():
            print(f"  {status}: {count}")

        if stats['latest_operation']:
            print(f"\nLatest operation: {stats['latest_operation'].id} "
                  f"({self._format_datetime(stats['latest_operation'].timestamp)})")

        if stats['oldest_operation']:
            print(f"Oldest operation: {stats['oldest_operation'].id} "
                  f"({self._format_datetime(stats['oldest_operation'].timestamp)})")

    def close(self) -> None:
        """Close resources."""
        self.history.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
