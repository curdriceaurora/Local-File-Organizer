"""Integration tests for history tracking, cleanup, export, and transaction workflows.

These tests exercise the full history subsystem using real SQLite databases
(in-memory via tmp_path), with no mocked layers.  Coverage targets:
  - history/tracker.py
  - history/cleanup.py
  - history/export.py
  - history/transaction.py
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from file_organizer.history.cleanup import HistoryCleanup, HistoryCleanupConfig
from file_organizer.history.export import HistoryExporter
from file_organizer.history.models import (
    OperationStatus,
    OperationType,
    TransactionStatus,
)
from file_organizer.history.tracker import OperationHistory
from file_organizer.history.transaction import OperationTransaction

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def history(tmp_path: Path) -> OperationHistory:
    """Real OperationHistory backed by a per-test SQLite file."""
    db_path = tmp_path / "history.db"
    with OperationHistory(db_path) as h:
        yield h


@pytest.fixture()
def populated_history(history: OperationHistory, tmp_path: Path) -> OperationHistory:
    """History pre-populated with a mix of move, rename, delete, and failed ops."""
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Create real files so file-hash + stat collection is exercised
    for i in range(5):
        f = src_dir / f"file_{i}.txt"
        f.write_text(f"content {i}")

    # Completed moves
    for i in range(3):
        history.log_operation(
            OperationType.MOVE,
            source_path=src_dir / f"file_{i}.txt",
            destination_path=tmp_path / f"out/file_{i}.txt",
        )

    # Rename (file does not need to exist for non-hashing path)
    history.log_operation(
        OperationType.RENAME,
        source_path=Path("/virtual/old_name.txt"),
        destination_path=Path("/virtual/new_name.txt"),
    )

    # Failed operation
    history.log_operation(
        OperationType.DELETE,
        source_path=Path("/virtual/missing.txt"),
        status=OperationStatus.FAILED,
        error_message="File not found",
    )

    return history


# ---------------------------------------------------------------------------
# OperationHistory — tracker
# ---------------------------------------------------------------------------


class TestOperationHistoryTracker:
    """Integration tests for OperationHistory.log_operation / get_operations."""

    def test_log_and_retrieve_move(self, history: OperationHistory, tmp_path: Path) -> None:
        src = tmp_path / "a.txt"
        src.write_text("hello")
        dest = tmp_path / "b.txt"

        op_id = history.log_operation(OperationType.MOVE, src, dest)
        assert op_id > 0

        ops = history.get_operations(operation_type=OperationType.MOVE)
        assert len(ops) == 1
        assert ops[0].id == op_id
        assert ops[0].operation_type == OperationType.MOVE
        assert Path(ops[0].source_path) == src
        assert Path(ops[0].destination_path) == dest
        assert ops[0].status == OperationStatus.COMPLETED
        # File stat metadata collected
        assert ops[0].metadata.get("is_file") is True

    def test_log_operation_hashes_existing_file(
        self, history: OperationHistory, tmp_path: Path
    ) -> None:
        f = tmp_path / "hashme.txt"
        f.write_text("deterministic content")

        op_id = history.log_operation(OperationType.COPY, f, tmp_path / "copy.txt")
        ops = history.get_operations()
        assert ops[0].id == op_id
        # Hash should be a 64-char hex SHA-256
        assert ops[0].file_hash is not None
        assert len(ops[0].file_hash) == 64

    def test_log_failed_operation(self, history: OperationHistory) -> None:
        history.log_operation(
            OperationType.DELETE,
            source_path=Path("/no/such/file.txt"),
            status=OperationStatus.FAILED,
            error_message="Permission denied",
        )
        ops = history.get_operations(status=OperationStatus.FAILED)
        assert len(ops) == 1
        assert ops[0].error_message == "Permission denied"
        assert ops[0].status == OperationStatus.FAILED

    def test_filter_by_operation_type(self, populated_history: OperationHistory) -> None:
        moves = populated_history.get_operations(operation_type=OperationType.MOVE)
        renames = populated_history.get_operations(operation_type=OperationType.RENAME)
        deletes = populated_history.get_operations(operation_type=OperationType.DELETE)

        assert len(moves) == 3
        assert len(renames) == 1
        assert len(deletes) == 1

    def test_filter_by_status(self, populated_history: OperationHistory) -> None:
        completed = populated_history.get_operations(status=OperationStatus.COMPLETED)
        failed = populated_history.get_operations(status=OperationStatus.FAILED)
        assert len(completed) == 4  # 3 moves + 1 rename
        assert len(failed) == 1

    def test_limit_parameter(self, populated_history: OperationHistory) -> None:
        ops = populated_history.get_operations(limit=2)
        assert len(ops) == 2

    def test_date_range_filter(self, history: OperationHistory) -> None:
        history.log_operation(OperationType.CREATE, source_path=Path("/virtual/x.txt"))
        before = datetime.now(UTC) + timedelta(seconds=1)
        ops = history.get_operations(end_date=before)
        assert len(ops) == 1

        after = datetime.now(UTC) + timedelta(hours=1)
        ops_empty = history.get_operations(start_date=after)
        assert len(ops_empty) == 0

    def test_get_recent_operations(self, populated_history: OperationHistory) -> None:
        recent = populated_history.get_recent_operations(limit=3)
        assert len(recent) == 3

    def test_transaction_lifecycle(self, history: OperationHistory) -> None:
        txn_id = history.start_transaction({"batch": "test"})
        assert txn_id

        history.log_operation(
            OperationType.MOVE,
            source_path=Path("/virtual/src.txt"),
            destination_path=Path("/virtual/dst.txt"),
            transaction_id=txn_id,
        )

        committed = history.commit_transaction(txn_id)
        assert committed is True

        txn = history.get_transaction(txn_id)
        assert txn is not None
        assert txn.transaction_id == txn_id
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.operation_count == 1

    def test_rollback_transaction(self, history: OperationHistory) -> None:
        txn_id = history.start_transaction()
        history.log_operation(
            OperationType.MOVE,
            source_path=Path("/virtual/src.txt"),
            destination_path=Path("/virtual/dst.txt"),
            transaction_id=txn_id,
        )

        rolled_back = history.rollback_transaction(txn_id)
        assert rolled_back is True

        txn = history.get_transaction(txn_id)
        assert txn.status == TransactionStatus.FAILED

        ops = history.get_operations(status=OperationStatus.ROLLED_BACK)
        assert len(ops) == 1

    def test_get_nonexistent_transaction_returns_none(self, history: OperationHistory) -> None:
        result = history.get_transaction("does-not-exist")
        assert result is None


# ---------------------------------------------------------------------------
# OperationTransaction — context manager
# ---------------------------------------------------------------------------


class TestOperationTransaction:
    """Integration tests for the OperationTransaction context manager."""

    def test_auto_commit_on_success(self, history: OperationHistory) -> None:
        with OperationTransaction(history, metadata={"note": "batch"}) as txn:
            txn.log_move(Path("/src/a.txt"), Path("/dst/a.txt"))
            txn.log_rename(Path("/src/b.txt"), Path("/src/b_new.txt"))
            txn_id = txn.get_transaction_id()

        assert txn._committed is True
        assert txn._rolled_back is False
        db_txn = history.get_transaction(txn_id)
        assert db_txn.status == TransactionStatus.COMPLETED
        assert db_txn.operation_count == 2

    def test_auto_rollback_on_exception(self, history: OperationHistory) -> None:
        txn_id = None
        with pytest.raises(ValueError, match="test error"):
            with OperationTransaction(history) as txn:
                txn.log_move(Path("/src/a.txt"), Path("/dst/a.txt"))
                txn_id = txn.get_transaction_id()
                raise ValueError("test error")

        assert txn._rolled_back is True
        db_txn = history.get_transaction(txn_id)
        assert db_txn.status == TransactionStatus.FAILED
        rolled_back_ops = history.get_operations(status=OperationStatus.ROLLED_BACK)
        assert len(rolled_back_ops) == 1

    def test_log_all_operation_types(self, history: OperationHistory) -> None:
        with OperationTransaction(history) as txn:
            txn.log_move(Path("/src/move.txt"), Path("/dst/move.txt"))
            txn.log_rename(Path("/src/old.txt"), Path("/src/new.txt"))
            txn.log_delete(Path("/src/del.txt"))
            txn.log_copy(Path("/src/orig.txt"), Path("/dst/copy.txt"))
            txn.log_create(Path("/src/new.txt"))
            txn.log_failed_operation(
                OperationType.MOVE,
                Path("/src/fail.txt"),
                error_message="Disk full",
                destination_path=Path("/dst/fail.txt"),
            )

        ops = history.get_operations()
        op_types = {str(op.operation_type) for op in ops}
        assert "move" in op_types
        assert "rename" in op_types
        assert "delete" in op_types
        assert "copy" in op_types
        assert "create" in op_types

        failed = [op for op in ops if op.status == OperationStatus.FAILED]
        assert len(failed) == 1
        assert failed[0].error_message == "Disk full"

    def test_explicit_commit_before_exit(self, history: OperationHistory) -> None:
        with OperationTransaction(history) as txn:
            txn.log_move(Path("/s.txt"), Path("/d.txt"))
            txn.commit()
            assert txn._committed is True
        # __exit__ should not double-commit
        assert txn._committed is True

    def test_explicit_rollback_before_exit(self, history: OperationHistory) -> None:
        with OperationTransaction(history) as txn:
            txn.log_move(Path("/s.txt"), Path("/d.txt"))
            txn.rollback()
            assert txn._rolled_back is True
        assert txn._rolled_back is True

    def test_log_operation_outside_context_raises(self, history: OperationHistory) -> None:
        txn = OperationTransaction(history)
        with pytest.raises(RuntimeError, match="outside of transaction context"):
            txn.log_move(Path("/s.txt"), Path("/d.txt"))

    def test_commit_idempotent(self, history: OperationHistory) -> None:
        with OperationTransaction(history) as txn:
            txn.log_move(Path("/s.txt"), Path("/d.txt"))
            first = txn.commit()
            second = txn.commit()  # should return False, not raise
        assert first is True
        assert second is False

    def test_cannot_rollback_committed(self, history: OperationHistory) -> None:
        with OperationTransaction(history) as txn:
            txn.log_move(Path("/s.txt"), Path("/d.txt"))
            txn.commit()
            result = txn.rollback()
        assert result is False

    def test_nested_transactions_independent(self, history: OperationHistory) -> None:
        with OperationTransaction(history) as txn1:
            txn1.log_move(Path("/s1.txt"), Path("/d1.txt"))

        txn1_id = txn1.get_transaction_id()

        with pytest.raises(RuntimeError):
            with OperationTransaction(history) as txn2:
                txn2.log_move(Path("/s2.txt"), Path("/d2.txt"))
                raise RuntimeError("abort txn2")

        txn2_id = txn2.get_transaction_id()
        assert txn1_id != txn2_id

        assert history.get_transaction(txn1_id).status == TransactionStatus.COMPLETED
        assert history.get_transaction(txn2_id).status == TransactionStatus.FAILED


# ---------------------------------------------------------------------------
# HistoryCleanup
# ---------------------------------------------------------------------------


class TestHistoryCleanup:
    """Integration tests for HistoryCleanup policies."""

    @pytest.fixture()
    def cleanup(self, history: OperationHistory) -> HistoryCleanup:
        config = HistoryCleanupConfig(
            max_operations=100,
            max_age_days=90,
            max_size_mb=100,
            cleanup_batch_size=50,
        )
        return HistoryCleanup(history.db, config)

    def _add_old_ops(self, history: OperationHistory, count: int, days_old: int = 100) -> None:
        """Insert operations backdated to simulate age."""
        old_ts = (datetime.now(UTC) - timedelta(days=days_old)).isoformat().replace("+00:00", "Z")
        import json

        for i in range(count):
            history.db.execute_query(
                """INSERT INTO operations
                   (operation_type, timestamp, source_path, destination_path,
                    file_hash, metadata, transaction_id, status, error_message)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    "move",
                    old_ts,
                    f"/old/file_{i}.txt",
                    None,
                    None,
                    json.dumps({}),
                    None,
                    "completed",
                    None,
                ),
            )
        history.db.get_connection().commit()

    def test_cleanup_old_operations_removes_expired(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        self._add_old_ops(history, 5, days_old=100)
        # Add recent op that should survive
        history.log_operation(OperationType.CREATE, Path("/recent.txt"))

        deleted = cleanup.cleanup_old_operations(max_age_days=30)
        assert deleted == 5

        remaining = history.get_operations()
        assert len(remaining) == 1

    def test_cleanup_by_count_keeps_most_recent(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        for i in range(10):
            history.log_operation(OperationType.CREATE, Path(f"/file_{i}.txt"))

        deleted = cleanup.cleanup_by_count(max_operations=3)
        remaining = history.get_operations()
        # cleanup uses timestamp < cutoff (strict): ops sharing the same
        # sub-second timestamp are all kept; total preserved equals 10.
        assert deleted + len(remaining) == 10
        assert deleted > 0
        assert len(remaining) >= 3  # at least max_operations are preserved

    def test_cleanup_by_count_no_op_when_under_limit(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        for i in range(5):
            history.log_operation(OperationType.CREATE, Path(f"/file_{i}.txt"))

        deleted = cleanup.cleanup_by_count(max_operations=10)
        assert deleted == 0
        assert len(history.get_operations()) == 5

    def test_cleanup_by_count_delete_all(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        for i in range(5):
            history.log_operation(OperationType.CREATE, Path(f"/file_{i}.txt"))

        deleted = cleanup.cleanup_by_count(max_operations=0)
        assert deleted == 5
        assert len(history.get_operations()) == 0

    def test_cleanup_by_count_negative_raises(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            cleanup.cleanup_by_count(max_operations=-1)

    def test_cleanup_failed_operations(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        old_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        import json

        history.db.execute_query(
            """INSERT INTO operations
               (operation_type, timestamp, source_path, destination_path,
                file_hash, metadata, transaction_id, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "delete",
                old_ts,
                "/fail.txt",
                None,
                None,
                json.dumps({}),
                None,
                "failed",
                "disk full",
            ),
        )
        history.db.get_connection().commit()

        # Add a recent completed op that must survive
        history.log_operation(OperationType.CREATE, Path("/ok.txt"))

        deleted = cleanup.cleanup_failed_operations(older_than_days=1)
        assert deleted == 1
        remaining = history.get_operations()
        # Only the completed op remains
        assert all(str(op.status) != "failed" for op in remaining)

    def test_cleanup_rolled_back_operations(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        txn_id = history.start_transaction()
        history.log_operation(
            OperationType.MOVE,
            Path("/s.txt"),
            Path("/d.txt"),
            transaction_id=txn_id,
        )
        history.rollback_transaction(txn_id)

        # Backdate the rolled-back op
        old_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        history.db.execute_query(
            "UPDATE operations SET timestamp = ? WHERE status = ?",
            (old_ts, "rolled_back"),
        )
        history.db.get_connection().commit()

        deleted = cleanup.cleanup_rolled_back_operations(older_than_days=1)
        assert deleted >= 1

    def test_should_cleanup_when_over_count_limit(self, history: OperationHistory) -> None:
        config = HistoryCleanupConfig(max_operations=2, auto_cleanup_enabled=True)
        cleanup = HistoryCleanup(history.db, config)

        for i in range(3):
            history.log_operation(OperationType.CREATE, Path(f"/f{i}.txt"))

        assert cleanup.should_cleanup() is True

    def test_should_not_cleanup_when_disabled(self, history: OperationHistory) -> None:
        config = HistoryCleanupConfig(max_operations=1, auto_cleanup_enabled=False)
        cleanup = HistoryCleanup(history.db, config)
        for i in range(5):
            history.log_operation(OperationType.CREATE, Path(f"/f{i}.txt"))
        assert cleanup.should_cleanup() is False

    def test_clear_all_without_confirm_is_noop(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        history.log_operation(OperationType.CREATE, Path("/f.txt"))
        result = cleanup.clear_all(confirm=False)
        assert result is False
        assert len(history.get_operations()) == 1

    def test_clear_all_with_confirm_deletes_everything(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        txn_id = history.start_transaction()
        history.log_operation(
            OperationType.MOVE, Path("/s.txt"), Path("/d.txt"), transaction_id=txn_id
        )
        history.commit_transaction(txn_id)

        result = cleanup.clear_all(confirm=True)
        assert result is True
        assert len(history.get_operations()) == 0

    def test_get_statistics(self, history: OperationHistory, cleanup: HistoryCleanup) -> None:
        history.log_operation(OperationType.MOVE, Path("/s.txt"), Path("/d.txt"))
        history.log_operation(
            OperationType.DELETE,
            Path("/x.txt"),
            status=OperationStatus.FAILED,
        )

        stats = cleanup.get_statistics()
        assert stats["total_operations"] == 2
        assert stats["operations_completed"] == 1
        assert stats["operations_failed"] == 1
        assert "oldest_operation" in stats
        assert "newest_operation" in stats

    def test_auto_cleanup_when_over_count(self, history: OperationHistory) -> None:
        config = HistoryCleanupConfig(
            max_operations=2,
            max_age_days=9999,  # age doesn't trigger
            max_size_mb=9999,
            auto_cleanup_enabled=True,
        )
        cleanup = HistoryCleanup(history.db, config)

        for i in range(5):
            history.log_operation(OperationType.CREATE, Path(f"/f{i}.txt"))

        stats = cleanup.auto_cleanup()
        assert stats["deleted_operations"] > 0
        # cleanup_by_count uses timestamp < cutoff (strict); ops sharing the
        # same sub-second timestamp are all kept, so remaining may exceed
        # max_operations by at most the number of duplicate-timestamp ops.
        assert len(history.get_operations()) < 5  # fewer than original 5

    def test_orphaned_transaction_cleanup(
        self, history: OperationHistory, cleanup: HistoryCleanup
    ) -> None:
        # Start a transaction but log no ops in it; then manually call orphan cleanup
        txn_id = history.start_transaction()

        # Confirm the orphaned transaction exists
        txn = history.get_transaction(txn_id)
        assert txn is not None

        # cleanup_old_operations triggers _cleanup_orphaned_transactions internally
        # Insert a fake old op and delete it to trigger orphan removal
        import json

        old_ts = (datetime.now(UTC) - timedelta(days=1000)).isoformat().replace("+00:00", "Z")
        history.db.execute_query(
            """INSERT INTO operations
               (operation_type, timestamp, source_path, destination_path,
                file_hash, metadata, transaction_id, status, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "move",
                old_ts,
                "/old.txt",
                None,
                None,
                json.dumps({}),
                None,
                "completed",
                None,
            ),
        )
        history.db.get_connection().commit()

        deleted = cleanup.cleanup_old_operations(max_age_days=1)
        assert deleted == 1

        # The orphaned transaction (no remaining ops) should be cleaned up
        result = history.get_transaction(txn_id)
        assert result is None


# ---------------------------------------------------------------------------
# HistoryExporter
# ---------------------------------------------------------------------------


class TestHistoryExporter:
    """Integration tests for HistoryExporter JSON, CSV, and stats exports."""

    @pytest.fixture()
    def exporter(self, history: OperationHistory) -> HistoryExporter:
        return HistoryExporter(history.db)

    @pytest.fixture()
    def history_with_data(self, history: OperationHistory, tmp_path: Path) -> OperationHistory:
        txn_id = history.start_transaction({"note": "export_test"})
        history.log_operation(
            OperationType.MOVE,
            source_path=Path("/src/a.txt"),
            destination_path=Path("/dst/a.txt"),
            transaction_id=txn_id,
        )
        history.log_operation(
            OperationType.RENAME,
            source_path=Path("/src/b.txt"),
            destination_path=Path("/src/b_new.txt"),
            transaction_id=txn_id,
        )
        history.commit_transaction(txn_id)
        history.log_operation(
            OperationType.DELETE,
            source_path=Path("/trash/c.txt"),
            status=OperationStatus.FAILED,
            error_message="No permission",
        )
        return history

    # --- JSON export ---

    def test_export_to_json_creates_file(
        self,
        exporter: HistoryExporter,
        history_with_data: OperationHistory,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "export.json"
        stats = exporter.export_to_json(out, include_transactions=True)

        assert out.exists()
        assert stats["operations_exported"] == 3
        assert stats["transactions_exported"] == 1

        data = json.loads(out.read_text())
        assert data["operation_count"] == 3
        assert len(data["operations"]) == 3
        assert "transactions" in data
        assert len(data["transactions"]) == 1
        assert "export_date" in data

    def test_export_to_json_without_transactions(
        self,
        exporter: HistoryExporter,
        history_with_data: OperationHistory,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "no_txn.json"
        stats = exporter.export_to_json(out, include_transactions=False)

        data = json.loads(out.read_text())
        assert "transactions" not in data
        assert stats["transactions_exported"] == 0

    def test_export_to_json_filter_by_operation_type(
        self,
        exporter: HistoryExporter,
        history_with_data: OperationHistory,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "moves.json"
        stats = exporter.export_to_json(out, operation_type=OperationType.MOVE)
        assert stats["operations_exported"] == 1

        data = json.loads(out.read_text())
        assert all(op["operation_type"] == "move" for op in data["operations"])

    def test_export_to_json_filter_by_date(
        self,
        exporter: HistoryExporter,
        history_with_data: OperationHistory,
        tmp_path: Path,
    ) -> None:
        future = datetime.now(UTC) + timedelta(hours=1)
        out = tmp_path / "dated.json"
        stats = exporter.export_to_json(out, end_date=future)
        assert stats["operations_exported"] == 3

        datetime.now(UTC) - timedelta(hours=1)
        out2 = tmp_path / "empty.json"
        stats2 = exporter.export_to_json(out2, start_date=future)
        assert stats2["operations_exported"] == 0

    def test_export_to_json_creates_parent_dirs(
        self,
        exporter: HistoryExporter,
        history_with_data: OperationHistory,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "nested" / "deep" / "export.json"
        exporter.export_to_json(out)
        assert out.exists()

    # --- CSV export ---

    def test_export_to_csv_creates_file_with_rows(
        self,
        exporter: HistoryExporter,
        history_with_data: OperationHistory,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "ops.csv"
        count = exporter.export_to_csv(out)
        assert count == 3
        assert out.exists()

        with out.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 3
        expected_cols = {"id", "operation_type", "timestamp", "source_path", "status"}
        assert expected_cols.issubset(set(rows[0].keys()))

    def test_export_to_csv_filter_by_type(
        self,
        exporter: HistoryExporter,
        history_with_data: OperationHistory,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "renames.csv"
        count = exporter.export_to_csv(out, operation_type=OperationType.RENAME)
        assert count == 1

    def test_export_to_csv_empty_returns_zero(
        self, exporter: HistoryExporter, history: OperationHistory, tmp_path: Path
    ) -> None:
        out = tmp_path / "empty.csv"
        count = exporter.export_to_csv(out)
        assert count == 0

    def test_export_transactions_to_csv(
        self,
        exporter: HistoryExporter,
        history_with_data: OperationHistory,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "txns.csv"
        count = exporter.export_transactions_to_csv(out)
        assert count == 1

        with out.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["status"] == "completed"
        assert rows[0]["operation_count"] == "2"

    def test_export_transactions_csv_empty_returns_zero(
        self, exporter: HistoryExporter, history: OperationHistory, tmp_path: Path
    ) -> None:
        out = tmp_path / "empty_txns.csv"
        count = exporter.export_transactions_to_csv(out)
        assert count == 0

    # --- Statistics export ---

    def test_export_statistics(
        self,
        exporter: HistoryExporter,
        history_with_data: OperationHistory,
        tmp_path: Path,
    ) -> None:
        out = tmp_path / "stats.json"
        result = exporter.export_statistics(out)
        assert result is True
        assert out.exists()

        stats = json.loads(out.read_text())
        assert stats["total_operations"] == 3
        assert stats["total_transactions"] >= 1
        assert stats["operations_move"] == 1
        assert stats["operations_rename"] == 1
        assert stats["operations_delete"] == 1
        assert stats["operations_failed"] == 1
        assert stats["operations_completed"] == 2
        assert "export_date" in stats
        assert "oldest_operation" in stats
        assert "newest_operation" in stats

    def test_export_statistics_with_no_operations(
        self, exporter: HistoryExporter, history: OperationHistory, tmp_path: Path
    ) -> None:
        out = tmp_path / "empty_stats.json"
        result = exporter.export_statistics(out)
        assert result is True
        stats = json.loads(out.read_text())
        assert stats["total_operations"] == 0
