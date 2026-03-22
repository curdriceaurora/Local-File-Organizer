"""Integration tests for optimization/database.py.

Covers:
- DatabaseOptimizer constructor, connection property, close
- _validate_identifier: valid, invalid (space, leading digit, special chars)
- _validate_pragma_value: allowlisted, integer, unknown pragma
- create_indexes: returns count, idempotent, skips nonexistent tables, extra indexes
- analyze_tables: empty db, with tables, stats fields
- vacuum: runs without error
- get_query_plan: valid query returns QueryPlan, invalid query returns cost -1
- optimize_pragmas: returns dict with pragma keys, invalid value raises
- _table_exists, _list_tables, _count_rows, _count_indexes
- TableStats, QueryPlanStep, QueryPlan dataclasses
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def _optimizer(db_path: str = ":memory:"):
    from file_organizer.optimization.database import DatabaseOptimizer

    return DatabaseOptimizer(db_path)


def _create_test_table(optimizer, table: str = "test_table") -> None:
    optimizer.connection.execute(
        f"CREATE TABLE IF NOT EXISTS {table} (id INTEGER PRIMARY KEY, name TEXT)"
    )
    optimizer.connection.commit()


# ---------------------------------------------------------------------------
# TableStats / QueryPlanStep / QueryPlan dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_table_stats_fields(self) -> None:
        from file_organizer.optimization.database import TableStats

        ts = TableStats(name="foo", row_count=10, index_count=2, size_bytes=4096)
        assert ts.name == "foo"
        assert ts.row_count == 10
        assert ts.index_count == 2
        assert ts.size_bytes == 4096

    def test_query_plan_step_fields(self) -> None:
        from file_organizer.optimization.database import QueryPlanStep

        step = QueryPlanStep(id=1, parent=0, detail="SCAN TABLE foo")
        assert step.id == 1
        assert step.parent == 0
        assert "SCAN" in step.detail

    def test_query_plan_fields(self) -> None:
        from file_organizer.optimization.database import QueryPlan

        plan = QueryPlan(query="SELECT 1", steps=[], estimated_cost=0.0)
        assert plan.query == "SELECT 1"
        assert plan.steps == []
        assert plan.estimated_cost == 0.0

    def test_query_plan_with_steps(self) -> None:
        from file_organizer.optimization.database import QueryPlan, QueryPlanStep

        steps = [QueryPlanStep(id=1, parent=0, detail="SCAN TABLE t")]
        plan = QueryPlan(query="SELECT * FROM t", steps=steps, estimated_cost=100.0)
        assert len(plan.steps) == 1
        assert plan.estimated_cost == 100.0


# ---------------------------------------------------------------------------
# Constructor and connection
# ---------------------------------------------------------------------------


class TestDatabaseOptimizerInit:
    def test_constructor_with_memory(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        opt = DatabaseOptimizer(":memory:")
        assert opt._db_path == ":memory:"

    def test_constructor_with_path_string(self, tmp_path: Path) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        db_file = str(tmp_path / "test.db")
        opt = DatabaseOptimizer(db_file)
        assert opt._db_path == db_file

    def test_constructor_with_path_object(self, tmp_path: Path) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        db_file = tmp_path / "test.db"
        opt = DatabaseOptimizer(db_file)
        assert opt._db_path == str(db_file)

    def test_connection_property_returns_connection(self) -> None:
        opt = _optimizer()
        conn = opt.connection
        assert isinstance(conn, sqlite3.Connection)

    def test_connection_property_is_reused(self) -> None:
        opt = _optimizer()
        c1 = opt.connection
        c2 = opt.connection
        assert c1 is c2

    def test_close_clears_connection(self) -> None:
        opt = _optimizer()
        _ = opt.connection  # open connection
        opt.close()
        assert opt._conn is None

    def test_close_when_not_connected_is_safe(self) -> None:
        opt = _optimizer()
        opt.close()  # no connection opened yet — should not raise


# ---------------------------------------------------------------------------
# _validate_identifier
# ---------------------------------------------------------------------------


class TestValidateIdentifier:
    def test_valid_identifier(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        DatabaseOptimizer._validate_identifier("valid_name")  # no exception

    def test_valid_identifier_with_digits(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        DatabaseOptimizer._validate_identifier("name123")

    def test_leading_underscore_is_valid(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        DatabaseOptimizer._validate_identifier("_private")

    def test_leading_digit_raises_value_error(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            DatabaseOptimizer._validate_identifier("1invalid")

    def test_space_in_name_raises_value_error(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        with pytest.raises(ValueError):
            DatabaseOptimizer._validate_identifier("bad name")

    def test_hyphen_in_name_raises_value_error(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        with pytest.raises(ValueError):
            DatabaseOptimizer._validate_identifier("bad-name")

    def test_semicolon_raises_value_error(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        with pytest.raises(ValueError):
            DatabaseOptimizer._validate_identifier("name;drop")


# ---------------------------------------------------------------------------
# _validate_pragma_value
# ---------------------------------------------------------------------------


class TestValidatePragmaValue:
    def test_valid_journal_mode_wal(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        DatabaseOptimizer._validate_pragma_value("journal_mode", "WAL")

    def test_valid_journal_mode_case_insensitive(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        DatabaseOptimizer._validate_pragma_value("journal_mode", "wal")

    def test_invalid_journal_mode_raises(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        with pytest.raises(ValueError):
            DatabaseOptimizer._validate_pragma_value("journal_mode", "INVALID")

    def test_integer_pragma_valid(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        DatabaseOptimizer._validate_pragma_value("cache_size", "-8192")

    def test_integer_pragma_non_integer_raises(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        with pytest.raises(ValueError):
            DatabaseOptimizer._validate_pragma_value("cache_size", "notanint")

    def test_unknown_pragma_integer_passes(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        DatabaseOptimizer._validate_pragma_value("page_size", "4096")

    def test_unknown_pragma_non_integer_raises(self) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        with pytest.raises(ValueError):
            DatabaseOptimizer._validate_pragma_value("unknown_pragma", "bad_value")


# ---------------------------------------------------------------------------
# create_indexes
# ---------------------------------------------------------------------------


class TestCreateIndexes:
    def test_no_tables_returns_zero(self) -> None:
        opt = _optimizer()
        count = opt.create_indexes()
        assert count == 0

    def test_with_matching_table_creates_indexes(self) -> None:
        opt = _optimizer()
        # Create the 'operations' table that matches the built-in default indexes
        opt.connection.execute(
            "CREATE TABLE operations (id INTEGER PRIMARY KEY, timestamp TEXT, transaction_id TEXT, "
            "operation_type TEXT, status TEXT, source_path TEXT)"
        )
        opt.connection.commit()
        count = opt.create_indexes()
        assert count >= 1

    def test_is_idempotent(self) -> None:
        opt = _optimizer()
        opt.connection.execute(
            "CREATE TABLE operations (id INTEGER PRIMARY KEY, timestamp TEXT, transaction_id TEXT, "
            "operation_type TEXT, status TEXT, source_path TEXT)"
        )
        opt.connection.commit()
        count1 = opt.create_indexes()
        count2 = opt.create_indexes()
        assert count1 == count2

    def test_extra_indexes_on_existing_table(self) -> None:
        opt = _optimizer()
        _create_test_table(opt)
        count = opt.create_indexes(extra_indexes=[("idx_test_name", "test_table", "name", False)])
        assert count >= 1

    def test_extra_index_invalid_name_raises(self) -> None:
        opt = _optimizer()
        _create_test_table(opt)
        with pytest.raises(ValueError):
            opt.create_indexes(extra_indexes=[("bad-name", "test_table", "name", False)])


# ---------------------------------------------------------------------------
# analyze_tables
# ---------------------------------------------------------------------------


class TestAnalyzeTables:
    def test_empty_db_returns_empty_list(self) -> None:
        opt = _optimizer()
        results = opt.analyze_tables()
        assert results == []

    def test_with_one_table(self) -> None:
        from file_organizer.optimization.database import TableStats

        opt = _optimizer()
        _create_test_table(opt)
        results = opt.analyze_tables()
        assert len(results) == 1
        assert isinstance(results[0], TableStats)
        assert results[0].name == "test_table"

    def test_row_count_reflects_inserts(self) -> None:
        opt = _optimizer()
        _create_test_table(opt)
        opt.connection.execute("INSERT INTO test_table (name) VALUES ('a')")
        opt.connection.execute("INSERT INTO test_table (name) VALUES ('b')")
        opt.connection.commit()
        results = opt.analyze_tables()
        assert results[0].row_count == 2

    def test_multiple_tables_sorted(self) -> None:
        opt = _optimizer()
        _create_test_table(opt, "z_table")
        _create_test_table(opt, "a_table")
        results = opt.analyze_tables()
        names = [r.name for r in results]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# vacuum
# ---------------------------------------------------------------------------


class TestVacuum:
    def test_vacuum_completes_without_error(self, tmp_path: Path) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        db_file = str(tmp_path / "vacuum_test.db")
        opt = DatabaseOptimizer(db_file)
        _create_test_table(opt)
        opt.vacuum()
        opt.close()


# ---------------------------------------------------------------------------
# get_query_plan
# ---------------------------------------------------------------------------


class TestGetQueryPlan:
    def test_valid_query_returns_plan(self) -> None:
        from file_organizer.optimization.database import QueryPlan

        opt = _optimizer()
        _create_test_table(opt)
        plan = opt.get_query_plan("SELECT * FROM test_table")
        assert isinstance(plan, QueryPlan)
        assert plan.query == "SELECT * FROM test_table"
        assert plan.estimated_cost >= 0.0

    def test_invalid_query_returns_negative_cost(self) -> None:
        opt = _optimizer()
        plan = opt.get_query_plan("SELECT * FROM nonexistent_table_xyz")
        assert plan.estimated_cost == -1.0
        assert plan.steps == []

    def test_plan_steps_type(self) -> None:
        from file_organizer.optimization.database import QueryPlanStep

        opt = _optimizer()
        _create_test_table(opt)
        plan = opt.get_query_plan("SELECT * FROM test_table WHERE id=1")
        assert all(isinstance(s, QueryPlanStep) for s in plan.steps)

    def test_query_with_params(self) -> None:
        opt = _optimizer()
        _create_test_table(opt)
        plan = opt.get_query_plan("SELECT * FROM test_table WHERE id=?", (1,))
        assert plan.query.startswith("SELECT")


# ---------------------------------------------------------------------------
# optimize_pragmas
# ---------------------------------------------------------------------------


class TestOptimizePragmas:
    def test_returns_dict_with_pragma_keys(self, tmp_path: Path) -> None:
        from file_organizer.optimization.database import DatabaseOptimizer

        db_file = str(tmp_path / "pragma_test.db")
        opt = DatabaseOptimizer(db_file)
        result = opt.optimize_pragmas()
        assert "journal_mode" in result
        assert "cache_size" in result
        assert "synchronous" in result
        opt.close()

    def test_invalid_journal_mode_raises_value_error(self) -> None:
        opt = _optimizer()
        with pytest.raises(ValueError):
            opt.optimize_pragmas(journal_mode="INVALID_MODE")

    def test_invalid_synchronous_raises_value_error(self) -> None:
        opt = _optimizer()
        with pytest.raises(ValueError):
            opt.optimize_pragmas(synchronous="WRONG")
