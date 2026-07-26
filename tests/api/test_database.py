"""Tests for file_organizer.api.database."""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from file_organizer.api.database import (
    SQLITE_BUSY_TIMEOUT_MS,
    create_session,
    get_engine,
    get_session_factory,
    resolve_database_url,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _clear_lru_caches():
    """Clear engine/session LRU caches before and after each test."""
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    yield
    get_engine.cache_clear()
    get_session_factory.cache_clear()


class TestResolveDatabaseUrl:
    """Tests for resolve_database_url."""

    def test_memory_database(self):
        assert resolve_database_url(":memory:") == "sqlite+pysqlite:///:memory:"

    def test_memory_with_whitespace(self):
        assert resolve_database_url("  :memory:  ") == "sqlite+pysqlite:///:memory:"

    def test_relative_path(self):
        result = resolve_database_url("data/app.db")
        assert result == "sqlite+pysqlite:///data/app.db"

    def test_absolute_path(self):
        result = resolve_database_url("/tmp/app.db")  # noqa: test-hardcoded-paths
        assert result == "sqlite+pysqlite:////tmp/app.db"

    def test_backslash_normalized(self):
        result = resolve_database_url("data\\app.db")
        assert result == "sqlite+pysqlite:///data/app.db"

    def test_full_sqlite_url_passthrough(self):
        url = "sqlite+pysqlite:///mydb.sqlite"
        result = resolve_database_url(url)
        assert "mydb.sqlite" in result

    def test_postgresql_url_passthrough(self):
        url = "postgresql+psycopg://user:pass@localhost/dbname"
        result = resolve_database_url(url)
        assert "postgresql" in result
        assert "dbname" in result

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            resolve_database_url("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="cannot be empty"):
            resolve_database_url("   ")

    def test_null_byte_raises(self):
        with pytest.raises(ValueError, match="null byte"):
            resolve_database_url("db\x00.sqlite")

    def test_semicolon_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_database_url("db.sqlite; DROP TABLE users")

    def test_sql_comment_raises(self):
        with pytest.raises(ValueError, match="invalid characters"):
            resolve_database_url("db.sqlite--malicious")


class TestGetEngine:
    """Tests for get_engine."""

    def test_memory_engine_uses_static_pool(self):
        engine = get_engine(":memory:")
        assert isinstance(engine, Engine)
        assert isinstance(engine.pool, StaticPool)

    def test_engine_is_cached(self):
        engine1 = get_engine(":memory:")
        engine2 = get_engine(":memory:")
        assert engine1 is engine2

    def test_different_databases_different_engines(self):
        engine1 = get_engine(":memory:")
        engine2 = get_engine("test_other.db")
        assert engine1 is not engine2
        engine2.dispose()

    def test_echo_flag(self):
        engine = get_engine(":memory:", echo=True)
        assert engine.echo is True
        get_engine.cache_clear()


class TestSqliteBusyTimeout:
    """File-backed SQLite must wait for a lock instead of giving up.

    Regression cover for the Playwright E2E flake where
    ``POST /api/v1/auth/register`` died with
    ``sqlite3.OperationalError: database is locked`` on
    ``PRAGMA main.table_info("users")``: the reflection read was blocked by a
    concurrent writer and hit pysqlite's 5 s default timeout.
    """

    def test_file_engine_sets_busy_timeout(self, tmp_path: Path) -> None:
        engine = get_engine(str(tmp_path / "app.db"))
        with engine.connect() as conn:
            busy_ms = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        # Must exceed pysqlite's 5 s default, which the flake blew through.
        assert int(busy_ms) > 5_000

    def test_memory_engine_left_at_default(self) -> None:
        """The pragma is for file-lock contention, which :memory: cannot have.

        5000 ms is pysqlite's own default, from ``connect(timeout=5.0)`` -- the
        very timeout the flake blew through on a file-backed database. Seeing it
        here confirms the listener is file-only rather than global.
        """
        engine = get_engine(":memory:")
        with engine.connect() as conn:
            busy_ms = conn.exec_driver_sql("PRAGMA busy_timeout").scalar()
        assert int(busy_ms) == 5_000
        assert int(busy_ms) != SQLITE_BUSY_TIMEOUT_MS

    def test_reader_waits_out_a_writer_past_the_default_timeout(self, tmp_path: Path) -> None:
        """A schema read must survive a writer holding the lock over 5 s.

        This is the exact CI failure: ``PRAGMA main.table_info(...)`` raising
        "database is locked" after pysqlite's 5 s default. The read is still
        blocked — rollback-journal mode blocks readers behind an EXCLUSIVE
        lock — but it now waits for the writer rather than giving up.
        """
        db_path = tmp_path / "app.db"
        engine = get_engine(str(db_path))
        with engine.begin() as conn:
            conn.exec_driver_sql("CREATE TABLE users (id INTEGER PRIMARY KEY)")

        holding = threading.Event()
        release = threading.Event()

        def _hold_write_lock() -> None:
            conn = sqlite3.connect(str(db_path), timeout=30.0, isolation_level=None)
            try:
                # EXCLUSIVE, not IMMEDIATE: a RESERVED lock never blocks readers,
                # so IMMEDIATE would pass even in rollback-journal mode and prove
                # nothing. EXCLUSIVE is what a committing writer holds.
                conn.execute("BEGIN EXCLUSIVE")
                conn.execute("INSERT INTO users (id) VALUES (1)")
                holding.set()
                release.wait(timeout=30)
                conn.execute("COMMIT")
            finally:
                conn.close()

        # Long enough to blow through pysqlite's 5 s default, short enough to
        # stay well inside the configured timeout.
        hold_seconds = 6.0

        writer = threading.Thread(target=_hold_write_lock, daemon=True)
        writer.start()
        try:
            assert holding.wait(timeout=10), "writer never acquired the lock"
            timer = threading.Timer(hold_seconds, release.set)
            timer.daemon = True
            timer.start()
            started = time.monotonic()
            with engine.connect() as conn:
                rows = conn.exec_driver_sql('PRAGMA main.table_info("users")').fetchall()
            elapsed = time.monotonic() - started
            timer.cancel()
        finally:
            release.set()
            writer.join(timeout=30)

        assert rows, "reflection returned no columns for the users table"
        # It must have genuinely waited past the 5 s default rather than
        # squeezing in early -- otherwise the test would pass without the
        # pragma and prove nothing.
        assert elapsed > 5.0, f"read completed in {elapsed:.1f}s, before the old timeout"
        assert elapsed < SQLITE_BUSY_TIMEOUT_MS / 1000, "read consumed the whole timeout"


class TestGetSessionFactory:
    """Tests for get_session_factory."""

    def test_factory_returns_callable(self):
        factory = get_session_factory(":memory:")
        assert callable(factory)

    def test_factory_is_cached(self):
        f1 = get_session_factory(":memory:")
        f2 = get_session_factory(":memory:")
        assert f1 is f2


class TestCreateSession:
    """Tests for create_session."""

    def test_create_session_returns_session(self):
        session = create_session(":memory:")
        assert isinstance(session, Session)
        session.close()

    def test_create_session_multiple_calls_return_different_sessions(self):
        s1 = create_session(":memory:")
        s2 = create_session(":memory:")
        assert s1 is not s2
        s1.close()
        s2.close()
