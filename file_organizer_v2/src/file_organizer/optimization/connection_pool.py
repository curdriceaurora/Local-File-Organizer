"""
Thread-safe connection pool for SQLite.

This module provides a connection pool that manages a fixed number of SQLite
connections, handing them out to callers and returning them when done.  It is
designed for concurrent access from multiple threads while respecting SQLite's
threading constraints.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Queue

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PoolStats:
    """Snapshot of connection pool state.

    Attributes:
        active: Number of connections currently checked out.
        idle: Number of connections sitting in the pool.
        total: Total connections managed (active + idle).
        wait_count: Cumulative number of times a caller had to wait
            because all connections were in use.
        pool_size: Maximum pool capacity.
    """

    active: int
    idle: int
    total: int
    wait_count: int
    pool_size: int


class ConnectionPool:
    """Thread-safe SQLite connection pool.

    Manages a bounded set of SQLite connections so that multiple threads can
    perform database operations without contention on a single connection.

    Each connection is opened with ``check_same_thread=False`` to allow
    cross-thread usage, and WAL journal mode is enabled for better
    concurrency.

    Args:
        db_path: Path to the SQLite database file.  Use ``":memory:"`` for
            testing (note: each pooled connection to ``:memory:`` creates a
            separate database; use a file-backed database or URI filename
            for shared state).
        pool_size: Maximum number of connections in the pool.
        timeout: Maximum seconds to wait for a connection before raising
            ``TimeoutError``.

    Example:
        >>> pool = ConnectionPool(Path("app.db"), pool_size=5)
        >>> with pool.acquire() as conn:
        ...     cursor = conn.execute("SELECT 1")
        ...     print(cursor.fetchone())
        >>> pool.close()
    """

    def __init__(
        self,
        db_path: Path | str,
        pool_size: int = 5,
        timeout: float = 30.0,
    ) -> None:
        if pool_size < 1:
            raise ValueError("pool_size must be >= 1")

        self._db_path = str(db_path)
        self._pool_size = pool_size
        self._timeout = timeout

        self._pool: Queue[sqlite3.Connection] = Queue(maxsize=pool_size)
        self._lock = threading.Lock()
        self._active_count = 0
        self._wait_count = 0
        self._total_created = 0
        self._closed = False

        logger.info(
            "ConnectionPool initialised: db=%s, pool_size=%d, timeout=%.1fs",
            self._db_path,
            pool_size,
            timeout,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @contextmanager
    def acquire(self) -> Generator[sqlite3.Connection, None, None]:
        """Acquire a connection from the pool as a context manager.

        The connection is automatically returned to the pool when the
        ``with`` block exits (even if an exception is raised).

        Yields:
            A ``sqlite3.Connection`` instance.

        Raises:
            TimeoutError: If no connection becomes available within the
                configured timeout.
            RuntimeError: If the pool has been closed.
        """
        conn = self._checkout()
        try:
            yield conn
        finally:
            self._checkin(conn)

    def release(self, conn: sqlite3.Connection) -> None:
        """Manually return a connection to the pool.

        Prefer using :meth:`acquire` as a context manager instead.

        Args:
            conn: The connection to return.
        """
        self._checkin(conn)

    def stats(self) -> PoolStats:
        """Return a snapshot of pool statistics.

        Returns:
            A ``PoolStats`` instance reflecting current pool state.
        """
        with self._lock:
            idle = self._pool.qsize()
            active = self._active_count
            return PoolStats(
                active=active,
                idle=idle,
                total=active + idle,
                wait_count=self._wait_count,
                pool_size=self._pool_size,
            )

    def close(self) -> None:
        """Close all connections and shut down the pool.

        After calling this method, :meth:`acquire` will raise
        ``RuntimeError``.
        """
        with self._lock:
            self._closed = True

        # Drain all idle connections.
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.close()
            except Empty:
                break

        logger.info("ConnectionPool closed: db=%s", self._db_path)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _checkout(self) -> sqlite3.Connection:
        """Get a connection from the pool, creating one if needed."""
        if self._closed:
            raise RuntimeError("ConnectionPool is closed")

        # Fast path: try to grab an idle connection.
        try:
            conn = self._pool.get_nowait()
            with self._lock:
                self._active_count += 1
            return conn
        except Empty:
            pass

        # Can we create a new connection?
        with self._lock:
            if self._total_created < self._pool_size:
                conn = self._create_connection()
                self._total_created += 1
                self._active_count += 1
                return conn

        # Pool exhausted: wait for a connection to be returned.
        with self._lock:
            self._wait_count += 1

        try:
            conn = self._pool.get(timeout=self._timeout)
        except Empty:
            raise TimeoutError(
                f"Could not acquire connection within {self._timeout}s "
                f"(pool_size={self._pool_size})"
            ) from None

        with self._lock:
            self._active_count += 1
        return conn

    def _checkin(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool."""
        with self._lock:
            self._active_count = max(0, self._active_count - 1)

        if self._closed:
            conn.close()
            return

        try:
            self._pool.put_nowait(conn)
        except Exception:
            # Pool is full (shouldn't happen), just close it.
            conn.close()

    def _create_connection(self) -> sqlite3.Connection:
        """Open a new SQLite connection with sensible defaults."""
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row

        # Enable WAL for better concurrent read performance.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

        logger.debug(
            "Created new connection #%d for %s",
            self._total_created + 1,
            self._db_path,
        )
        return conn
