"""Coverage tests for history DatabaseManager — targets uncovered branches."""

from __future__ import annotations

import pytest

from file_organizer.history.database import DatabaseManager

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    db_path = tmp_path / "test.db"
    mgr = DatabaseManager(db_path=db_path)
    mgr.initialize()
    return mgr


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_exit(self, tmp_path):
        db_path = tmp_path / "ctx.db"
        with DatabaseManager(db_path=db_path) as mgr:
            assert mgr._initialized is True
        assert mgr._connection is None


# ---------------------------------------------------------------------------
# Double init guard
# ---------------------------------------------------------------------------


class TestDoubleInit:
    def test_second_init_noop(self, db):
        db.initialize()  # Should not raise


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------


class TestMigration:
    def test_migrate(self, db):
        conn = db.get_connection()
        db._migrate(1, 2, conn)
        cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        assert cursor.fetchone()[0] == 2


# ---------------------------------------------------------------------------
# Transaction rollback
# ---------------------------------------------------------------------------


class TestTransaction:
    def test_rollback_on_error(self, db):
        with pytest.raises(ValueError):
            with db.transaction():
                raise ValueError("boom")


# ---------------------------------------------------------------------------
# execute_query / execute_many / fetch_one / fetch_all
# ---------------------------------------------------------------------------


class TestExecute:
    def test_execute_query_no_params(self, db):
        cursor = db.execute_query("SELECT COUNT(*) FROM operations")
        row = cursor.fetchone()
        assert row[0] == 0

    def test_execute_query_with_params(self, db):
        cursor = db.execute_query(
            "SELECT COUNT(*) FROM operations WHERE status = ?", ("completed",)
        )
        row = cursor.fetchone()
        assert row[0] == 0

    def test_execute_many(self, db):
        db.execute_many(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) "
            "VALUES (?, ?, ?, ?)",
            [
                ("move", "2025-01-01", "/a", "completed"),
                ("copy", "2025-01-02", "/b", "completed"),
            ],
        )
        assert db.get_operation_count() == 2

    def test_fetch_one_returns_none(self, db):
        result = db.fetch_one("SELECT * FROM operations WHERE id = ?", (9999,))
        assert result is None

    def test_fetch_all(self, db):
        db.execute_many(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) "
            "VALUES (?, ?, ?, ?)",
            [
                ("move", "2025-01-01", "/a", "completed"),
                ("copy", "2025-01-02", "/b", "completed"),
            ],
        )
        rows = db.fetch_all("SELECT * FROM operations")
        assert len(rows) == 2


# ---------------------------------------------------------------------------
# get_database_size / get_operation_count / vacuum
# ---------------------------------------------------------------------------


class TestDbOps:
    def test_database_size(self, db):
        size = db.get_database_size()
        assert size > 0

    def test_database_size_missing_file(self, tmp_path):
        mgr = DatabaseManager(db_path=tmp_path / "nope.db")
        assert mgr.get_database_size() == 0

    def test_operation_count(self, db):
        assert db.get_operation_count() == 0

    def test_vacuum(self, db):
        db.vacuum()  # Should not raise


# ---------------------------------------------------------------------------
# close
# ---------------------------------------------------------------------------


class TestClose:
    def test_close(self, db):
        db.close()
        assert db._connection is None

    def test_close_twice(self, db):
        db.close()
        db.close()  # Should not raise
