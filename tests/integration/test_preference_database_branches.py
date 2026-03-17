"""Integration tests for preference_database module branch coverage.

Targets uncovered branches in:
  - PreferenceDatabaseManager.__init__: db_path=None default path
  - PreferenceDatabaseManager.initialize: double-init guard (outer + inner),
      first-time schema version insert, migration branch,
      exception → rollback
  - PreferenceDatabaseManager._migrate: method body
  - PreferenceDatabaseManager.transaction: exception → rollback
  - PreferenceDatabaseManager.close: with/without connection
  - PreferenceDatabaseManager.__enter__ / __exit__
  - PreferenceDatabaseManager.add_preference: pref_id is None → RuntimeError
  - PreferenceDatabaseManager.get_preference: context JSON parse branch
  - PreferenceDatabaseManager.get_preferences_by_type: context JSON parse
  - PreferenceDatabaseManager.get_corrections: metadata JSON parse branch
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path):
    from file_organizer.services.intelligence.preference_database import (
        PreferenceDatabaseManager,
    )

    db = PreferenceDatabaseManager(tmp_path / "prefs.db")
    db.initialize()
    return db


# ---------------------------------------------------------------------------
# __init__ — db_path=None branch
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseInit:
    def test_default_db_path_uses_data_dir(self, tmp_path: Path) -> None:
        """db_path=None triggers get_data_dir() import + path construction (lines 129-132).

        The import inside __init__ is lazy (`from file_organizer.config.path_manager
        import get_data_dir`), so we patch the source at the path_manager level.
        """
        from file_organizer.services.intelligence.preference_database import (
            PreferenceDatabaseManager,
        )

        fake_dir = tmp_path / "data_dir"
        fake_dir.mkdir(parents=True)

        with patch(
            "file_organizer.config.path_manager.get_data_dir",
            return_value=fake_dir,
        ):
            db = PreferenceDatabaseManager()
            assert db.db_path == fake_dir / "preferences.db"

    def test_explicit_db_path_used(self, tmp_path: Path) -> None:
        """Explicit db_path is stored as-is."""
        from file_organizer.services.intelligence.preference_database import (
            PreferenceDatabaseManager,
        )

        path = tmp_path / "explicit.db"
        db = PreferenceDatabaseManager(path)
        assert db.db_path == path


# ---------------------------------------------------------------------------
# initialize() — guard branches
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseInitialize:
    def test_double_initialize_outer_guard_is_noop(self, tmp_path: Path) -> None:
        """Second call hits `if self._initialized: return` outer guard (line 145-146)."""
        db = _make_db(tmp_path)
        assert db._initialized is True
        # Should not raise and should return early
        db.initialize()
        assert db._initialized is True

    def test_initialize_inner_lock_guard(self, tmp_path: Path) -> None:
        """Inner double-checked-locking guard (line 149-150) deterministically exercised.

        Thread-1 acquires _lock and holds it until Thread-2 has passed the outer
        ``if self._initialized`` check.  Thread-2 then blocks on the lock, enters
        the critical section after Thread-1 releases it, and hits the inner guard
        (``_initialized`` is already True) — returning early without re-running setup.
        """
        from file_organizer.services.intelligence.preference_database import (
            PreferenceDatabaseManager,
        )

        db = PreferenceDatabaseManager(tmp_path / "concurrent.db")
        inner_guard_hit: list[bool] = []

        # Event: signals that Thread-1 has acquired the lock and is inside init
        t1_inside = threading.Event()
        # Event: signals that Thread-2 has passed the outer check and is waiting
        t2_ready = threading.Event()

        original_initialize = PreferenceDatabaseManager.initialize

        # Spy on get_connection — only called when init proceeds past the inner guard.
        # Thread-2 hitting the inner guard must result in call_count == 1 (Thread-1 only).
        mock_get_connection = MagicMock(side_effect=db.get_connection)
        db.get_connection = mock_get_connection  # type: ignore[method-assign]

        def t1_init() -> None:
            """Hold the lock until Thread-2 is ready, then complete initialization."""
            with db._lock:
                t1_inside.set()  # tell Thread-2 the lock is held
                t2_ready.wait(timeout=5)  # wait until Thread-2 is past outer check
                original_initialize(db)

        def t2_init() -> None:
            """Pass outer check, then wait until Thread-1 owns the lock."""
            t1_inside.wait(timeout=5)  # ensure Thread-1 holds the lock first
            # _initialized is still False here → passes outer guard
            assert not db._initialized
            t2_ready.set()  # tell Thread-1 we're committed
            # acquire lock — blocks until Thread-1 releases it
            original_initialize(db)
            # get_connection count == 1 proves Thread-2 returned via the inner guard
            # without running setup again (get_connection is called only past line 149-150).
            if mock_get_connection.call_count == 1:
                inner_guard_hit.append(True)

        t1 = threading.Thread(target=t1_init)
        t2 = threading.Thread(target=t2_init)

        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert db._initialized is True
        assert mock_get_connection.call_count == 1  # only Thread-1 ran past the inner guard
        assert len(inner_guard_hit) == 1

    def test_first_time_schema_version_inserted(self, tmp_path: Path) -> None:
        """First initialization inserts schema version record (lines 172-176)."""
        from file_organizer.services.intelligence.preference_database import (
            PreferenceDatabaseManager,
        )

        db = PreferenceDatabaseManager(tmp_path / "fresh.db")
        db.initialize()

        conn = db.get_connection()
        cursor = conn.execute("SELECT version FROM schema_version")
        rows = cursor.fetchall()
        assert len(rows) == 1
        assert rows[0][0] == PreferenceDatabaseManager.SCHEMA_VERSION

    def test_migration_branch_when_schema_version_is_old(self, tmp_path: Path) -> None:
        """Migration branch triggered when stored version < SCHEMA_VERSION (lines 178-181)."""
        from file_organizer.services.intelligence.preference_database import (
            PreferenceDatabaseManager,
        )

        # Create and initialize a fresh DB
        db = PreferenceDatabaseManager(tmp_path / "migrate.db")
        db.initialize()

        # Manually downgrade schema version to 0
        conn = db.get_connection()
        conn.execute("UPDATE schema_version SET version = 0")
        conn.commit()

        # Create a new manager pointing at the same file (fresh _initialized state)
        db2 = PreferenceDatabaseManager(tmp_path / "migrate.db")
        # Initialize should see version 0 < 1 → call _migrate
        db2.initialize()
        assert db2._initialized is True

        # After migration, schema_version should have a new record for version 1
        cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        latest = cursor.fetchone()[0]
        assert latest == PreferenceDatabaseManager.SCHEMA_VERSION

    def test_initialize_exception_triggers_rollback(self, tmp_path: Path) -> None:
        """Exception in initialize() calls conn.rollback() and re-raises (lines 187-190).

        sqlite3.Connection is a C extension — its methods are read-only and
        cannot be patched directly.  Instead, patch get_connection() to return a
        MagicMock whose executescript raises so the except-branch fires.
        """
        from file_organizer.services.intelligence.preference_database import (
            PreferenceDatabaseManager,
        )

        db = PreferenceDatabaseManager(tmp_path / "failinit.db")

        mock_conn = MagicMock()
        mock_conn.executescript.side_effect = RuntimeError("schema boom")

        with patch.object(db, "get_connection", return_value=mock_conn):
            with pytest.raises(RuntimeError, match="schema boom"):
                db.initialize()

        # rollback must have been called
        mock_conn.rollback.assert_called_once()
        # _initialized must remain False
        assert db._initialized is False


# ---------------------------------------------------------------------------
# _migrate() — method body
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseMigrate:
    def test_migrate_inserts_version_record(self, tmp_path: Path) -> None:
        """_migrate() inserts target version into schema_version (lines 200-208)."""
        from file_organizer.services.intelligence.preference_database import (
            PreferenceDatabaseManager,
        )

        db = PreferenceDatabaseManager(tmp_path / "mig.db")
        db.initialize()
        conn = db.get_connection()

        # Call _migrate directly with fake version numbers
        db._migrate(0, 99, conn)
        conn.commit()

        cursor = conn.execute("SELECT version FROM schema_version WHERE version = 99")
        assert cursor.fetchone() is not None


# ---------------------------------------------------------------------------
# transaction() — exception rollback
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseTransaction:
    def test_transaction_exception_rolls_back(self, tmp_path: Path) -> None:
        """Exception inside transaction() triggers rollback (lines 239-243)."""
        db = _make_db(tmp_path)

        with pytest.raises(ValueError, match="tx_fail"):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO preferences "
                    "(preference_type, key, value, confidence, frequency, "
                    "created_at, updated_at, source) "
                    "VALUES ('test', 'k1', 'v1', 0.5, 1, "
                    "'2026-01-01Z', '2026-01-01Z', 'user')"
                )
                raise ValueError("tx_fail")

        # Row was rolled back
        result = db.get_preference("test", "k1")
        assert result is None


# ---------------------------------------------------------------------------
# close() — connection branches
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseClose:
    def test_close_with_active_connection(self, tmp_path: Path) -> None:
        """close() when _connection is set — closes and sets to None (lines 247-250)."""
        db = _make_db(tmp_path)
        assert db._connection is not None
        db.close()
        assert db._connection is None

    def test_close_no_connection_is_noop(self, tmp_path: Path) -> None:
        """close() when _connection is already None — no-op (line 248 false branch)."""
        from file_organizer.services.intelligence.preference_database import (
            PreferenceDatabaseManager,
        )

        db = PreferenceDatabaseManager(tmp_path / "noconn.db")
        db._connection = None
        db.close()  # Should not raise
        assert db._connection is None


# ---------------------------------------------------------------------------
# __enter__ / __exit__ context manager
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseContextManager:
    def test_context_manager_initializes_and_closes(self, tmp_path: Path) -> None:
        """__enter__ calls initialize(); __exit__ calls close() (lines 253-260)."""
        from file_organizer.services.intelligence.preference_database import (
            PreferenceDatabaseManager,
        )

        db_path = tmp_path / "ctx.db"
        with PreferenceDatabaseManager(db_path) as db:
            assert db._initialized is True
            assert db._connection is not None
        # After exit, connection should be closed
        assert db._connection is None


# ---------------------------------------------------------------------------
# add_preference() — pref_id is None RuntimeError
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseAddPreference:
    def test_add_preference_returns_id(self, tmp_path: Path) -> None:
        """Normal add_preference returns a positive integer ID."""
        db = _make_db(tmp_path)
        pref_id = db.add_preference("folder_mapping", "docs", "/Documents")
        assert isinstance(pref_id, int)
        assert pref_id > 0

    def test_add_preference_pref_id_none_raises_runtime_error(self, tmp_path: Path) -> None:
        """RuntimeError raised when cursor.fetchone() returns None (lines 324-325).

        sqlite3.Connection.execute is a C extension method (read-only), so we
        patch get_connection() to return a MagicMock that produces a cursor
        whose fetchone() returns None.
        """
        db = _make_db(tmp_path)

        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_cursor

        with patch.object(db, "get_connection", return_value=mock_conn):
            with pytest.raises(RuntimeError, match="Failed to retrieve preference ID"):
                db.add_preference("folder_mapping", "key_x", "val_x")

    def test_add_preference_upsert_increments_frequency(self, tmp_path: Path) -> None:
        """Adding the same preference twice increments frequency via ON CONFLICT."""
        db = _make_db(tmp_path)
        db.add_preference("folder_mapping", "photos", "/Photos", frequency=1)
        db.add_preference("folder_mapping", "photos", "/Photos", frequency=1)

        row = db.get_preference("folder_mapping", "photos")
        assert row is not None
        assert row["frequency"] >= 2


# ---------------------------------------------------------------------------
# get_preference() — context JSON parse
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseGetPreference:
    def test_get_preference_with_context_json_parsed(self, tmp_path: Path) -> None:
        """get_preference() parses context JSON when present (line 355-356)."""
        db = _make_db(tmp_path)
        ctx: dict[str, Any] = {"source_type": "automatic", "confidence": 0.9}
        db.add_preference("folder_mapping", "docs_ctx", "/Docs", context=ctx)

        result = db.get_preference("folder_mapping", "docs_ctx")
        assert result is not None
        assert isinstance(result["context"], dict)
        assert result["context"]["source_type"] == "automatic"

    def test_get_preference_without_context_returns_null(self, tmp_path: Path) -> None:
        """get_preference() returns None for context when not set."""
        db = _make_db(tmp_path)
        db.add_preference("folder_mapping", "no_ctx", "/NoCtx")

        result = db.get_preference("folder_mapping", "no_ctx")
        assert result is not None
        assert result["context"] is None

    def test_get_preference_not_found_returns_none(self, tmp_path: Path) -> None:
        """get_preference() returns None when key does not exist."""
        db = _make_db(tmp_path)
        assert db.get_preference("folder_mapping", "nonexistent") is None


# ---------------------------------------------------------------------------
# get_preferences_by_type() — context JSON parse
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseGetPreferencesByType:
    def test_get_preferences_by_type_with_context_parsed(self, tmp_path: Path) -> None:
        """get_preferences_by_type() parses context JSON for each row (lines 385-386)."""
        db = _make_db(tmp_path)
        ctx1: dict[str, Any] = {"tag": "work"}
        ctx2: dict[str, Any] = {"tag": "personal"}
        db.add_preference("category_override", "invoice", "financial", context=ctx1)
        db.add_preference("category_override", "photo", "media", context=ctx2)

        results = db.get_preferences_by_type("category_override")
        assert len(results) == 2
        for r in results:
            assert isinstance(r["context"], dict)
            assert "tag" in r["context"]

    def test_get_preferences_by_type_no_context_is_null(self, tmp_path: Path) -> None:
        """get_preferences_by_type() leaves context as None when not stored."""
        db = _make_db(tmp_path)
        db.add_preference("naming_pattern", "sep_dash", "hyphen")

        results = db.get_preferences_by_type("naming_pattern")
        assert len(results) == 1
        assert results[0]["context"] is None

    def test_get_preferences_by_type_empty_when_none(self, tmp_path: Path) -> None:
        """Returns empty list when no preferences of that type exist."""
        db = _make_db(tmp_path)
        assert db.get_preferences_by_type("nonexistent_type") == []


# ---------------------------------------------------------------------------
# get_corrections() — metadata JSON parse
# ---------------------------------------------------------------------------


class TestPreferenceDatabaseGetCorrections:
    def test_get_corrections_with_metadata_parsed(self, tmp_path: Path) -> None:
        """get_corrections() parses metadata JSON when present (lines 537-538)."""
        db = _make_db(tmp_path)
        meta: dict[str, Any] = {"reason": "user_moved", "confidence": 0.85}
        db.add_correction(
            correction_type="file_move",
            source_path=str(tmp_path / "file.txt"),
            destination_path=str(tmp_path / "docs" / "file.txt"),
            metadata=meta,
        )

        corrections = db.get_corrections()
        assert len(corrections) == 1
        assert isinstance(corrections[0]["metadata"], dict)
        assert corrections[0]["metadata"]["reason"] == "user_moved"

    def test_get_corrections_without_metadata_is_null(self, tmp_path: Path) -> None:
        """get_corrections() leaves metadata as None when not stored."""
        db = _make_db(tmp_path)
        db.add_correction(
            correction_type="file_rename",
            source_path=str(tmp_path / "old.txt"),
            destination_path=str(tmp_path / "new.txt"),
        )

        corrections = db.get_corrections()
        assert len(corrections) == 1
        assert corrections[0]["metadata"] is None

    def test_get_corrections_filtered_by_type(self, tmp_path: Path) -> None:
        """correction_type filter returns only matching rows."""
        db = _make_db(tmp_path)
        db.add_correction("file_move", "/a/b.txt", "/c/b.txt")
        db.add_correction("file_rename", "/a/old.txt", "/a/new.txt")

        moves = db.get_corrections(correction_type="file_move")
        assert len(moves) == 1
        assert moves[0]["correction_type"] == "file_move"

    def test_get_corrections_unfiltered_returns_all(self, tmp_path: Path) -> None:
        """No correction_type filter returns all rows."""
        db = _make_db(tmp_path)
        db.add_correction("file_move", "/a.txt", "/b.txt")
        db.add_correction("file_rename", "/c.txt", "/d.txt")

        all_corrections = db.get_corrections()
        assert len(all_corrections) == 2
