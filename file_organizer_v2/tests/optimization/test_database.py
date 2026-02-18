"""
Tests for DatabaseOptimizer.

All tests use in-memory SQLite databases so no files are created on disk.
"""

from __future__ import annotations

import sqlite3

import pytest

from file_organizer.optimization.database import (
    DatabaseOptimizer,
    QueryPlan,
    QueryPlanStep,
    TableStats,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_schema(conn: sqlite3.Connection) -> None:
    """Create the standard file-organizer schema in *conn*."""
    conn.executescript(
        """
        CREATE TABLE operations (
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

        CREATE TABLE transactions (
            transaction_id TEXT PRIMARY KEY,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            operation_count INTEGER DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'in_progress',
            metadata TEXT
        );

        CREATE TABLE preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT NOT NULL,
            value TEXT,
            updated_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            payload TEXT
        );
        """
    )


def _seed_operations(conn: sqlite3.Connection, count: int = 50) -> None:
    """Insert *count* dummy operation rows."""
    for i in range(count):
        conn.execute(
            "INSERT INTO operations (operation_type, timestamp, source_path, status) "
            "VALUES (?, ?, ?, ?)",
            ("move", f"2026-01-{(i % 28) + 1:02d}T00:00:00Z", f"/src/file_{i}.txt", "completed"),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def optimizer() -> DatabaseOptimizer:
    """Create an optimizer backed by an in-memory database."""
    opt = DatabaseOptimizer(":memory:")
    yield opt
    opt.close()


@pytest.fixture()
def optimizer_with_schema(optimizer: DatabaseOptimizer) -> DatabaseOptimizer:
    """Optimizer with the standard schema already created."""
    _create_schema(optimizer.connection)
    return optimizer


@pytest.fixture()
def optimizer_with_data(
    optimizer_with_schema: DatabaseOptimizer,
) -> DatabaseOptimizer:
    """Optimizer with schema and seed data."""
    _seed_operations(optimizer_with_schema.connection, count=50)
    return optimizer_with_schema


# ---------------------------------------------------------------------------
# Tests — Initialisation
# ---------------------------------------------------------------------------


class TestDatabaseOptimizerInit:
    """Tests for basic lifecycle."""

    def test_create_in_memory(self) -> None:
        """Optimizer can be created with :memory: path."""
        opt = DatabaseOptimizer(":memory:")
        assert opt.connection is not None
        opt.close()

    def test_close_sets_connection_none(self, optimizer: DatabaseOptimizer) -> None:
        """Closing the optimizer releases the connection."""
        _ = optimizer.connection  # Ensure it's open.
        optimizer.close()
        # After close, accessing .connection should create a new one.
        assert optimizer._conn is None

    def test_connection_property_opens_lazily(self) -> None:
        """Connection is not opened until first access."""
        opt = DatabaseOptimizer(":memory:")
        assert opt._conn is None
        _ = opt.connection
        assert opt._conn is not None
        opt.close()


# ---------------------------------------------------------------------------
# Tests — Index Management
# ---------------------------------------------------------------------------


class TestCreateIndexes:
    """Tests for create_indexes()."""

    def test_creates_indexes_on_existing_tables(
        self, optimizer_with_schema: DatabaseOptimizer
    ) -> None:
        """Indexes are created for tables that exist."""
        created = optimizer_with_schema.create_indexes()
        assert created > 0

    def test_skips_missing_tables(self, optimizer: DatabaseOptimizer) -> None:
        """No indexes created when tables are missing."""
        created = optimizer.create_indexes()
        assert created == 0

    def test_idempotent(self, optimizer_with_schema: DatabaseOptimizer) -> None:
        """Calling create_indexes twice produces the same result."""
        first = optimizer_with_schema.create_indexes()
        second = optimizer_with_schema.create_indexes()
        assert first == second

    def test_extra_indexes(self, optimizer_with_schema: DatabaseOptimizer) -> None:
        """Extra indexes are applied when supplied."""
        extra = [("idx_ops_hash", "operations", "file_hash", False)]
        optimizer_with_schema.create_indexes(extra_indexes=extra)
        # Should include the extra one.
        conn = optimizer_with_schema.connection
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ops_hash'"
        )
        assert cursor.fetchone() is not None

    def test_unique_index(self, optimizer_with_schema: DatabaseOptimizer) -> None:
        """Unique indexes are created correctly (preferences.key)."""
        optimizer_with_schema.create_indexes()
        conn = optimizer_with_schema.connection
        cursor = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name='idx_preferences_key'"
        )
        row = cursor.fetchone()
        assert row is not None
        assert "UNIQUE" in row[0].upper()


# ---------------------------------------------------------------------------
# Tests — Table Analysis
# ---------------------------------------------------------------------------


