"""
SQLite database manager for preference tracking.

This module provides database connection management, schema creation,
and migration support for the intelligent preference tracking system.
"""

import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager
from threading import RLock
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class PreferenceDatabaseManager:
    """Manages SQLite database connections and schema for preference tracking."""

    # Database schema version
    SCHEMA_VERSION = 1

    # SQL schema definitions
    SCHEMA_SQL = """
    CREATE TABLE IF NOT EXISTS preferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        preference_type TEXT NOT NULL,
        key TEXT NOT NULL,
        value TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.5,
        frequency INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_used_at TEXT,
        source TEXT NOT NULL DEFAULT 'user_correction',
        context TEXT,
        UNIQUE(preference_type, key)
    );

    CREATE TABLE IF NOT EXISTS preference_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        preference_id INTEGER NOT NULL,
        operation TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        confidence REAL,
        timestamp TEXT NOT NULL,
        metadata TEXT,
        FOREIGN KEY (preference_id) REFERENCES preferences(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS corrections (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        correction_type TEXT NOT NULL,
        source_path TEXT NOT NULL,
        destination_path TEXT,
        category_old TEXT,
        category_new TEXT,
        timestamp TEXT NOT NULL,
        confidence_before REAL,
        confidence_after REAL,
        metadata TEXT
    );

    CREATE TABLE IF NOT EXISTS folder_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern TEXT NOT NULL UNIQUE,
        target_folder TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.5,
        frequency INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        metadata TEXT
    );

    CREATE TABLE IF NOT EXISTS naming_patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern TEXT NOT NULL,
        replacement TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.5,
        frequency INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        metadata TEXT
    );

    CREATE TABLE IF NOT EXISTS category_overrides (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_pattern TEXT NOT NULL UNIQUE,
        override_category TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.5,
        frequency INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        metadata TEXT
    );

    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY,
        applied_at TEXT DEFAULT (datetime('now'))
    );

    -- Indexes for performance
    CREATE INDEX IF NOT EXISTS idx_preferences_type ON preferences(preference_type);
    CREATE INDEX IF NOT EXISTS idx_preferences_key ON preferences(key);
    CREATE INDEX IF NOT EXISTS idx_preferences_confidence ON preferences(confidence);
    CREATE INDEX IF NOT EXISTS idx_preferences_updated ON preferences(updated_at);
    CREATE INDEX IF NOT EXISTS idx_preference_history_pref ON preference_history(preference_id);
    CREATE INDEX IF NOT EXISTS idx_preference_history_timestamp ON preference_history(timestamp);
    CREATE INDEX IF NOT EXISTS idx_corrections_type ON corrections(correction_type);
    CREATE INDEX IF NOT EXISTS idx_corrections_timestamp ON corrections(timestamp);
    CREATE INDEX IF NOT EXISTS idx_folder_mappings_pattern ON folder_mappings(pattern);
    CREATE INDEX IF NOT EXISTS idx_naming_patterns_pattern ON naming_patterns(pattern);
    CREATE INDEX IF NOT EXISTS idx_category_overrides_pattern ON category_overrides(category_pattern);
    """

    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file.
                    Defaults to ~/.file_organizer/preferences.db
        """
        if db_path is None:
            db_path = Path.home() / '.file_organizer' / 'preferences.db'

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._connection: Optional[sqlite3.Connection] = None
        self._lock = RLock()
        self._initialized = False

        logger.info(f"Preference database manager initialized: {self.db_path}")

    def initialize(self) -> None:
        """Initialize database schema and enable WAL mode."""
        if self._initialized:
            return

        with self._lock:
            if self._initialized:
                return

            logger.info("Initializing preference database schema...")
            conn = self.get_connection()

            try:
                # Enable WAL mode for better concurrent access
                conn.execute("PRAGMA journal_mode=WAL")

                # Enable foreign keys
                conn.execute("PRAGMA foreign_keys=ON")

                # Create schema
                conn.executescript(self.SCHEMA_SQL)

                # Check and update schema version
                cursor = conn.execute(
                    "SELECT version FROM schema_version ORDER BY version DESC LIMIT 1"
                )
                result = cursor.fetchone()

                if result is None:
                    # First time setup
                    conn.execute(
                        "INSERT INTO schema_version (version) VALUES (?)",
                        (self.SCHEMA_VERSION,)
                    )
                    logger.info(f"Database schema version {self.SCHEMA_VERSION} created")
                else:
                    current_version = result[0]
                    if current_version < self.SCHEMA_VERSION:
                        self._migrate(current_version, self.SCHEMA_VERSION, conn)
                    logger.info(f"Database schema version: {current_version}")

                conn.commit()
                self._initialized = True
                logger.info("Preference database initialization complete")

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
        # Example:
        # if from_version == 1 and to_version == 2:
        #     conn.execute("ALTER TABLE preferences ADD COLUMN new_field TEXT")

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
                isolation_level=None  # Autocommit mode
            )
            self._connection.row_factory = sqlite3.Row
            logger.debug(f"Database connection established: {self.db_path}")

        return self._connection

    @contextmanager
    def transaction(self):
        """
        Context manager for database transactions.

        Yields:
            Database connection with active transaction
        """
        conn = self.get_connection()
        with self._lock:
            try:
                conn.execute("BEGIN")
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Transaction failed: {e}")
                raise

    def close(self) -> None:
        """Close database connection."""
        with self._lock:
            if self._connection:
                self._connection.close()
                self._connection = None
                logger.debug("Database connection closed")

    def __enter__(self) -> "PreferenceDatabaseManager":
        """Context manager entry."""
        self.initialize()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.close()

    # CRUD Operations for Preferences

    def add_preference(
        self,
        preference_type: str,
        key: str,
        value: str,
        confidence: float = 0.5,
        frequency: int = 1,
        source: str = "user_correction",
        context: Optional[dict[str, Any]] = None
    ) -> int:
        """
        Add or update a preference.

        Args:
            preference_type: Type of preference (folder_mapping, naming_pattern, etc.)
            key: Preference key/identifier
            value: Preference value
            confidence: Confidence score (0.0-1.0)
            frequency: Usage frequency count
            source: Source of the preference
            context: Additional context as dictionary

        Returns:
            Preference ID
        """
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        context_json = json.dumps(context) if context else None

        with self._lock:
            try:
                cursor = conn.execute(
                    """
                    INSERT INTO preferences (
                        preference_type, key, value, confidence, frequency,
                        created_at, updated_at, source, context
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(preference_type, key) DO UPDATE SET
                        value = excluded.value,
                        confidence = excluded.confidence,
                        frequency = frequency + 1,
                        source = excluded.source,
                        context = excluded.context,
                        updated_at = excluded.updated_at,
                        last_used_at = excluded.updated_at
                    RETURNING id
                    """,
                    (preference_type, key, value, confidence, frequency, now, now, source, context_json)
                )
                row = cursor.fetchone()
                pref_id = row[0] if row else None
                if pref_id is None:
                    raise RuntimeError("Failed to retrieve preference ID after insert/update")
                return pref_id
            except Exception as e:
                logger.error(f"Failed to add preference: {e}")
                raise

    def get_preference(self, preference_type: str, key: str) -> Optional[dict[str, Any]]:
        """
        Get a preference by type and key.

        Args:
            preference_type: Type of preference
            key: Preference key

        Returns:
            Preference dictionary or None if not found
        """
        conn = self.get_connection()

        with self._lock:
            cursor = conn.execute(
                """
                SELECT * FROM preferences
                WHERE preference_type = ? AND key = ?
                """,
                (preference_type, key)
            )
            row = cursor.fetchone()

            if row:
                result = dict(row)
                if result['context']:
                    result['context'] = json.loads(result['context'])
                return result
            return None

    def get_preferences_by_type(self, preference_type: str) -> list[dict[str, Any]]:
        """
        Get all preferences of a specific type.

        Args:
            preference_type: Type of preferences to retrieve

        Returns:
            List of preference dictionaries
        """
        conn = self.get_connection()

        with self._lock:
            cursor = conn.execute(
                """
                SELECT * FROM preferences
                WHERE preference_type = ?
                ORDER BY confidence DESC, frequency DESC
                """,
                (preference_type,)
            )
            rows = cursor.fetchall()

            results = []
            for row in rows:
                result = dict(row)
                if result['context']:
                    result['context'] = json.loads(result['context'])
                results.append(result)

            return results

    def update_preference_confidence(
        self,
        preference_id: int,
        confidence: float
    ) -> None:
        """
        Update preference confidence score.

        Args:
            preference_id: Preference ID
            confidence: New confidence score (0.0-1.0)
        """
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

        with self._lock:
            conn.execute(
                """
                UPDATE preferences
                SET confidence = ?, updated_at = ?
                WHERE id = ?
                """,
                (confidence, now, preference_id)
            )

    def increment_preference_usage(self, preference_id: int) -> None:
        """
        Increment preference usage frequency.

        Args:
            preference_id: Preference ID
        """
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

        with self._lock:
            conn.execute(
                """
                UPDATE preferences
                SET frequency = frequency + 1,
                    last_used_at = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (now, now, preference_id)
            )

    def delete_preference(self, preference_id: int) -> None:
        """
        Delete a preference.

        Args:
            preference_id: Preference ID to delete
        """
        conn = self.get_connection()

        with self._lock:
            conn.execute(
                "DELETE FROM preferences WHERE id = ?",
                (preference_id,)
            )

    # Correction Tracking

    def add_correction(
        self,
        correction_type: str,
        source_path: str,
        destination_path: Optional[str] = None,
        category_old: Optional[str] = None,
        category_new: Optional[str] = None,
        confidence_before: Optional[float] = None,
        confidence_after: Optional[float] = None,
        metadata: Optional[dict[str, Any]] = None
    ) -> int:
        """
        Add a user correction to the database.

        Args:
            correction_type: Type of correction (file_move, file_rename, category_change, etc.)
            source_path: Source file path
            destination_path: Destination file path (for moves/renames)
            category_old: Old category
            category_new: New category
            confidence_before: Confidence score before correction
            confidence_after: Confidence score after correction
            metadata: Additional metadata

        Returns:
            Correction ID
        """
        conn = self.get_connection()
        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        metadata_json = json.dumps(metadata) if metadata else None

        with self._lock:
            cursor = conn.execute(
                """
                INSERT INTO corrections (
                    correction_type, source_path, destination_path,
                    category_old, category_new, timestamp,
                    confidence_before, confidence_after, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (correction_type, source_path, destination_path,
                 category_old, category_new, now,
                 confidence_before, confidence_after, metadata_json)
            )
            return cursor.lastrowid

    def get_corrections(
        self,
        correction_type: Optional[str] = None,
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get corrections from the database.

        Args:
            correction_type: Filter by correction type (optional)
            limit: Maximum number of corrections to return

        Returns:
            List of correction dictionaries
        """
        conn = self.get_connection()

        with self._lock:
            if correction_type:
                cursor = conn.execute(
                    """
                    SELECT * FROM corrections
                    WHERE correction_type = ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (correction_type, limit)
                )
            else:
                cursor = conn.execute(
                    """
                    SELECT * FROM corrections
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (limit,)
                )

            rows = cursor.fetchall()
            results = []
            for row in rows:
                result = dict(row)
                if result['metadata']:
                    result['metadata'] = json.loads(result['metadata'])
                results.append(result)

            return results

    # Statistics

    def get_preference_stats(self) -> dict[str, Any]:
        """
        Get statistics about stored preferences.

        Returns:
            Dictionary with preference statistics
        """
        conn = self.get_connection()

        with self._lock:
            cursor = conn.execute(
                """
                SELECT
                    COUNT(*) as total_count,
                    AVG(confidence) as avg_confidence,
                    SUM(frequency) as total_usage,
                    preference_type,
                    COUNT(*) as type_count
                FROM preferences
                GROUP BY preference_type
                """
            )
            rows = cursor.fetchall()

            stats = {
                "total_preferences": 0,
                "average_confidence": 0.0,
                "total_usage_count": 0,
                "by_type": {}
            }

            for row in rows:
                row_dict = dict(row)
                pref_type = row_dict['preference_type']
                stats["by_type"][pref_type] = {
                    "count": row_dict['type_count'],
                    "avg_confidence": row_dict['avg_confidence']
                }
                stats["total_preferences"] += row_dict['type_count']
                stats["total_usage_count"] += row_dict['total_usage'] or 0

            if stats["total_preferences"] > 0:
                cursor = conn.execute("SELECT AVG(confidence) FROM preferences")
                stats["average_confidence"] = cursor.fetchone()[0] or 0.0

            return stats
