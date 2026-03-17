"""Integration tests for history module branch coverage.

Targets uncovered branches in:
  - history/database.py   — double-init, execute_many, context manager,
                             transaction exception, get_database_size, close, __enter__/__exit__
  - history/transaction.py — commit/rollback guard branches (already-committed,
                              already-rolled-back, outside-context)
  - history/tracker.py    — hash failure, metadata failure, commit/rollback failure,
                             limit < 0 ValueError
  - history/export.py     — timezone-aware start_date / end_date branches
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path):
    from file_organizer.history.database import DatabaseManager

    db = DatabaseManager(tmp_path / "test.db")
    db.initialize()
    return db


def _make_history(tmp_path: Path):
    from file_organizer.history.tracker import OperationHistory

    return OperationHistory(tmp_path / "history.db")


# ---------------------------------------------------------------------------
# history/database.py
# ---------------------------------------------------------------------------


class TestDatabaseManagerBranches:
    def test_double_initialize_is_noop(self, tmp_path: Path) -> None:
        """Second call to initialize() returns early (line 93 branch)."""
        from file_organizer.history.database import DatabaseManager

        db = DatabaseManager(tmp_path / "db.sqlite")
        db.initialize()
        # Second call should hit the `if self._initialized: return` guard
        db.initialize()
        assert db._initialized is True

    def test_execute_many_inserts_rows(self, tmp_path: Path) -> None:
        """execute_many() runs executemany via transaction (lines 215-216)."""
        db = _make_db(tmp_path)
        query = "INSERT INTO operations (operation_type, source_path, timestamp, status) VALUES (?, ?, ?, ?)"
        params_list = [
            ("move", "/a/b", "2026-01-01T00:00:00Z", "completed"),
            ("move", "/c/d", "2026-01-02T00:00:00Z", "completed"),
        ]
        db.execute_many(query, params_list)
        count = db.get_operation_count()
        assert count == 2

    def test_get_database_size_existing_file(self, tmp_path: Path) -> None:
        """get_database_size() returns > 0 for a real on-disk DB (line 251 branch)."""
        db = _make_db(tmp_path)
        size = db.get_database_size()
        assert size > 0

    def test_context_manager_enter_exit(self, tmp_path: Path) -> None:
        """__enter__ / __exit__ work correctly (lines 282-283, 287)."""
        from file_organizer.history.database import DatabaseManager

        db_path = tmp_path / "ctx.db"
        with DatabaseManager(db_path) as db:
            assert db._initialized is True
        # After exit the connection may still exist; test that no exception was raised

    def test_transaction_context_exception_rolls_back(self, tmp_path: Path) -> None:
        """Exception inside db.transaction() triggers rollback (lines 186-189)."""
        db = _make_db(tmp_path)
        with pytest.raises(RuntimeError, match="deliberate"):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO operations (operation_type, source_path, timestamp, status)"
                    " VALUES ('move', '/x', '2026-01-01T00:00:00Z', 'completed')"
                )
                raise RuntimeError("deliberate")
        # Row was rolled back
        assert db.get_operation_count() == 0

    def test_close_noop_when_no_connection(self, tmp_path: Path) -> None:
        """close() is a no-op when _connection is already None."""
        from file_organizer.history.database import DatabaseManager

        db = DatabaseManager(tmp_path / "no_conn.db")
        db._connection = None
        db.close()  # Should not raise


# ---------------------------------------------------------------------------
# history/transaction.py
# ---------------------------------------------------------------------------


class TestOperationTransactionGuardBranches:
    def test_commit_outside_context_returns_false(self, tmp_path: Path) -> None:
        """commit() when transaction_id is None returns False (lines 252-254)."""
        from file_organizer.history.transaction import OperationTransaction

        history = _make_history(tmp_path)
        txn = OperationTransaction(history)
        # transaction_id is None — never entered context
        result = txn.commit()
        assert result is False

    def test_rollback_outside_context_returns_false(self, tmp_path: Path) -> None:
        """rollback() when transaction_id is None returns False (lines 276-278)."""
        from file_organizer.history.transaction import OperationTransaction

        history = _make_history(tmp_path)
        txn = OperationTransaction(history)
        result = txn.rollback()
        assert result is False

    def test_commit_already_rolled_back_returns_false(self, tmp_path: Path) -> None:
        """commit() on already-rolled-back txn returns False (lines 248-250)."""
        from file_organizer.history.transaction import OperationTransaction

        history = _make_history(tmp_path)
        with OperationTransaction(history) as txn:
            txn.rollback()
            # Now try to commit the already-rolled-back transaction
            result = txn.commit()
            assert result is False

    def test_rollback_already_rolled_back_returns_false(self, tmp_path: Path) -> None:
        """rollback() called twice returns False on second call (lines 268-270)."""
        from file_organizer.history.transaction import OperationTransaction

        history = _make_history(tmp_path)
        with OperationTransaction(history) as txn:
            txn.rollback()
            result = txn.rollback()
            assert result is False

    def test_rollback_already_committed_returns_false(self, tmp_path: Path) -> None:
        """rollback() after commit() returns False (lines 272-274)."""
        from file_organizer.history.transaction import OperationTransaction

        history = _make_history(tmp_path)
        with OperationTransaction(history) as txn:
            txn.commit()
            result = txn.rollback()
            assert result is False

    def test_context_exit_with_exception_calls_rollback(self, tmp_path: Path) -> None:
        """__exit__ on exception triggers rollback (not already-rolled-back path)."""
        from file_organizer.history.transaction import OperationTransaction

        history = _make_history(tmp_path)
        try:
            with OperationTransaction(history) as txn:
                raise ValueError("boom")
        except ValueError:
            pass
        assert txn._rolled_back is True
        assert txn._committed is False


# ---------------------------------------------------------------------------
# history/tracker.py
# ---------------------------------------------------------------------------


class TestOperationHistoryBranches:
    def test_log_operation_hash_failure_is_silenced(self, tmp_path: Path) -> None:
        """Exception in _calculate_file_hash is caught; op still logged (lines 71-72)."""
        from file_organizer.history.models import OperationType
        from file_organizer.history.tracker import OperationHistory

        tracker = OperationHistory(tmp_path / "h.db")
        src = tmp_path / "source.txt"
        src.write_text("hello")

        with patch.object(tracker, "_calculate_file_hash", side_effect=OSError("disk error")):
            op_id = tracker.log_operation(OperationType.MOVE, src)

        assert isinstance(op_id, int)

    def test_log_operation_stat_failure_is_silenced(self, tmp_path: Path) -> None:
        """Exception collecting stat metadata is caught; op still logged (lines 93-94).

        Uses a fake path object that overrides exists()/is_file() to return True while
        stat() raises PermissionError — bypassing the internal exists() → stat() chain.
        """
        import os

        from file_organizer.history.models import OperationType
        from file_organizer.history.tracker import OperationHistory

        # Create a real backing file so _calculate_file_hash(open(...)) works.
        real_src = tmp_path / "source2.txt"
        real_src.write_text("world")

        class PathWithFailingStat:
            """Fake path: exists=True, is_file=True, stat() raises."""

            def exists(self, **kw: object) -> bool:
                return True

            def is_file(self, **kw: object) -> bool:
                return True

            def stat(self, **kw: object) -> None:  # type: ignore[override]
                raise PermissionError("no access")

            def __str__(self) -> str:
                return str(real_src)

            def __fspath__(self) -> str:
                return os.fspath(real_src)

        tracker = OperationHistory(tmp_path / "h2.db")
        op_id = tracker.log_operation(OperationType.COPY, PathWithFailingStat())  # type: ignore[arg-type]
        assert isinstance(op_id, int)

    def test_commit_transaction_failure_returns_false(self, tmp_path: Path) -> None:
        """commit_transaction returns False when db.execute_query raises (lines 195-197)."""
        from file_organizer.history.tracker import OperationHistory

        tracker = OperationHistory(tmp_path / "h3.db")
        txn_id = tracker.start_transaction()

        with patch.object(tracker.db, "execute_query", side_effect=Exception("write error")):
            result = tracker.commit_transaction(txn_id)

        assert result is False

    def test_rollback_transaction_failure_returns_false(self, tmp_path: Path) -> None:
        """rollback_transaction returns False when db.transaction raises (lines 228-230)."""
        from file_organizer.history.tracker import OperationHistory

        tracker = OperationHistory(tmp_path / "h4.db")
        txn_id = tracker.start_transaction()

        with patch.object(tracker.db, "transaction", side_effect=Exception("lock error")):
            result = tracker.rollback_transaction(txn_id)

        assert result is False

    def test_get_operations_negative_limit_raises(self, tmp_path: Path) -> None:
        """get_operations with limit < 0 raises ValueError (line 287)."""
        from file_organizer.history.tracker import OperationHistory

        tracker = OperationHistory(tmp_path / "h5.db")
        with pytest.raises(ValueError, match="non-negative"):
            tracker.get_operations(limit=-1)


# ---------------------------------------------------------------------------
# history/export.py — timezone-aware datetime branches
# ---------------------------------------------------------------------------


class TestHistoryExporterTimezoneBranches:
    def _setup_exporter_with_ops(self, tmp_path: Path):
        """Create DB with one operation and return an exporter."""
        from file_organizer.history.database import DatabaseManager
        from file_organizer.history.export import HistoryExporter
        from file_organizer.history.models import OperationType
        from file_organizer.history.tracker import OperationHistory

        db_path = tmp_path / "export.db"
        history = OperationHistory(db_path)
        src = tmp_path / "file.txt"
        src.write_text("content")
        history.log_operation(OperationType.MOVE, src, tmp_path / "dest.txt")

        db = DatabaseManager(db_path)
        db.initialize()
        return HistoryExporter(db)

    def test_export_json_aware_start_date(self, tmp_path: Path) -> None:
        """export_to_json with tz-aware start_date hits else branch (line 76)."""
        exporter = self._setup_exporter_with_ops(tmp_path)
        # Timezone-aware datetime (not UTC — forces astimezone conversion)
        tokyo = timezone(timedelta(hours=9))
        aware_start = datetime(2020, 1, 1, tzinfo=tokyo)

        result = exporter.export_to_json(tmp_path / "out.json", start_date=aware_start)
        # 1 operation was inserted; start_date is in 2020 so it falls within range
        assert result["operations_exported"] == 1

    def test_export_json_aware_end_date(self, tmp_path: Path) -> None:
        """export_to_json with tz-aware end_date hits else branch (line 84)."""
        exporter = self._setup_exporter_with_ops(tmp_path)
        paris = timezone(timedelta(hours=1))
        aware_end = datetime(2030, 12, 31, tzinfo=paris)

        result = exporter.export_to_json(tmp_path / "out2.json", end_date=aware_end)
        # end_date is in 2030 so the inserted operation is within range
        assert result["operations_exported"] == 1

    def test_export_json_aware_start_and_end(self, tmp_path: Path) -> None:
        """export_to_json with both aware dates hits both else branches."""
        exporter = self._setup_exporter_with_ops(tmp_path)
        ny = timezone(timedelta(hours=-5))
        aware_start = datetime(2020, 1, 1, tzinfo=ny)
        aware_end = datetime(2030, 12, 31, tzinfo=ny)

        result = exporter.export_to_json(
            tmp_path / "out3.json", start_date=aware_start, end_date=aware_end
        )
        # Both dates bracket the inserted operation
        assert result["operations_exported"] == 1

    def test_export_csv_aware_start_date(self, tmp_path: Path) -> None:
        """export_to_csv with tz-aware start_date hits else branch (lines 162-163)."""
        exporter = self._setup_exporter_with_ops(tmp_path)
        tokyo = timezone(timedelta(hours=9))
        aware_start = datetime(2020, 1, 1, tzinfo=tokyo)

        count = exporter.export_to_csv(tmp_path / "ops.csv", start_date=aware_start)
        # start_date is in 2020; the inserted operation falls within range
        assert count == 1

    def test_export_csv_aware_end_date(self, tmp_path: Path) -> None:
        """export_to_csv with tz-aware end_date hits else branch (lines 170-171)."""
        exporter = self._setup_exporter_with_ops(tmp_path)
        paris = timezone(timedelta(hours=1))
        aware_end = datetime(2030, 12, 31, tzinfo=paris)

        count = exporter.export_to_csv(tmp_path / "ops2.csv", end_date=aware_end)
        # end_date is in 2030; the inserted operation falls within range
        assert count == 1

    def test_export_csv_aware_both_dates(self, tmp_path: Path) -> None:
        """export_to_csv with both aware dates hits both else branches."""
        exporter = self._setup_exporter_with_ops(tmp_path)
        ny = timezone(timedelta(hours=-5))
        aware_start = datetime(2020, 1, 1, tzinfo=ny)
        aware_end = datetime(2030, 12, 31, tzinfo=ny)

        count = exporter.export_to_csv(
            tmp_path / "ops3.csv", start_date=aware_start, end_date=aware_end
        )
        # Both dates bracket the inserted operation
        assert count == 1