class TestAnalyzeTables:
    """Tests for analyze_tables()."""

    def test_empty_database_returns_empty_list(self, optimizer: DatabaseOptimizer) -> None:
        """No tables means no stats."""
        stats = optimizer.analyze_tables()
        assert stats == []

    def test_returns_all_tables(self, optimizer_with_schema: DatabaseOptimizer) -> None:
        """All user tables appear in results."""
        stats = optimizer_with_schema.analyze_tables()
        table_names = {s.name for s in stats}
        assert "operations" in table_names
        assert "transactions" in table_names
        assert "preferences" in table_names
        assert "analytics_events" in table_names

    def test_row_count_reflects_data(self, optimizer_with_data: DatabaseOptimizer) -> None:
        """Row counts are accurate after seeding data."""
        stats = optimizer_with_data.analyze_tables()
        ops = next(s for s in stats if s.name == "operations")
        assert ops.row_count == 50

    def test_index_count_after_create(self, optimizer_with_schema: DatabaseOptimizer) -> None:
        """Index count increases after create_indexes()."""
        before = optimizer_with_schema.analyze_tables()
        ops_before = next(s for s in before if s.name == "operations")

        optimizer_with_schema.create_indexes()

        after = optimizer_with_schema.analyze_tables()
        ops_after = next(s for s in after if s.name == "operations")
        assert ops_after.index_count > ops_before.index_count

    def test_stats_sorted_by_name(self, optimizer_with_schema: DatabaseOptimizer) -> None:
        """Results are sorted alphabetically by table name."""
        stats = optimizer_with_schema.analyze_tables()
        names = [s.name for s in stats]
        assert names == sorted(names)

    def test_table_stats_dataclass(self) -> None:
        """TableStats dataclass holds correct fields."""
        ts = TableStats(name="t", row_count=10, index_count=2, size_bytes=4096)
        assert ts.name == "t"
        assert ts.row_count == 10
        assert ts.index_count == 2
        assert ts.size_bytes == 4096


# ---------------------------------------------------------------------------
# Tests — VACUUM
# ---------------------------------------------------------------------------


class TestVacuum:
    """Tests for vacuum()."""

    def test_vacuum_runs_without_error(self, optimizer_with_data: DatabaseOptimizer) -> None:
        """VACUUM completes successfully on a populated database."""
        optimizer_with_data.vacuum()  # Should not raise.

    def test_vacuum_on_empty_db(self, optimizer: DatabaseOptimizer) -> None:
        """VACUUM on an empty database is a no-op but should not fail."""
        optimizer.vacuum()


# ---------------------------------------------------------------------------
# Tests — Query Plan
# ---------------------------------------------------------------------------


class TestGetQueryPlan:
    """Tests for get_query_plan()."""

    def test_simple_select(self, optimizer_with_schema: DatabaseOptimizer) -> None:
        """A simple SELECT produces a non-empty plan."""
        plan = optimizer_with_schema.get_query_plan(
            "SELECT * FROM operations WHERE status = ?", ("completed",)
        )
        assert isinstance(plan, QueryPlan)
        assert len(plan.steps) > 0

    def test_plan_cost_for_scan(self, optimizer_with_schema: DatabaseOptimizer) -> None:
        """A full table scan has cost >= 100."""
        plan = optimizer_with_schema.get_query_plan("SELECT * FROM operations")
        assert plan.estimated_cost >= 100.0

    def test_plan_cost_for_indexed_search(self, optimizer_with_schema: DatabaseOptimizer) -> None:
        """An indexed lookup costs less than a full scan."""
        optimizer_with_schema.create_indexes()
        plan = optimizer_with_schema.get_query_plan(
            "SELECT * FROM operations WHERE status = ?", ("completed",)
        )
        # Indexed search should use SEARCH (cost 10), not SCAN (cost 100).
        assert plan.estimated_cost < 100.0

    def test_invalid_query_returns_error_plan(
        self, optimizer_with_schema: DatabaseOptimizer
    ) -> None:
        """An invalid query returns a plan with cost -1."""
        plan = optimizer_with_schema.get_query_plan("SELECT * FROM nonexistent_table")
        assert plan.estimated_cost == -1.0
        assert plan.steps == []

    def test_query_plan_step_fields(self) -> None:
        """QueryPlanStep dataclass holds correct fields."""
        step = QueryPlanStep(id=0, parent=0, detail="SCAN operations")
        assert step.id == 0
        assert step.parent == 0
        assert step.detail == "SCAN operations"


# ---------------------------------------------------------------------------
# Tests — Pragma Optimisation
# ---------------------------------------------------------------------------


class TestOptimizePragmas:
    """Tests for optimize_pragmas()."""

    def test_sets_wal_mode(self, optimizer: DatabaseOptimizer) -> None:
        """WAL journal mode is activated."""
        pragmas = optimizer.optimize_pragmas()
        # In-memory databases cannot use WAL and report "memory" instead.
        assert pragmas["journal_mode"].lower() in ("wal", "memory")

    def test_sets_cache_size(self, optimizer: DatabaseOptimizer) -> None:
        """Cache size is set to the requested value (negative KiB)."""
        pragmas = optimizer.optimize_pragmas(cache_size_kb=4096)
        # SQLite stores negative pages; the returned value should be -4096.
        assert pragmas["cache_size"] == "-4096"

    def test_sets_synchronous(self, optimizer: DatabaseOptimizer) -> None:
        """Synchronous mode is set (NORMAL == 1)."""
        pragmas = optimizer.optimize_pragmas(synchronous="NORMAL")
        # SQLite returns 1 for NORMAL.
        assert pragmas["synchronous"] in ("1", "NORMAL", "normal")

    def test_custom_mmap_size(self, optimizer: DatabaseOptimizer) -> None:
        """Custom mmap_size is applied."""
        pragmas = optimizer.optimize_pragmas(mmap_size=0)
        assert pragmas["mmap_size"] == "0"

    def test_returns_all_pragmas(self, optimizer: DatabaseOptimizer) -> None:
        """All five pragmas are present in the return dict."""
        pragmas = optimizer.optimize_pragmas()
        expected_keys = {"journal_mode", "cache_size", "synchronous", "temp_store", "mmap_size"}
        assert set(pragmas.keys()) == expected_keys
