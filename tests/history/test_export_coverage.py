"""Coverage tests for HistoryExporter — targets uncovered branches."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest

from file_organizer.history.database import DatabaseManager
from file_organizer.history.export import HistoryExporter
from file_organizer.history.models import OperationType

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    db_path = tmp_path / "export_test.db"
    mgr = DatabaseManager(db_path=db_path)
    mgr.initialize()
    return mgr


@pytest.fixture()
def exporter(db):
    return HistoryExporter(db=db)


def _insert_op(db, op_type="move", ts=None, status="completed", src="/a", dest="/b"):
    if ts is None:
        ts = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    metadata = json.dumps({"size": 100, "is_file": True, "is_dir": False})
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO operations (operation_type, timestamp, source_path, "
            "destination_path, status, metadata) VALUES (?, ?, ?, ?, ?, ?)",
            (op_type, ts, src, dest, status, metadata),
        )


# ---------------------------------------------------------------------------
# export_to_json
# ---------------------------------------------------------------------------


class TestExportToJson:
    def test_basic_json_export(self, exporter, db, tmp_path):
        _insert_op(db)
        out = tmp_path / "out" / "export.json"
        stats = exporter.export_to_json(out)
        assert stats["operations_exported"] == 1
        data = json.loads(out.read_text())
        assert data["operation_count"] == 1

    def test_json_empty(self, exporter, tmp_path):
        out = tmp_path / "empty.json"
        stats = exporter.export_to_json(out)
        assert stats["operations_exported"] == 0

    def test_json_filter_by_type(self, exporter, db, tmp_path):
        _insert_op(db, op_type="move")
        _insert_op(db, op_type="copy")
        out = tmp_path / "filtered.json"
        stats = exporter.export_to_json(out, operation_type=OperationType.MOVE)
        assert stats["operations_exported"] == 1

    def test_json_filter_by_type_string(self, exporter, db, tmp_path):
        _insert_op(db, op_type="move")
        out = tmp_path / "filtered_str.json"
        stats = exporter.export_to_json(out, operation_type="move")
        assert stats["operations_exported"] == 1

    def test_json_filter_by_start_date_naive(self, exporter, db, tmp_path):
        old_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        _insert_op(db, ts=old_ts)
        out = tmp_path / "start.json"
        start = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=5)  # naive datetime
        stats = exporter.export_to_json(out, start_date=start)
        assert stats["operations_exported"] == 0

    def test_json_filter_by_start_date_aware(self, exporter, db, tmp_path):
        _insert_op(db)
        out = tmp_path / "start_aware.json"
        start = datetime.now(UTC) - timedelta(hours=1)
        stats = exporter.export_to_json(out, start_date=start)
        assert stats["operations_exported"] == 1

    def test_json_filter_by_end_date_naive(self, exporter, db, tmp_path):
        _insert_op(db)
        out = tmp_path / "end.json"
        # Use UTC-based time to ensure end_date is after the stored timestamp,
        # then strip tzinfo to make it naive (exercises the replace(tzinfo=UTC) branch)
        end = datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)
        stats = exporter.export_to_json(out, end_date=end)
        assert stats["operations_exported"] == 1

    def test_json_filter_by_end_date_aware(self, exporter, db, tmp_path):
        _insert_op(db)
        out = tmp_path / "end_aware.json"
        tz_offset = timezone(timedelta(hours=5))
        end = datetime.now(tz_offset) + timedelta(hours=1)
        stats = exporter.export_to_json(out, end_date=end)
        assert stats["operations_exported"] == 1

    def test_json_no_transactions(self, exporter, db, tmp_path):
        _insert_op(db)
        out = tmp_path / "no_txn.json"
        exporter.export_to_json(out, include_transactions=False)
        data = json.loads(out.read_text())
        assert "transactions" not in data


# ---------------------------------------------------------------------------
# export_to_csv
# ---------------------------------------------------------------------------


class TestExportToCsv:
    def test_csv_basic(self, exporter, db, tmp_path):
        _insert_op(db)
        out = tmp_path / "out" / "export.csv"
        count = exporter.export_to_csv(out)
        assert count == 1
        assert out.exists()

    def test_csv_empty(self, exporter, tmp_path):
        out = tmp_path / "empty.csv"
        count = exporter.export_to_csv(out)
        assert count == 0

    def test_csv_filter_by_type(self, exporter, db, tmp_path):
        _insert_op(db, op_type="move")
        _insert_op(db, op_type="copy")
        out = tmp_path / "typed.csv"
        count = exporter.export_to_csv(out, operation_type=OperationType.MOVE)
        assert count == 1


# ---------------------------------------------------------------------------
# export_transactions_to_csv
# ---------------------------------------------------------------------------


class TestExportTransactionsCsv:
    def test_no_transactions(self, exporter, tmp_path):
        out = tmp_path / "txn.csv"
        count = exporter.export_transactions_to_csv(out)
        assert count == 0


# ---------------------------------------------------------------------------
# export_statistics
# ---------------------------------------------------------------------------


class TestExportStatistics:
    def test_stats_empty(self, exporter, tmp_path):
        out = tmp_path / "stats.json"
        result = exporter.export_statistics(out)
        assert result is True
        data = json.loads(out.read_text())
        assert data["total_operations"] == 0

    def test_stats_with_data(self, exporter, db, tmp_path):
        _insert_op(db, op_type="move")
        _insert_op(db, op_type="copy", status="failed")
        out = tmp_path / "stats2.json"
        exporter.export_statistics(out)
        data = json.loads(out.read_text())
        assert data["total_operations"] == 2
