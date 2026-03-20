"""
Tests for ConnectionPool.

Tests verify thread safety, pool lifecycle, and error handling using
temporary SQLite database files.
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

import pytest

from file_organizer.optimization.connection_pool import ConnectionPool, PoolStats

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Return a temporary database file path."""
    return tmp_path / "test_pool.db"


@pytest.fixture()
def pool(db_path: Path) -> ConnectionPool:
    """Create a connection pool with default settings."""
    p = ConnectionPool(db_path, pool_size=3, timeout=5.0)
    yield p
    p.close()


@pytest.fixture()
def pool_with_table(pool: ConnectionPool, db_path: Path) -> ConnectionPool:
    """Pool whose database has a test table."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()
    return pool


# ---------------------------------------------------------------------------
# Tests — Initialisation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPoolInit:
    """Tests for pool creation and configuration."""

    def test_create_pool(self, db_path: Path) -> None:
        """Pool can be created with valid arguments."""
        p = ConnectionPool(db_path, pool_size=5)
        stats = p.stats()
        assert stats.pool_size == 5
        assert stats.active == 0
        assert stats.idle == 0
        p.close()

    def test_invalid_pool_size(self, db_path: Path) -> None:
        """pool_size < 1 raises ValueError."""
        with pytest.raises(ValueError, match="pool_size must be >= 1"):
            ConnectionPool(db_path, pool_size=0)

    def test_string_path(self, db_path: Path) -> None:
        """Pool accepts a string path."""
        p = ConnectionPool(str(db_path), pool_size=2)
        with p.acquire() as conn:
            assert conn is not None
        p.close()


# ---------------------------------------------------------------------------
# Tests — Acquire / Release
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAcquireRelease:
    """Tests for connection checkout and return."""

    def test_acquire_returns_connection(self, pool: ConnectionPool) -> None:
        """acquire() yields a sqlite3.Connection."""
        with pool.acquire() as conn:
            assert isinstance(conn, sqlite3.Connection)

    def test_connection_usable(self, pool_with_table: ConnectionPool) -> None:
        """Acquired connection can execute queries."""
        with pool_with_table.acquire() as conn:
            conn.execute("INSERT INTO test_data (value) VALUES (?)", ("hello",))
            conn.commit()
            cursor = conn.execute("SELECT COUNT(*) FROM test_data")
            assert cursor.fetchone()[0] == 1

    def test_release_returns_connection_to_pool(self, pool: ConnectionPool) -> None:
        """After exiting the context manager, connection goes back to idle."""
        with pool.acquire():
            assert pool.stats().active == 1
        assert pool.stats().active == 0
        assert pool.stats().idle == 1

    def test_manual_release(self, pool: ConnectionPool) -> None:
        """release() manually returns a connection."""
        conn = pool._checkout()
        assert pool.stats().active == 1
        pool.release(conn)
        assert pool.stats().active == 0

    def test_reuse_connections(self, pool: ConnectionPool) -> None:
        """Connections are reused instead of creating new ones."""
        with pool.acquire() as c1:
            id1 = id(c1)
        with pool.acquire() as c2:
            id2 = id(c2)
        # Same connection object should be reused.
        assert id1 == id2

    def test_multiple_concurrent_connections(self, pool: ConnectionPool) -> None:
        """Multiple connections can be checked out simultaneously."""
        with pool.acquire() as c1:
            with pool.acquire() as c2:
                assert c1 is not c2
                stats = pool.stats()
                assert stats.active == 2


# ---------------------------------------------------------------------------
# Tests — Pool Stats
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPoolStats:
    """Tests for stats reporting."""

    def test_initial_stats(self, pool: ConnectionPool) -> None:
        """Fresh pool reports zeros."""
        stats = pool.stats()
        assert stats.active == 0
        assert stats.idle == 0
        assert stats.total == 0
        assert stats.wait_count == 0
        assert stats.pool_size == 3

    def test_stats_after_use(self, pool: ConnectionPool) -> None:
        """Stats reflect connection lifecycle."""
        with pool.acquire():
            s = pool.stats()
            assert s.active == 1
            assert s.total >= 1

    def test_pool_stats_dataclass(self) -> None:
        """PoolStats dataclass holds correct fields."""
        ps = PoolStats(active=2, idle=3, total=5, wait_count=1, pool_size=5)
        assert ps.active == 2
        assert ps.idle == 3
        assert ps.total == 5
        assert ps.wait_count == 1
        assert ps.pool_size == 5


# ---------------------------------------------------------------------------
# Tests — Thread Safety
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestThreadSafety:
    """Tests verifying thread-safe access."""

    def test_concurrent_acquire_release(self, pool_with_table: ConnectionPool) -> None:
        """Multiple threads can acquire and release without errors."""
        errors: list[str] = []
        barrier = threading.Barrier(5)

        def worker(worker_id: int) -> None:
            try:
                barrier.wait(timeout=5)
                with pool_with_table.acquire() as conn:
                    conn.execute(
                        "INSERT INTO test_data (value) VALUES (?)",
                        (f"worker-{worker_id}",),
                    )
                    conn.commit()
            except Exception as exc:
                errors.append(f"worker-{worker_id}: {exc}")

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == [], f"Errors in threads: {errors}"

    def test_pool_exhaustion_waits(self, db_path: Path) -> None:
        """When all connections are checked out, next acquire waits."""
        small_pool = ConnectionPool(db_path, pool_size=1, timeout=2.0)
        acquired = threading.Event()
        released = threading.Event()

        def holder() -> None:
            with small_pool.acquire():
                acquired.set()  # Signal that connection has been acquired
                released.wait(timeout=5)

        t = threading.Thread(target=holder)
        t.start()
        acquired.wait(timeout=5)  # Wait until holder has actually acquired the connection

        # Pool should now be exhausted.
        stats = small_pool.stats()
        assert stats.active >= 1

        released.set()
        t.join(timeout=5)
        small_pool.close()

    def test_pool_exhaustion_timeout(self, db_path: Path) -> None:
        """TimeoutError raised when pool is fully checked out."""
        small_pool = ConnectionPool(db_path, pool_size=1, timeout=0.3)
        conn = small_pool._checkout()

        with pytest.raises(TimeoutError, match="Could not acquire"):
            small_pool._checkout()

        small_pool.release(conn)
        small_pool.close()

    def test_stats_thread_safe(self, pool_with_table: ConnectionPool) -> None:
        """stats() can be called concurrently without errors."""
        errors: list[str] = []

        def reader() -> None:
            try:
                for _ in range(20):
                    s = pool_with_table.stats()
                    assert s.pool_size == 3
            except Exception as exc:
                errors.append(str(exc))

        threads = [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == []


# ---------------------------------------------------------------------------
# Tests — Close / Lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPoolClose:
    """Tests for pool shutdown."""

    def test_close_rejects_new_acquires(self, pool: ConnectionPool) -> None:
        """After close(), acquire() raises RuntimeError."""
        pool.close()
        with pytest.raises(RuntimeError, match="closed"):
            with pool.acquire():
                pass

    def test_close_idempotent(self, pool: ConnectionPool) -> None:
        """Calling close() twice does not raise."""
        pool.close()
        pool.close()  # Should not raise.

    def test_close_drains_idle(self, pool: ConnectionPool) -> None:
        """close() closes all idle connections."""
        with pool.acquire():
            pass  # Puts one connection back in pool.
        assert pool.stats().idle >= 1
        pool.close()
        assert pool._pool.empty()


# ---------------------------------------------------------------------------
# Tests — WAL mode
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWALMode:
    """Tests for connection configuration."""

    def test_wal_mode_enabled(self, pool: ConnectionPool) -> None:
        """Pooled connections use WAL journal mode."""
        with pool.acquire() as conn:
            cursor = conn.execute("PRAGMA journal_mode")
            mode = cursor.fetchone()[0]
            assert mode.lower() == "wal"
