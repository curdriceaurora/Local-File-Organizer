"""
SQLite database manager for operation history tracking.

This module provides database connection management, schema creation,
and migration support for the operation history system.
"""

import sqlite3
import logging
from pathlib import Path
from typing import Optional, Any, Tuple, List
from contextlib import contextmanager
from threading import Lock

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages SQLite database connections and schema for operation history."""

    # Database schema version
    SCHEMA_VERSION = 1

    # SQL schema definitions
    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS operations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        operation_type TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        source_path TEXT NOT NULL,
        destination_path TEXT,
        file_hash TEXT,
        metadata TEXT,
        transaction_id TEXT,
        status TEXT NOT NULL DEFAULT 'completed',
        error_message TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS transactions (
        transaction_id TEXT PRIMARY KEY,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        operation_count INTEGER DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'in_progress',
        metadata TEXT
    );

    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT DEFAULT (datetime('now'))
    );

    CREATE INDEX IF NOT EXISTS idx_operations_timestamp ON operations(timestamp);
    CREATE INDEX IF NOT EXISTS idx_operations_transaction ON operations(transaction_id);
    CREATE INDEX IF NOT EXISTS idx_operations_type ON operations(operation_type);
    CREATE INDEX IF NOT EXISTS idx_operations_status ON operations(status);
    CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file.
                    Defaults to ~/.file_organizer/history.db
        """
        if db_path is None:
            db_path = Path.home() / '.file_organizer' / 'history.db'

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection: Optional[sqlite3.Connection] = None
        self._lock = Lock()
        self._initialized = False

        logger.info(f"Database manager initialized with path: {self.db_path}")

    def initialize(self) -> None:
        """Initialize database schema and enable WAL mode."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            logger.info("Initializing database schema...")
            conn = self.get_connection()

            try:
                # Enable WAL mode for better concurrent access
                conn.execute("PRAGMA journal_mode=WAL")

                # Enable foreign keys
                conn.execute("PRAGMA foreign_keys=ON")

                # Create schema
                conn.executescript(self.SCHEMA_SQL)

                # Check and update schema version
                cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
                result = cursor.fetchone()

                if result is None:
                    # First time setup
                    conn.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
                    logger.info(f"Database schema version {self.SCHEMA_VERSION} created")
                else:
                    current_version = result[0]
                    if current_version < self.SCHEMA_VERSION:
                        self._migrate(current_version, self.SCHEMA_VERSION, conn)
                    logger.info(f"Database schema version: {current_version}")

                conn.commit()
                self._initialized = True
                logger.info("Database initialization complete")

            except Exception as e:
                conn.rollback()
                logger.error(f"Database initialization failed: {e}")
                raise

    def _migrate(self, from_version: int, to_version: int, conn: sqlite3.Connection) -> None:
        """
        Perform database migration from one version to another.

        Args:
            from_version: Current schema version
            to_version: Target schema version
            conn: Database connection
        """
        logger.info(f"Migrating database from version {from_version} to {to_version}")

        # Future migrations will be added here
        # For now, this is a placeholder for migration logic

        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (to_version,))
        logger.info(f"Migration to version {to_version} complete")

    def get_connection(self) -> sqlite3.Connection:
        """
        Get or create database connection.

        Returns:
            SQLite database connection
        """
        if self._connection is None:
            self._connection = sqlite3.connect(
                str(self.db_path),
                check_same_thread=False,
                timeout=30.0
            )
            # Enable row factory for easier data access
            self._connection.row_factory = sqlite3.Row

        return self._connection

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Yields:
            Database connection

        Example:
            with db.transaction() as conn:
                conn.execute("INSERT INTO operations ...")
        """
        with self._lock:
            conn = self.get_connection()
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction failed: {e}")
                raise

    def execute_query(self, query: str, params: Optional[Tuple] = None) -> sqlite3.Cursor:
        """
        Execute a SQL query with optional parameters.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            Query cursor
        """
        with self._lock:
            conn = self.get_connection()
            if params is None:
                return conn.execute(query)
            else:
                return conn.execute(query, params)

    def execute_many(self, query: str, params_list: List[Tuple]) -> None:
        """
        Execute a SQL query with multiple parameter sets (batch insert).

        Args:
            query: SQL query string
            params_list: List of parameter tuples
        """
        with self.transaction() as conn:
            conn.executemany(query, params_list)

    def fetch_one(self, query: str, params: Optional[Tuple] = None) -> Optional[sqlite3.Row]:
        """
        Execute query and fetch one result.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            Single row result or None
        """
        cursor = self.execute_query(query, params)
        return cursor.fetchone()

    def fetch_all(self, query: str, params: Optional[Tuple] = None) -> List[sqlite3.Row]:
        """
        Execute query and fetch all results.

        Args:
            query: SQL query string
            params: Query parameters tuple

        Returns:
            List of row results
        """
        cursor = self.execute_query(query, params)
        return cursor.fetchall()

    def get_database_size(self) -> int:
        """
        Get current database file size in bytes.

        Returns:
            Database size in bytes
        """
        if self.db_path.exists():
            return self.db_path.stat().st_size
        return 0

    def get_operation_count(self) -> int:
        """
        Get total number of operations in database.

        Returns:
            Total operation count
        """
        result = self.fetch_one("SELECT COUNT(*) as count FROM operations")
        return result['count'] if result else 0

    def vacuum(self) -> None:
        """
        Vacuum the database to reclaim space and optimize performance.
        """
        logger.info("Vacuuming database...")
        conn = self.get_connection()
        conn.execute("VACUUM")
        logger.info("Database vacuum complete")

    def close(self) -> None:
        """Close database connection."""
        if self._connection is not None:
            try:
                self._connection.close()
                self._connection = None
                logger.info("Database connection closed")
            except Exception as e:
                logger.error(f"Error closing database connection: {e}")

    def __enter__(self):
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
