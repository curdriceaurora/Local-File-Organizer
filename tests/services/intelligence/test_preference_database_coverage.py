"""Coverage tests for PreferenceDatabaseManager — targets uncovered branches."""

from __future__ import annotations

import pytest

from file_organizer.services.intelligence.preference_database import (
    PreferenceDatabaseManager,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def db(tmp_path):
    """Create a PreferenceDatabaseManager backed by a temp dir."""
    db_path = tmp_path / "test.db"
    mgr = PreferenceDatabaseManager(db_path=db_path)
    mgr.initialize()
    return mgr


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_exit(self, tmp_path):
        db_path = tmp_path / "ctx.db"
        with PreferenceDatabaseManager(db_path=db_path) as mgr:
            assert mgr._initialized is True
        # After exit, connection should be closed
        assert mgr._connection is None


# ---------------------------------------------------------------------------
# Double initialisation guard
# ---------------------------------------------------------------------------


class TestDoubleInit:
    def test_second_init_is_noop(self, db):
        db.initialize()  # Should not raise


# ---------------------------------------------------------------------------
# Migration path
# ---------------------------------------------------------------------------


class TestMigration:
    def test_migrate_inserts_new_version(self, db):
        conn = db.get_connection()
        db._migrate(1, 2, conn)
        cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        assert row[0] == 2


# ---------------------------------------------------------------------------
# Transaction context manager
# ---------------------------------------------------------------------------


class TestTransaction:
    def test_transaction_commit(self, db):
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO preferences "
                "(preference_type, key, value, confidence, frequency, "
                "created_at, updated_at, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                ("test", "k1", "v1", 0.5, 1, "2025-01-01", "2025-01-01", "test"),
            )
        pref = db.get_preference("test", "k1")
        assert pref is not None

    def test_transaction_rollback_on_error(self, db):
        with pytest.raises(ValueError):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO preferences "
                    "(preference_type, key, value, confidence, frequency, "
                    "created_at, updated_at, source) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    ("test", "rollback_key", "v1", 0.5, 1, "2025-01-01", "2025-01-01", "test"),
                )
                raise ValueError("boom")
        # The row written inside the transaction must not be visible after rollback
        assert db.get_preference("test", "rollback_key") is None


# ---------------------------------------------------------------------------
# CRUD: add / get / update / delete / increment
# ---------------------------------------------------------------------------


class TestCRUD:
    def test_add_preference_returns_id(self, db):
        pid = db.add_preference("folder_mapping", "key1", "val1", confidence=0.9)
        assert isinstance(pid, int)
        assert pid > 0

    def test_add_preference_upsert_increments_frequency(self, db):
        db.add_preference("folder_mapping", "k", "v1")
        db.add_preference("folder_mapping", "k", "v2")
        pref = db.get_preference("folder_mapping", "k")
        assert pref["frequency"] == 2
        assert pref["value"] == "v2"

    def test_add_preference_with_context(self, db):
        db.add_preference("naming", "k", "v", context={"source_dir": "tmp"})
        pref = db.get_preference("naming", "k")
        assert pref["context"] == {"source_dir": "tmp"}

    def test_get_preference_not_found(self, db):
        assert db.get_preference("nope", "nope") is None

    def test_get_preference_without_context(self, db):
        db.add_preference("t", "k", "v")
        pref = db.get_preference("t", "k")
        assert pref["context"] is None

    def test_get_preferences_by_type(self, db):
        db.add_preference("cat", "k1", "v1", confidence=0.9)
        db.add_preference("cat", "k2", "v2", confidence=0.3)
        db.add_preference("other", "k3", "v3")
        results = db.get_preferences_by_type("cat")
        assert len(results) == 2
        # Should be sorted by confidence DESC
        assert results[0]["confidence"] >= results[1]["confidence"]

    def test_get_preferences_by_type_with_context(self, db):
        db.add_preference("cat", "k1", "v1", context={"a": 1})
        results = db.get_preferences_by_type("cat")
        assert results[0]["context"] == {"a": 1}

    def test_update_confidence(self, db):
        pid = db.add_preference("t", "k", "v", confidence=0.5)
        db.update_preference_confidence(pid, 0.99)
        pref = db.get_preference("t", "k")
        assert pref["confidence"] == 0.99

    def test_increment_usage(self, db):
        pid = db.add_preference("t", "k", "v", frequency=1)
        db.increment_preference_usage(pid)
        pref = db.get_preference("t", "k")
        assert pref["frequency"] == 2

    def test_delete_preference(self, db):
        pid = db.add_preference("t", "k", "v")
        db.delete_preference(pid)
        assert db.get_preference("t", "k") is None


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------


class TestCorrections:
    def test_add_and_get_corrections(self, db):
        cid = db.add_correction(
            "file_move",
            "src/a.txt",
            destination_path="dst/a.txt",
            category_old="misc",
            category_new="docs",
            confidence_before=0.3,
            confidence_after=0.8,
            metadata={"reason": "user"},
        )
        assert cid > 0
        corrections = db.get_corrections(correction_type="file_move")
        assert len(corrections) == 1
        assert corrections[0]["metadata"] == {"reason": "user"}

    def test_get_corrections_all_types(self, db):
        db.add_correction("file_move", "a.txt")
        db.add_correction("rename", "b.txt")
        all_corrections = db.get_corrections()
        assert len(all_corrections) == 2

    def test_get_corrections_without_metadata(self, db):
        db.add_correction("move", "a.txt")
        corrections = db.get_corrections()
        assert corrections[0]["metadata"] is None


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


class TestStatistics:
    def test_stats_empty(self, db):
        stats = db.get_preference_stats()
        assert stats["total_preferences"] == 0
        assert stats["average_confidence"] == 0.0

    def test_stats_with_data(self, db):
        db.add_preference("cat_a", "k1", "v1", confidence=0.8)
        db.add_preference("cat_a", "k2", "v2", confidence=0.6)
        db.add_preference("cat_b", "k3", "v3", confidence=0.4)
        stats = db.get_preference_stats()
        assert stats["total_preferences"] == 3
        assert stats["average_confidence"] > 0
        assert "cat_a" in stats["by_type"]
        assert "cat_b" in stats["by_type"]


# ---------------------------------------------------------------------------
# Close / reopen
# ---------------------------------------------------------------------------


class TestCloseReopen:
    def test_close_then_reopen(self, tmp_path):
        db_path = tmp_path / "test.db"
        mgr = PreferenceDatabaseManager(db_path=db_path)
        mgr.initialize()
        mgr.add_preference("t", "k", "v")
        mgr.close()
        assert mgr._connection is None
        # Reopen
        conn = mgr.get_connection()
        assert conn is not None
