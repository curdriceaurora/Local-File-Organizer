"""Tests for history data models (Operation, Transaction, enums).

Covers construction, serialization (to_dict/from_dict), edge cases,
and round-trip fidelity for all model classes.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from file_organizer.history.models import (
    Operation,
    OperationStatus,
    OperationType,
    Transaction,
    TransactionStatus,
)

# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOperationType:
    """Tests for OperationType enum."""

    def test_all_values_present(self) -> None:
        assert set(OperationType) == {
            OperationType.MOVE,
            OperationType.RENAME,
            OperationType.DELETE,
            OperationType.COPY,
            OperationType.CREATE,
        }

    def test_string_values(self) -> None:
        assert OperationType.MOVE.value == "move"
        assert OperationType.RENAME.value == "rename"
        assert OperationType.DELETE.value == "delete"
        assert OperationType.COPY.value == "copy"
        assert OperationType.CREATE.value == "create"

    def test_construction_from_value(self) -> None:
        assert OperationType("move") is OperationType.MOVE
        assert OperationType("create") is OperationType.CREATE

    def test_is_str_subclass(self) -> None:
        # StrEnum members are instances of str and their value matches
        assert isinstance(OperationType.MOVE, str)
        assert OperationType.MOVE == "move"

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            OperationType("invalid")


@pytest.mark.unit
class TestOperationStatus:
    """Tests for OperationStatus enum."""

    def test_all_values_present(self) -> None:
        assert set(OperationStatus) == {
            OperationStatus.PENDING,
            OperationStatus.COMPLETED,
            OperationStatus.FAILED,
            OperationStatus.ROLLED_BACK,
        }

    def test_string_values(self) -> None:
        assert OperationStatus.PENDING.value == "pending"
        assert OperationStatus.COMPLETED.value == "completed"
        assert OperationStatus.FAILED.value == "failed"
        assert OperationStatus.ROLLED_BACK.value == "rolled_back"

    def test_construction_from_value(self) -> None:
        assert OperationStatus("pending") is OperationStatus.PENDING
        assert OperationStatus("rolled_back") is OperationStatus.ROLLED_BACK


@pytest.mark.unit
class TestTransactionStatus:
    """Tests for TransactionStatus enum."""

    def test_all_values_present(self) -> None:
        assert set(TransactionStatus) == {
            TransactionStatus.IN_PROGRESS,
            TransactionStatus.COMPLETED,
            TransactionStatus.FAILED,
            TransactionStatus.PARTIALLY_ROLLED_BACK,
        }

    def test_string_values(self) -> None:
        assert TransactionStatus.IN_PROGRESS.value == "in_progress"
        assert TransactionStatus.COMPLETED.value == "completed"
        assert TransactionStatus.FAILED.value == "failed"
        assert TransactionStatus.PARTIALLY_ROLLED_BACK.value == "partially_rolled_back"


# ---------------------------------------------------------------------------
# Operation Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOperation:
    """Tests for the Operation dataclass."""

    @pytest.fixture()
    def now(self) -> datetime:
        return datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)

    @pytest.fixture()
    def minimal_op(self, now: datetime) -> Operation:
        """Operation with only required fields."""
        return Operation(
            operation_type=OperationType.MOVE,
            timestamp=now,
            source_path=Path("/src/file.txt"),
        )

    @pytest.fixture()
    def full_op(self, now: datetime) -> Operation:
        """Operation with all fields populated."""
        return Operation(
            id=42,
            operation_type=OperationType.COPY,
            timestamp=now,
            source_path=Path("/src/file.txt"),
            destination_path=Path("/dst/file.txt"),
            file_hash="abc123",
            metadata={"size": 1024, "type": "text"},
            transaction_id="txn-001",
            status=OperationStatus.COMPLETED,
            error_message=None,
            created_at=now,
        )

    # -- Construction -------------------------------------------------------

    def test_minimal_construction(self, minimal_op: Operation) -> None:
        assert minimal_op.operation_type is OperationType.MOVE
        assert minimal_op.source_path == Path("/src/file.txt")
        assert minimal_op.id is None
        assert minimal_op.destination_path is None
        assert minimal_op.file_hash is None
        assert minimal_op.metadata == {}
        assert minimal_op.transaction_id is None
        assert minimal_op.status is OperationStatus.COMPLETED
        assert minimal_op.error_message is None
        assert minimal_op.created_at is None

    def test_full_construction(self, full_op: Operation, now: datetime) -> None:
        assert full_op.id == 42
        assert full_op.operation_type is OperationType.COPY
        assert full_op.timestamp == now
        assert full_op.destination_path == Path("/dst/file.txt")
        assert full_op.file_hash == "abc123"
        assert full_op.metadata == {"size": 1024, "type": "text"}
        assert full_op.transaction_id == "txn-001"
        assert full_op.status is OperationStatus.COMPLETED
        assert full_op.created_at == now

    def test_default_metadata_is_independent(self) -> None:
        """Each instance gets its own empty dict for metadata."""
        now = datetime.now(tz=UTC)
        op1 = Operation(
            operation_type=OperationType.MOVE,
            timestamp=now,
            source_path=Path("/a"),
        )
        op2 = Operation(
            operation_type=OperationType.MOVE,
            timestamp=now,
            source_path=Path("/b"),
        )
        op1.metadata["key"] = "val"
        assert "key" not in op2.metadata

    # -- to_dict ------------------------------------------------------------

    def test_to_dict_minimal(self, minimal_op: Operation, now: datetime) -> None:
        d = minimal_op.to_dict()
        assert d["id"] is None
        assert d["operation_type"] == "move"
        assert d["timestamp"] == now.isoformat()
        assert d["source_path"] == "/src/file.txt"
        assert d["destination_path"] is None
        assert d["file_hash"] is None
        assert d["metadata"] == {}
        assert d["transaction_id"] is None
        assert d["status"] == "completed"
        assert d["error_message"] is None
        assert d["created_at"] is None

    def test_to_dict_full(self, full_op: Operation, now: datetime) -> None:
        d = full_op.to_dict()
        assert d["id"] == 42
        assert d["operation_type"] == "copy"
        assert d["timestamp"] == now.isoformat()
        assert d["source_path"] == "/src/file.txt"
        assert d["destination_path"] == "/dst/file.txt"
        assert d["file_hash"] == "abc123"
        assert d["metadata"] == {"size": 1024, "type": "text"}
        assert d["transaction_id"] == "txn-001"
        assert d["status"] == "completed"
        assert d["created_at"] == now.isoformat()

    def test_to_dict_with_failed_status(self, now: datetime) -> None:
        op = Operation(
            operation_type=OperationType.DELETE,
            timestamp=now,
            source_path=Path("/tmp/gone.txt"),
            status=OperationStatus.FAILED,
            error_message="Permission denied",
        )
        d = op.to_dict()
        assert d["status"] == "failed"
        assert d["error_message"] == "Permission denied"

    def test_to_dict_handles_pre_serialized_strings(self, now: datetime) -> None:
        """When operation_type/status are already plain strings (e.g. from DB)."""
        op = Operation(
            operation_type=OperationType.MOVE,
            timestamp=now,
            source_path=Path("/a"),
        )
        # Force plain-string values to exercise the isinstance branches
        op.operation_type = "move"  # type: ignore[assignment]
        op.status = "completed"  # type: ignore[assignment]
        op.timestamp = now.isoformat()  # type: ignore[assignment]
        op.created_at = "2026-01-01T00:00:00"  # type: ignore[assignment]
        d = op.to_dict()
        assert d["operation_type"] == "move"
        assert d["status"] == "completed"
        assert d["timestamp"] == now.isoformat()
        assert d["created_at"] == "2026-01-01T00:00:00"

    # -- from_dict ----------------------------------------------------------

    def test_from_dict_minimal(self) -> None:
        data: dict[str, Any] = {
            "operation_type": "rename",
            "timestamp": "2026-02-26T12:00:00+00:00",
            "source_path": "/src/old.txt",
        }
        op = Operation.from_dict(data)
        assert op.operation_type is OperationType.RENAME
        assert isinstance(op.timestamp, datetime)
        assert op.source_path == Path("/src/old.txt")
        assert op.destination_path is None
        assert op.status is OperationStatus.COMPLETED
        assert op.metadata == {}

    def test_from_dict_full(self) -> None:
        data: dict[str, Any] = {
            "id": 7,
            "operation_type": "delete",
            "timestamp": "2026-02-26T12:00:00+00:00",
            "source_path": "/src/file.txt",
            "destination_path": "/dst/file.txt",
            "file_hash": "deadbeef",
            "metadata": {"permissions": "0644"},
            "transaction_id": "txn-abc",
            "status": "failed",
            "error_message": "disk full",
            "created_at": "2026-02-26T13:00:00+00:00",
        }
        op = Operation.from_dict(data)
        assert op.id == 7
        assert op.operation_type is OperationType.DELETE
        assert op.destination_path == Path("/dst/file.txt")
        assert op.file_hash == "deadbeef"
        assert op.metadata == {"permissions": "0644"}
        assert op.transaction_id == "txn-abc"
        assert op.status is OperationStatus.FAILED
        assert op.error_message == "disk full"
        assert isinstance(op.created_at, datetime)

    def test_from_dict_with_z_suffix_timestamp(self) -> None:
        """Timestamps ending in 'Z' are properly handled."""
        data: dict[str, Any] = {
            "operation_type": "move",
            "timestamp": "2026-02-26T12:00:00Z",
            "source_path": "/a",
        }
        op = Operation.from_dict(data)
        assert isinstance(op.timestamp, datetime)

    def test_from_dict_metadata_as_json_string(self) -> None:
        """Metadata stored as JSON string (from SQLite) is deserialized."""
        data: dict[str, Any] = {
            "operation_type": "move",
            "timestamp": "2026-02-26T12:00:00+00:00",
            "source_path": "/a",
            "metadata": '{"key": "value"}',
        }
        op = Operation.from_dict(data)
        assert op.metadata == {"key": "value"}

    def test_from_dict_with_datetime_objects(self) -> None:
        """When dict values are already datetime objects (not strings)."""
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        data: dict[str, Any] = {
            "operation_type": OperationType.MOVE,
            "timestamp": now,
            "source_path": "/a",
            "created_at": now,
        }
        op = Operation.from_dict(data)
        assert op.timestamp == now
        assert op.created_at == now

    def test_from_dict_with_enum_objects(self) -> None:
        """When dict values are already enum members."""
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        data: dict[str, Any] = {
            "operation_type": OperationType.CREATE,
            "timestamp": now,
            "source_path": "/a",
            "status": OperationStatus.PENDING,
        }
        op = Operation.from_dict(data)
        assert op.operation_type is OperationType.CREATE
        assert op.status is OperationStatus.PENDING

    def test_from_dict_created_at_z_suffix(self) -> None:
        data: dict[str, Any] = {
            "operation_type": "move",
            "timestamp": "2026-02-26T12:00:00+00:00",
            "source_path": "/a",
            "created_at": "2026-02-26T13:00:00Z",
        }
        op = Operation.from_dict(data)
        assert isinstance(op.created_at, datetime)

    def test_from_dict_no_created_at(self) -> None:
        data: dict[str, Any] = {
            "operation_type": "move",
            "timestamp": "2026-02-26T12:00:00+00:00",
            "source_path": "/a",
        }
        op = Operation.from_dict(data)
        assert op.created_at is None

    def test_from_dict_missing_status_defaults_to_completed(self) -> None:
        data: dict[str, Any] = {
            "operation_type": "move",
            "timestamp": "2026-02-26T12:00:00+00:00",
            "source_path": "/a",
        }
        op = Operation.from_dict(data)
        assert op.status is OperationStatus.COMPLETED

    # -- Round-trip ---------------------------------------------------------

    def test_round_trip(self, full_op: Operation) -> None:
        """to_dict -> from_dict should produce an equivalent Operation."""
        d = full_op.to_dict()
        restored = Operation.from_dict(d)
        assert restored.id == full_op.id
        assert restored.operation_type == full_op.operation_type
        assert restored.source_path == full_op.source_path
        assert restored.destination_path == full_op.destination_path
        assert restored.file_hash == full_op.file_hash
        assert restored.metadata == full_op.metadata
        assert restored.transaction_id == full_op.transaction_id
        assert restored.status == full_op.status
        assert restored.error_message == full_op.error_message

    def test_round_trip_minimal(self, minimal_op: Operation) -> None:
        d = minimal_op.to_dict()
        restored = Operation.from_dict(d)
        assert restored.operation_type == minimal_op.operation_type
        assert restored.source_path == minimal_op.source_path
        assert restored.destination_path is None

    # -- from_row -----------------------------------------------------------

    def test_from_row_delegates_to_from_dict(self) -> None:
        """from_row converts a row-like object to dict then to Operation."""
        mock_row = MagicMock()
        row_data = {
            "id": 1,
            "operation_type": "move",
            "timestamp": "2026-02-26T12:00:00+00:00",
            "source_path": "/src/file.txt",
            "destination_path": "/dst/file.txt",
            "file_hash": None,
            "metadata": "{}",
            "transaction_id": None,
            "status": "completed",
            "error_message": None,
            "created_at": None,
        }
        # sqlite3.Row supports dict(row)
        mock_row.__iter__ = MagicMock(return_value=iter(row_data.items()))
        mock_row.keys = MagicMock(return_value=row_data.keys())
        # dict(row) calls __iter__ or keys(); we mock via side_effect on dict()
        # Simpler: make mock behave like a mapping
        type(mock_row).__iter__ = lambda self: iter(row_data.items())
        type(mock_row).keys = lambda self: row_data.keys()
        type(mock_row).__getitem__ = lambda self, key: row_data[key]
        type(mock_row).__len__ = lambda self: len(row_data)

        op = Operation.from_row(mock_row)
        assert op.id == 1
        assert op.operation_type is OperationType.MOVE
        assert op.source_path == Path("/src/file.txt")

    # -- Edge cases ---------------------------------------------------------

    def test_all_operation_types_round_trip(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        for op_type in OperationType:
            op = Operation(
                operation_type=op_type,
                timestamp=now,
                source_path=Path("/test"),
            )
            restored = Operation.from_dict(op.to_dict())
            assert restored.operation_type is op_type

    def test_all_operation_statuses_round_trip(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        for status in OperationStatus:
            op = Operation(
                operation_type=OperationType.MOVE,
                timestamp=now,
                source_path=Path("/test"),
                status=status,
            )
            restored = Operation.from_dict(op.to_dict())
            assert restored.status is status


# ---------------------------------------------------------------------------
# Transaction Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestTransaction:
    """Tests for the Transaction dataclass."""

    @pytest.fixture()
    def now(self) -> datetime:
        return datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)

    @pytest.fixture()
    def minimal_txn(self, now: datetime) -> Transaction:
        return Transaction(
            transaction_id="txn-001",
            started_at=now,
        )

    @pytest.fixture()
    def full_txn(self, now: datetime) -> Transaction:
        return Transaction(
            transaction_id="txn-002",
            started_at=now,
            status=TransactionStatus.COMPLETED,
            completed_at=datetime(2026, 2, 26, 13, 0, 0, tzinfo=UTC),
            operation_count=5,
            metadata={"batch": "daily"},
        )

    # -- Construction -------------------------------------------------------

    def test_minimal_construction(self, minimal_txn: Transaction, now: datetime) -> None:
        assert minimal_txn.transaction_id == "txn-001"
        assert minimal_txn.started_at == now
        assert minimal_txn.status is TransactionStatus.IN_PROGRESS
        assert minimal_txn.completed_at is None
        assert minimal_txn.operation_count == 0
        assert minimal_txn.metadata == {}

    def test_full_construction(self, full_txn: Transaction, now: datetime) -> None:
        assert full_txn.transaction_id == "txn-002"
        assert full_txn.status is TransactionStatus.COMPLETED
        assert full_txn.completed_at is not None
        assert full_txn.operation_count == 5
        assert full_txn.metadata == {"batch": "daily"}

    def test_default_metadata_is_independent(self, now: datetime) -> None:
        txn1 = Transaction(transaction_id="a", started_at=now)
        txn2 = Transaction(transaction_id="b", started_at=now)
        txn1.metadata["x"] = 1
        assert "x" not in txn2.metadata

    # -- to_dict ------------------------------------------------------------

    def test_to_dict_minimal(self, minimal_txn: Transaction, now: datetime) -> None:
        d = minimal_txn.to_dict()
        assert d["transaction_id"] == "txn-001"
        assert d["started_at"] == now.isoformat()
        assert d["completed_at"] is None
        assert d["operation_count"] == 0
        assert d["status"] == "in_progress"
        assert d["metadata"] == {}

    def test_to_dict_full(self, full_txn: Transaction) -> None:
        d = full_txn.to_dict()
        assert d["transaction_id"] == "txn-002"
        assert d["status"] == "completed"
        assert d["completed_at"] is not None
        assert d["operation_count"] == 5
        assert d["metadata"] == {"batch": "daily"}

    def test_to_dict_handles_pre_serialized_strings(self, now: datetime) -> None:
        """Exercise isinstance branches when fields are already strings."""
        txn = Transaction(
            transaction_id="txn-str",
            started_at=now,
        )
        txn.started_at = now.isoformat()  # type: ignore[assignment]
        txn.status = "in_progress"  # type: ignore[assignment]
        txn.completed_at = "2026-02-26T13:00:00"  # type: ignore[assignment]
        d = txn.to_dict()
        assert d["started_at"] == now.isoformat()
        assert d["status"] == "in_progress"
        assert d["completed_at"] == "2026-02-26T13:00:00"

    # -- from_dict ----------------------------------------------------------

    def test_from_dict_minimal(self) -> None:
        data: dict[str, Any] = {
            "transaction_id": "txn-100",
            "started_at": "2026-02-26T12:00:00+00:00",
        }
        txn = Transaction.from_dict(data)
        assert txn.transaction_id == "txn-100"
        assert isinstance(txn.started_at, datetime)
        assert txn.status is TransactionStatus.IN_PROGRESS
        assert txn.completed_at is None
        assert txn.operation_count == 0
        assert txn.metadata == {}

    def test_from_dict_full(self) -> None:
        data: dict[str, Any] = {
            "transaction_id": "txn-200",
            "started_at": "2026-02-26T12:00:00+00:00",
            "completed_at": "2026-02-26T13:00:00+00:00",
            "operation_count": 10,
            "status": "completed",
            "metadata": {"source": "cli"},
        }
        txn = Transaction.from_dict(data)
        assert txn.transaction_id == "txn-200"
        assert txn.status is TransactionStatus.COMPLETED
        assert isinstance(txn.completed_at, datetime)
        assert txn.operation_count == 10
        assert txn.metadata == {"source": "cli"}

    def test_from_dict_z_suffix_timestamps(self) -> None:
        data: dict[str, Any] = {
            "transaction_id": "txn-z",
            "started_at": "2026-02-26T12:00:00Z",
            "completed_at": "2026-02-26T13:00:00Z",
        }
        txn = Transaction.from_dict(data)
        assert isinstance(txn.started_at, datetime)
        assert isinstance(txn.completed_at, datetime)

    def test_from_dict_metadata_as_json_string(self) -> None:
        data: dict[str, Any] = {
            "transaction_id": "txn-json",
            "started_at": "2026-02-26T12:00:00+00:00",
            "metadata": '{"key": "value"}',
        }
        txn = Transaction.from_dict(data)
        assert txn.metadata == {"key": "value"}

    def test_from_dict_with_datetime_objects(self) -> None:
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        later = datetime(2026, 2, 26, 13, 0, 0, tzinfo=UTC)
        data: dict[str, Any] = {
            "transaction_id": "txn-dt",
            "started_at": now,
            "completed_at": later,
        }
        txn = Transaction.from_dict(data)
        assert txn.started_at == now
        assert txn.completed_at == later

    def test_from_dict_with_enum_status(self) -> None:
        now = datetime(2026, 2, 26, 12, 0, 0, tzinfo=UTC)
        data: dict[str, Any] = {
            "transaction_id": "txn-enum",
            "started_at": now,
            "status": TransactionStatus.FAILED,
        }
        txn = Transaction.from_dict(data)
        assert txn.status is TransactionStatus.FAILED

    def test_from_dict_missing_status_defaults(self) -> None:
        data: dict[str, Any] = {
            "transaction_id": "txn-def",
            "started_at": "2026-02-26T12:00:00+00:00",
        }
        txn = Transaction.from_dict(data)
        assert txn.status is TransactionStatus.IN_PROGRESS

    def test_from_dict_no_completed_at(self) -> None:
        data: dict[str, Any] = {
            "transaction_id": "txn-nc",
            "started_at": "2026-02-26T12:00:00+00:00",
        }
        txn = Transaction.from_dict(data)
        assert txn.completed_at is None

    # -- Round-trip ---------------------------------------------------------

    def test_round_trip(self, full_txn: Transaction) -> None:
        d = full_txn.to_dict()
        restored = Transaction.from_dict(d)
        assert restored.transaction_id == full_txn.transaction_id
        assert restored.operation_count == full_txn.operation_count
        assert restored.status == full_txn.status
        assert restored.metadata == full_txn.metadata

    def test_round_trip_minimal(self, minimal_txn: Transaction) -> None:
        d = minimal_txn.to_dict()
        restored = Transaction.from_dict(d)
        assert restored.transaction_id == minimal_txn.transaction_id
        assert restored.status == minimal_txn.status
        assert restored.completed_at is None

    # -- from_row -----------------------------------------------------------

    def test_from_row_delegates_to_from_dict(self) -> None:
        mock_row = MagicMock()
        row_data = {
            "transaction_id": "txn-row",
            "started_at": "2026-02-26T12:00:00+00:00",
            "completed_at": None,
            "operation_count": 3,
            "status": "in_progress",
            "metadata": "{}",
        }
        type(mock_row).__iter__ = lambda self: iter(row_data.items())
        type(mock_row).keys = lambda self: row_data.keys()
        type(mock_row).__getitem__ = lambda self, key: row_data[key]
        type(mock_row).__len__ = lambda self: len(row_data)

        txn = Transaction.from_row(mock_row)
        assert txn.transaction_id == "txn-row"
        assert txn.operation_count == 3
        assert txn.status is TransactionStatus.IN_PROGRESS

    # -- Edge cases / all statuses ------------------------------------------

    def test_all_transaction_statuses_round_trip(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        for status in TransactionStatus:
            txn = Transaction(
                transaction_id=f"txn-{status.value}",
                started_at=now,
                status=status,
            )
            restored = Transaction.from_dict(txn.to_dict())
            assert restored.status is status

    def test_partially_rolled_back_status(self) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)
        txn = Transaction(
            transaction_id="txn-prb",
            started_at=now,
            status=TransactionStatus.PARTIALLY_ROLLED_BACK,
        )
        d = txn.to_dict()
        assert d["status"] == "partially_rolled_back"
        restored = Transaction.from_dict(d)
        assert restored.status is TransactionStatus.PARTIALLY_ROLLED_BACK
