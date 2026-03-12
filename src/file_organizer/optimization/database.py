"""Database optimizer for SQLite operations.

This module provides index management, table analysis, vacuuming, query plan
inspection, and pragma optimization for SQLite databases used by the file
organizer system.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Regex that every SQL identifier (table name, index name, column name,
# pragma name) must satisfy.  Only ASCII letters, digits, and underscores
# are allowed, and the name must start with a letter or underscore.
_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Per-pragma allowlists for string-typed values.  Numeric pragmas are
# validated separately by checking that the stringified value is a valid
# integer.
_SAFE_PRAGMA_VALUES: dict[str, frozenset[str]] = {
    "journal_mode": frozenset({"WAL", "DELETE", "TRUNCATE", "PERSIST", "MEMORY", "OFF"}),
    "synchronous": frozenset({"FULL", "NORMAL", "OFF", "EXTRA"}),
    "temp_store": frozenset({"DEFAULT", "FILE", "MEMORY", "0", "1", "2"}),
}

# Pragmas whose value must be a (possibly negative) integer.
_INTEGER_PRAGMAS: frozenset[str] = frozenset({"cache_size", "mmap_size"})


@dataclass(frozen=True)
class TableStats:
    """Statistics for a single database table.

    Attributes:
        name: Table name.
        row_count: Number of rows in the table.
        index_count: Number of indexes on this table.
        size_bytes: Estimated size in bytes (page_count * page_size).
    """

    name: str
    row_count: int
    index_count: int
    size_bytes: int


@dataclass(frozen=True)
class QueryPlanStep:
    """A single step in a query execution plan.

    Attributes:
        id: Step identifier from the planner.
        parent: Parent step identifier.
        detail: Human-readable description of what this step does.
    """

    id: int
    parent: int
    detail: str


@dataclass(frozen=True)
class QueryPlan:
    """Execution plan for a SQL query.

    Attributes:
        query: The original SQL query.
        steps: Ordered list of execution steps.
        estimated_cost: Heuristic cost estimate (higher means more work).
    """

    query: str
    steps: list[QueryPlanStep] = field(default_factory=list)
    estimated_cost: float = 0.0


# Index definitions for common query patterns used by the file organizer system.
# Each tuple is (index_name, table_name, column_expression, is_unique).
_DEFAULT_INDEXES: list[tuple[str, str, str, bool]] = [
    # History / operations
    ("idx_operations_timestamp", "operations", "timestamp", False),
    ("idx_operations_transaction", "operations", "transaction_id", False),
    ("idx_operations_type", "operations", "operation_type", False),
    ("idx_operations_status", "operations", "status", False),
    ("idx_operations_source", "operations", "source_path", False),
    # Transactions
    ("idx_transactions_status", "transactions", "status", False),
    ("idx_transactions_started", "transactions", "started_at", False),
    # Preferences (if table exists)
    ("idx_preferences_key", "preferences", "key", True),
    ("idx_preferences_updated", "preferences", "updated_at", False),
    # Analytics (if table exists)
    ("idx_analytics_event_type", "analytics_events", "event_type", False),
    ("idx_analytics_timestamp", "analytics_events", "timestamp", False),
]


class DatabaseOptimizer:
    """Optimizes SQLite database performance through indexing, pragma tuning, and maintenance.

    This class wraps a SQLite database and provides utilities for:
    - Creating indexes for common query patterns
    - Analysing table statistics
    - Running VACUUM to reclaim space
    - Inspecting query execution plans
    - Setting performance-oriented PRAGMAs (WAL mode, cache size, etc.)

    Args:
        db_path: Path to the SQLite database file.  Use ``":memory:"`` for an
            in-memory database (useful for testing).

    Example:
        >>> optimizer = DatabaseOptimizer(Path("app.db"))
        >>> optimizer.optimize_pragmas()
        >>> optimizer.create_indexes()
        >>> stats = optimizer.analyze_tables()
    """

    def __init__(self, db_path: Path | str) -> None:
        """Set up the database optimizer for the given SQLite database path."""
        self._db_path = str(db_path)
        self._conn: sqlite3.Connection | None = None
        logger.info("DatabaseOptimizer initialised for %s", self._db_path)

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        """Return the current connection, opening one if needed."""
        if self._conn is None:
            self._conn = sqlite3.connect(self._db_path)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def close(self) -> None:
        """Close the underlying database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            logger.debug("Database connection closed for %s", self._db_path)

    # ------------------------------------------------------------------
    # Security helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_identifier(name: str) -> None:
        """Validate that *name* is a safe SQL identifier.

        Raises:
            ValueError: If *name* contains characters outside
                ``[A-Za-z0-9_]`` or does not start with a letter/underscore.
        """
        if not _IDENTIFIER_RE.match(name):
            raise ValueError(
                f"Invalid SQL identifier {name!r}: only ASCII letters, digits, and "
                "underscores are allowed, and the name must start with a letter or "
                "underscore."
            )

    @staticmethod
    def _validate_pragma_value(pragma_name: str, pragma_value: str) -> None:
        """Validate that *pragma_value* is safe for PRAGMA *pragma_name*.

        For string-valued pragmas the value must appear in the allowlist
        ``_SAFE_PRAGMA_VALUES``.  For integer-valued pragmas the value must
        parse as an integer (negative values are allowed, e.g. for
        ``cache_size``).

        Raises:
            ValueError: If the value is not permitted.
        """
        if pragma_name in _SAFE_PRAGMA_VALUES:
            if pragma_value.upper() not in _SAFE_PRAGMA_VALUES[pragma_name]:
                raise ValueError(
                    f"Unsafe PRAGMA value {pragma_value!r} for {pragma_name!r}. "
                    f"Allowed values: {sorted(_SAFE_PRAGMA_VALUES[pragma_name])}"
                )
        elif pragma_name in _INTEGER_PRAGMAS:
            try:
                int(pragma_value)
            except ValueError:
                raise ValueError(
                    f"PRAGMA {pragma_name!r} requires an integer value, got {pragma_value!r}."
                ) from None
        else:
            # For pragmas not explicitly categorised, fall back to integer
            # validation as the safest default.
            try:
                int(pragma_value)
            except ValueError:
                raise ValueError(
                    f"PRAGMA {pragma_name!r} value {pragma_value!r} is not an "
                    "integer and has no allowlist entry; refusing to execute."
                ) from None

    # ------------------------------------------------------------------
    # Index management
    # ------------------------------------------------------------------

    def create_indexes(self, extra_indexes: list[tuple[str, str, str, bool]] | None = None) -> int:
        """Create optimal indexes for common query patterns.

        Indexes are created with ``IF NOT EXISTS`` so calling this method
        multiple times is safe.

        Args:
            extra_indexes: Additional indexes to create beyond the built-in
                defaults.  Each tuple is
                ``(index_name, table_name, column_expr, is_unique)``.
                All identifier fields are validated before use.

        Returns:
            Number of indexes successfully created.

        Raises:
            ValueError: If any identifier in *extra_indexes* fails validation.
        """
        all_indexes = list(_DEFAULT_INDEXES)
        if extra_indexes:
            # Validate all extra index identifiers eagerly before touching the DB.
            for idx_name, table, columns, _unique in extra_indexes:
                self._validate_identifier(idx_name)
                self._validate_identifier(table)
                # columns may be a comma-separated list; validate each part.
                for col in columns.split(","):
                    self._validate_identifier(col.strip())
            all_indexes.extend(extra_indexes)

        created = 0
        conn = self.connection
        for idx_name, table, columns, unique in all_indexes:
            # Validate every identifier used in the dynamic SQL.
            self._validate_identifier(idx_name)
            self._validate_identifier(table)
            for col in columns.split(","):
                self._validate_identifier(col.strip())

            # Skip indexes for tables that don't exist yet.
            if not self._table_exists(table):
                logger.debug("Skipping index %s: table %s does not exist", idx_name, table)
                continue

            unique_kw = "UNIQUE " if unique else ""
            sql = f"CREATE {unique_kw}INDEX IF NOT EXISTS {idx_name} ON {table}({columns})"
            try:
                conn.execute(sql)
                created += 1
                logger.debug("Created index %s on %s(%s)", idx_name, table, columns)
            except sqlite3.OperationalError as exc:
                logger.warning("Failed to create index %s: %s", idx_name, exc, exc_info=True)

        conn.commit()
        logger.info("Created %d indexes", created)
        return created

    # ------------------------------------------------------------------
    # Table analysis
    # ------------------------------------------------------------------

    def analyze_tables(self) -> list[TableStats]:
        """Collect statistics for every user table in the database.

        Returns:
            A list of ``TableStats`` instances, one per table, sorted by
            table name.
        """
        page_size = self._get_pragma_int("page_size")

        tables = self._list_tables()
        results: list[TableStats] = []

        for table in sorted(tables):
            row_count = self._count_rows(table)
            index_count = self._count_indexes(table)
            page_count = self._table_page_count(table)
            size_bytes = page_count * page_size

            results.append(
                TableStats(
                    name=table,
                    row_count=row_count,
                    index_count=index_count,
                    size_bytes=size_bytes,
                )
            )

        logger.info("Analysed %d tables", len(results))
        return results

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def vacuum(self) -> None:
        """Run ``VACUUM`` to rebuild the database and reclaim free space.

        Note:
            ``VACUUM`` requires exclusive access and may take a while on
            large databases.
        """
        conn = self.connection
        # VACUUM cannot run inside a transaction, so we temporarily set
        # isolation_level to None (autocommit mode).
        old_isolation = conn.isolation_level
        try:
            conn.isolation_level = None
            conn.execute("VACUUM")
            logger.info("VACUUM completed for %s", self._db_path)
        finally:
            conn.isolation_level = old_isolation

    # ------------------------------------------------------------------
    # Query plan inspection
    # ------------------------------------------------------------------

    def get_query_plan(self, query: str, params: tuple[object, ...] = ()) -> QueryPlan:
        """Retrieve the execution plan for a SQL query.

        Uses ``EXPLAIN QUERY PLAN`` to obtain the planner's strategy.

        Args:
            query: The SQL query to analyse (should be a SELECT).
            params: Optional bind parameters for the query.

        Returns:
            A ``QueryPlan`` describing the execution steps and estimated cost.
        """
        conn = self.connection
        explain_sql = f"EXPLAIN QUERY PLAN {query}"

        steps: list[QueryPlanStep] = []
        try:
            cursor = conn.execute(explain_sql, params)
            for row in cursor.fetchall():
                steps.append(
                    QueryPlanStep(
                        id=int(row[0]),
                        parent=int(row[1]),
                        detail=str(row[3]),
                    )
                )
        except sqlite3.OperationalError as exc:
            logger.error("Failed to explain query: %s", exc, exc_info=True)
            return QueryPlan(query=query, steps=[], estimated_cost=-1.0)

        # Simple heuristic: each SCAN step is expensive (100), SEARCH is
        # cheap (10), and other steps are neutral (1).
        cost = 0.0
        for step in steps:
            detail_upper = step.detail.upper()
            if "SCAN" in detail_upper:
                cost += 100.0
            elif "SEARCH" in detail_upper:
                cost += 10.0
            else:
                cost += 1.0

        plan = QueryPlan(query=query, steps=steps, estimated_cost=cost)
        logger.debug("Query plan for '%s': cost=%.1f, steps=%d", query, cost, len(steps))
        return plan

    # ------------------------------------------------------------------
    # Pragma optimisation
    # ------------------------------------------------------------------

    def optimize_pragmas(
        self,
        *,
        journal_mode: str = "WAL",
        cache_size_kb: int = 8192,
        synchronous: str = "NORMAL",
        temp_store: str = "MEMORY",
        mmap_size: int = 268435456,
    ) -> dict[str, str]:
        """Set performance-oriented SQLite PRAGMAs.

        Args:
            journal_mode: Journal mode (``WAL`` recommended for concurrency).
            cache_size_kb: Page cache size in KiB (negative value to sqlite).
            synchronous: Sync mode (``NORMAL`` is a good balance).
            temp_store: Where to store temporary tables (``MEMORY`` is fastest).
            mmap_size: Memory-mapped I/O size in bytes (0 to disable).

        Returns:
            Dictionary of pragma names to their new effective values.

        Raises:
            ValueError: If any pragma name or value fails allowlist validation.
        """
        conn = self.connection
        pragmas: dict[str, str] = {}

        pragma_settings: list[tuple[str, str]] = [
            ("journal_mode", journal_mode),
            ("cache_size", str(-cache_size_kb)),
            ("synchronous", synchronous),
            ("temp_store", temp_store),
            ("mmap_size", str(mmap_size)),
        ]

        for pragma_name, pragma_value in pragma_settings:
            # Validate the pragma name is a safe identifier.
            self._validate_identifier(pragma_name)
            # Validate the pragma value against its allowlist or integer check.
            self._validate_pragma_value(pragma_name, pragma_value)

            try:
                conn.execute(f"PRAGMA {pragma_name} = {pragma_value}")
                cursor = conn.execute(f"PRAGMA {pragma_name}")
                result = cursor.fetchone()
                effective = str(result[0]) if result else pragma_value
                pragmas[pragma_name] = effective
                logger.debug(
                    "PRAGMA %s = %s (effective: %s)",
                    pragma_name,
                    pragma_value,
                    effective,
                )
            except sqlite3.OperationalError as exc:
                logger.warning("Failed to set PRAGMA %s: %s", pragma_name, exc, exc_info=True)
                pragmas[pragma_name] = f"ERROR: {exc}"

        logger.info("Optimised %d PRAGMAs", len(pragmas))
        return pragmas

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _table_exists(self, table: str) -> bool:
        """Check whether a table exists in the database."""
        cursor = self.connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        )
        return cursor.fetchone() is not None

    def _list_tables(self) -> list[str]:
        """Return a list of all user-created tables."""
        cursor = self.connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
        return [row[0] for row in cursor.fetchall()]

    def _count_rows(self, table: str) -> int:
        """Return the number of rows in *table*."""
        self._validate_identifier(table)
        try:
            cursor = self.connection.execute(f"SELECT COUNT(*) FROM [{table}]")
            result = cursor.fetchone()
            return int(result[0]) if result else 0
        except sqlite3.OperationalError:
            return 0

    def _count_indexes(self, table: str) -> int:
        """Return the number of indexes on *table*."""
        cursor = self.connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND tbl_name=?",
            (table,),
        )
        result = cursor.fetchone()
        return int(result[0]) if result else 0

    def _table_page_count(self, table: str) -> int:
        """Estimate the number of pages used by *table* using ``dbstat``."""
        try:
            cursor = self.connection.execute(
                "SELECT SUM(pageno) FROM dbstat WHERE name=?",
                (table,),
            )
            result = cursor.fetchone()
            return int(result[0]) if result and result[0] is not None else 0
        except sqlite3.OperationalError:
            # dbstat virtual table may not be available in all builds.
            return 0

    def _get_pragma_int(self, name: str) -> int:
        """Read a PRAGMA that returns an integer."""
        self._validate_identifier(name)
        cursor = self.connection.execute(f"PRAGMA {name}")
        result = cursor.fetchone()
        return int(result[0]) if result else 0
