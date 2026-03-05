"""Coverage tests for HistoryCleanup — targets uncovered branches."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from file_organizer.history.cleanup import HistoryCleanup, HistoryCleanupConfig
from file_organizer.history.database import DatabaseManager

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    db_path = tmp_path / "test_history.db"
    mgr = DatabaseManager(db_path=db_path)
    mgr.initialize()
    return mgr


@pytest.fixture()
def cleanup(db):
    return HistoryCleanup(db=db)


def _insert_operation(db, timestamp=None, status="completed"):
    if timestamp is None:
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) "
            "VALUES (?, ?, ?, ?)",
            ("move", timestamp, "/src/file.txt", status),
        )


# ---------------------------------------------------------------------------
# HistoryCleanupConfig
# ---------------------------------------------------------------------------


class TestConfig:
    def test_defaults(self):
        cfg = HistoryCleanupConfig()
        assert cfg.max_operations == 10000
        assert cfg.max_age_days == 90
        assert cfg.max_size_mb == 100

    def test_custom(self):
        cfg = HistoryCleanupConfig(max_operations=100, max_age_days=7)
        assert cfg.max_operations == 100
        assert cfg.max_age_days == 7


# ---------------------------------------------------------------------------
# should_cleanup
# ---------------------------------------------------------------------------


class TestShouldCleanup:
    def test_disabled(self, db):
        cfg = HistoryCleanupConfig(auto_cleanup_enabled=False)
        c = HistoryCleanup(db=db, config=cfg)
        assert c.should_cleanup() is False

    def test_below_limits(self, cleanup):
        assert cleanup.should_cleanup() is False

    def test_over_operation_count(self, db):
        cfg = HistoryCleanupConfig(max_operations=2)
        c = HistoryCleanup(db=db, config=cfg)
        for _ in range(3):
            _insert_operation(db)
        assert c.should_cleanup() is True

    def test_over_size_limit(self, db):
        cfg = HistoryCleanupConfig(max_size_mb=0)
        c = HistoryCleanup(db=db, config=cfg)
        _insert_operation(db)
        assert c.should_cleanup() is True


# ---------------------------------------------------------------------------
# cleanup_old_operations
# ---------------------------------------------------------------------------


class TestCleanupOldOperations:
    def test_deletes_old_ops(self, db, cleanup):
        old_ts = (datetime.now(UTC) - timedelta(days=200)).isoformat().replace("+00:00", "Z")
        _insert_operation(db, timestamp=old_ts)
        _insert_operation(db)  # recent
        deleted = cleanup.cleanup_old_operations(max_age_days=90)
        assert deleted == 1

    def test_uses_config_default(self, db):
        cfg = HistoryCleanupConfig(max_age_days=1)
        c = HistoryCleanup(db=db, config=cfg)
        old_ts = (datetime.now(UTC) - timedelta(days=5)).isoformat().replace("+00:00", "Z")
        _insert_operation(db, timestamp=old_ts)
        deleted = c.cleanup_old_operations()
        assert deleted == 1


# ---------------------------------------------------------------------------
# cleanup_by_count
# ---------------------------------------------------------------------------


class TestCleanupByCount:
    def test_no_cleanup_needed(self, db, cleanup):
        _insert_operation(db)
        deleted = cleanup.cleanup_by_count(max_operations=100)
        assert deleted == 0

    def test_deletes_excess(self, db):
        cfg = HistoryCleanupConfig(max_operations=2)
        c = HistoryCleanup(db=db, config=cfg)
        for i in range(5):
            ts = (datetime.now(UTC) - timedelta(hours=5 - i)).isoformat().replace("+00:00", "Z")
            _insert_operation(db, timestamp=ts)
        deleted = c.cleanup_by_count(max_operations=2)
        assert deleted >= 1

    def test_delete_all_when_zero(self, db, cleanup):
        for _ in range(3):
            _insert_operation(db)
        deleted = cleanup.cleanup_by_count(max_operations=0)
        assert deleted == 3
        assert db.get_operation_count() == 0

    def test_negative_raises(self, cleanup):
        with pytest.raises(ValueError, match="non-negative"):
            cleanup.cleanup_by_count(max_operations=-1)


# ---------------------------------------------------------------------------
# cleanup_by_size
# ---------------------------------------------------------------------------


class TestCleanupBySize:
    def test_no_cleanup_needed(self, cleanup):
        deleted = cleanup.cleanup_by_size(max_size_mb=999)
        assert deleted == 0

    def test_cleanup_when_over_size(self, db):
        # Use a very small limit
        cfg = HistoryCleanupConfig(max_size_mb=0, cleanup_batch_size=5)
        c = HistoryCleanup(db=db, config=cfg)
        for _ in range(10):
            _insert_operation(db)
        deleted = c.cleanup_by_size(max_size_mb=0)
        assert deleted >= 1


# ---------------------------------------------------------------------------
# cleanup_failed_operations
# ---------------------------------------------------------------------------


class TestCleanupFailed:
    def test_deletes_old_failed(self, db, cleanup):
        old_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        _insert_operation(db, timestamp=old_ts, status="failed")
        _insert_operation(db, status="completed")
        deleted = cleanup.cleanup_failed_operations(older_than_days=7)
        assert deleted == 1

    def test_keeps_recent_failed(self, db, cleanup):
        _insert_operation(db, status="failed")
        deleted = cleanup.cleanup_failed_operations(older_than_days=7)
        assert deleted == 0


# ---------------------------------------------------------------------------
# cleanup_rolled_back_operations
# ---------------------------------------------------------------------------


class TestCleanupRolledBack:
    def test_deletes_old_rolled_back(self, db, cleanup):
        old_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat().replace("+00:00", "Z")
        _insert_operation(db, timestamp=old_ts, status="rolled_back")
        deleted = cleanup.cleanup_rolled_back_operations(older_than_days=7)
        assert deleted == 1


# ---------------------------------------------------------------------------
# auto_cleanup
# ---------------------------------------------------------------------------


class TestAutoCleanup:
    def test_not_needed(self, cleanup):
        result = cleanup.auto_cleanup()
        assert result["deleted_operations"] == 0

    def test_runs_when_needed(self, db):
        cfg = HistoryCleanupConfig(max_operations=2, max_age_days=1)
        c = HistoryCleanup(db=db, config=cfg)
        for i in range(5):
            ts = (datetime.now(UTC) - timedelta(days=5 - i)).isoformat().replace("+00:00", "Z")
            _insert_operation(db, timestamp=ts)
        result = c.auto_cleanup()
        assert result["deleted_operations"] >= 1


# ---------------------------------------------------------------------------
# clear_all
# ---------------------------------------------------------------------------


class TestClearAll:
    def test_without_confirm(self, cleanup, db):
        _insert_operation(db)
        assert cleanup.clear_all(confirm=False) is False
        assert db.get_operation_count() == 1

    def test_with_confirm(self, cleanup, db):
        _insert_operation(db)
        assert cleanup.clear_all(confirm=True) is True
        assert db.get_operation_count() == 0


# ---------------------------------------------------------------------------
# get_statistics
# ---------------------------------------------------------------------------


class TestGetStatistics:
    def test_empty_db(self, cleanup):
        stats = cleanup.get_statistics()
        assert stats["total_operations"] == 0

    def test_with_data(self, cleanup, db):
        _insert_operation(db, status="completed")
        _insert_operation(db, status="failed")
        stats = cleanup.get_statistics()
        assert stats["total_operations"] == 2
        assert stats["operations_completed"] == 1
        assert stats["operations_failed"] == 1
