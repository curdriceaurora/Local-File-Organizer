"""
Tests for SQL injection allowlisting in DatabaseOptimizer.

Covers:
- Identifier validation (_validate_identifier)
- Pragma value validation (_validate_pragma_value)
- create_indexes with safe and malicious extra_indexes
- optimize_pragmas with valid and invalid pragma values
- _count_rows and _get_pragma_int with unsafe identifiers

Issue #341: SQL Injection Vector in DatabaseOptimization (DB-1)
"""

from __future__ import annotations

import pytest

from file_organizer.optimization.database import DatabaseOptimizer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_optimizer() -> DatabaseOptimizer:
    """Return a DatabaseOptimizer backed by an in-memory SQLite database."""
    return DatabaseOptimizer(":memory:")


def _optimizer_with_table(table_name: str = "items") -> DatabaseOptimizer:
    """Return an optimizer with a simple table already created."""
    opt = _make_optimizer()
    opt.connection.execute(f"CREATE TABLE {table_name} (id INTEGER PRIMARY KEY, name TEXT)")
    opt.connection.commit()
    return opt


# ---------------------------------------------------------------------------
# TestIdentifierValidation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIdentifierValidation:
    """_validate_identifier must accept safe names and reject dangerous ones."""

    @pytest.mark.parametrize(
        "name",
        [
            "table_name",
            "idx_operations_timestamp",
            "Column1",
            "_private",
            "A",
            "abc123",
            "my_long_table_name_with_numbers_123",
        ],
    )
    def test_valid_identifiers_pass(self, name: str) -> None:
        """Well-formed identifiers should not raise."""
        DatabaseOptimizer._validate_identifier(name)  # must not raise

    @pytest.mark.parametrize(
        "name",
        [
            # Classic SQL injection attempts
            "users; DROP TABLE users--",
            "'; DROP TABLE operations;--",
            "name OR 1=1",
            "table UNION SELECT * FROM sqlite_master",
            # Whitespace / special characters
            "my table",
            "col-name",
            "col.name",
            "col*",
            # Empty or numeric start
            "",
            "123abc",
            "1",
            # Null byte
            "col\x00name",
            # Semicolons
            "col;name",
            # Parentheses
            "col(name)",
            # Quotes
            "col'name",
            '"col"',
        ],
    )
    def test_invalid_identifiers_raise_value_error(self, name: str) -> None:
        """Dangerous or malformed identifiers must raise ValueError."""
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            DatabaseOptimizer._validate_identifier(name)


# ---------------------------------------------------------------------------
# TestPragmaValueValidation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPragmaValueValidation:
    """_validate_pragma_value must accept known-safe values and reject injections."""

    @pytest.mark.parametrize(
        "pragma_name,pragma_value",
        [
            ("journal_mode", "WAL"),
            ("journal_mode", "DELETE"),
            ("journal_mode", "TRUNCATE"),
            ("journal_mode", "PERSIST"),
            ("journal_mode", "MEMORY"),
            ("journal_mode", "OFF"),
            ("synchronous", "FULL"),
            ("synchronous", "NORMAL"),
            ("synchronous", "OFF"),
            ("synchronous", "EXTRA"),
            ("temp_store", "DEFAULT"),
            ("temp_store", "FILE"),
            ("temp_store", "MEMORY"),
            ("cache_size", "-8192"),
            ("cache_size", "0"),
            ("cache_size", "4096"),
            ("mmap_size", "268435456"),
            ("mmap_size", "0"),
        ],
    )
    def test_valid_pragma_values_pass(self, pragma_name: str, pragma_value: str) -> None:
        """Allowlisted pragma values should not raise."""
        DatabaseOptimizer._validate_pragma_value(pragma_name, pragma_value)

    @pytest.mark.parametrize(
        "pragma_name,pragma_value",
        [
            # SQL injection via journal_mode
            ("journal_mode", "WAL; DROP TABLE operations--"),
            ("journal_mode", "DELETE; INSERT INTO sqlite_master"),
            # Unknown string for journal_mode
            ("journal_mode", "ROLLBACK"),
            # SQL injection via synchronous
            ("synchronous", "NORMAL; DROP TABLE users--"),
            ("synchronous", "1 OR 1=1"),
            # Integer pragma with non-integer value
            ("cache_size", "WAL"),
            ("cache_size", "100; DROP TABLE x"),
            ("mmap_size", "big"),
            # Unknown pragma with non-integer value
            ("page_size", "abc"),
            ("page_size", "4096; DROP TABLE users"),
        ],
    )
    def test_invalid_pragma_values_raise_value_error(
        self, pragma_name: str, pragma_value: str
    ) -> None:
        """Unsafe pragma values must raise ValueError."""
        with pytest.raises(ValueError):
            DatabaseOptimizer._validate_pragma_value(pragma_name, pragma_value)


# ---------------------------------------------------------------------------
# TestCreateIndexesSafe
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCreateIndexesSafe:
    """create_indexes must work for valid indexes and block malicious ones."""

    def test_create_indexes_on_existing_table(self) -> None:
        """Indexes on existing tables should be created without error."""
        opt = _optimizer_with_table("operations")
        opt.connection.execute("ALTER TABLE operations ADD COLUMN timestamp TEXT")
        opt.connection.commit()

        count = opt.create_indexes(extra_indexes=[("idx_ops_ts", "operations", "timestamp", False)])
        assert count >= 1
        opt.close()

    def test_extra_index_valid_names_accepted(self) -> None:
        """A well-named extra index on an existing table should be created."""
        opt = _optimizer_with_table("logs")
        opt.connection.execute("ALTER TABLE logs ADD COLUMN created_at TEXT")
        opt.connection.commit()

        count = opt.create_indexes(
            extra_indexes=[("idx_logs_created", "logs", "created_at", False)]
        )
        assert count >= 1
        opt.close()

    @pytest.mark.parametrize(
        "bad_idx",
        [
            # Malicious index name
            ("idx; DROP TABLE sqlite_master--", "logs", "id", False),
            # Malicious table name
            ("idx_logs_ts", "logs; DROP TABLE users--", "id", False),
            # Malicious column name
            ("idx_logs_col", "logs", "id; DROP TABLE users--", False),
            # Index name starting with digit
            ("1badindex", "logs", "id", False),
            # Spaces in table name
            ("idx_ok", "my table", "id", False),
        ],
    )
    def test_malicious_extra_index_raises_value_error(
        self, bad_idx: tuple[str, str, str, bool]
    ) -> None:
        """Malicious identifiers in extra_indexes must raise ValueError."""
        opt = _optimizer_with_table("logs")
        with pytest.raises(ValueError):
            opt.create_indexes(extra_indexes=[bad_idx])
        opt.close()

    def test_create_indexes_skips_nonexistent_tables(self) -> None:
        """Indexes for tables that do not exist should be silently skipped."""
        opt = _make_optimizer()
        # No tables exist; default indexes should be skipped, not error.
        count = opt.create_indexes()
        assert count == 0
        opt.close()


# ---------------------------------------------------------------------------
# TestOptimizePragmasSafe
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestOptimizePragmasSafe:
    """optimize_pragmas must accept valid settings and reject injections."""

    def test_default_pragmas_apply_without_error(self) -> None:
        """Default pragma values should apply successfully."""
        opt = _make_optimizer()
        result = opt.optimize_pragmas()
        assert "journal_mode" in result
        assert "synchronous" in result
        opt.close()

    def test_wal_journal_mode_accepted(self) -> None:
        """WAL journal mode is an explicitly allowed value."""
        opt = _make_optimizer()
        result = opt.optimize_pragmas(journal_mode="WAL")
        assert "journal_mode" in result
        opt.close()

    def test_delete_journal_mode_accepted(self) -> None:
        """DELETE journal mode is an explicitly allowed value."""
        opt = _make_optimizer()
        result = opt.optimize_pragmas(journal_mode="DELETE")
        assert result.get("journal_mode") is not None
        opt.close()

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"journal_mode": "WAL; DROP TABLE users--"},
            {"journal_mode": "ROLLBACK"},
            {"synchronous": "NORMAL; DELETE FROM operations"},
            {"synchronous": "1=1"},
            {"temp_store": "INVALID"},
        ],
    )
    def test_invalid_pragma_values_raise_before_execution(self, kwargs: dict) -> None:
        """optimize_pragmas must raise ValueError before touching the DB."""
        opt = _make_optimizer()
        with pytest.raises(ValueError):
            opt.optimize_pragmas(**kwargs)
        opt.close()


# ---------------------------------------------------------------------------
# TestCountRowsSafe
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCountRowsSafe:
    """_count_rows must validate the table name before building SQL."""

    def test_count_rows_on_valid_table(self) -> None:
        """Row count on a real table returns a non-negative integer."""
        opt = _optimizer_with_table("items")
        opt.connection.execute("INSERT INTO items (name) VALUES ('a'), ('b')")
        opt.connection.commit()

        count = opt._count_rows("items")
        assert count == 2
        opt.close()

    @pytest.mark.parametrize(
        "bad_table",
        [
            "items; DROP TABLE items--",
            "'; SELECT * FROM sqlite_master--",
            "items UNION SELECT 1",
        ],
    )
    def test_count_rows_with_injection_raises_value_error(self, bad_table: str) -> None:
        """_count_rows must reject unsafe table names."""
        opt = _make_optimizer()
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            opt._count_rows(bad_table)
        opt.close()


# ---------------------------------------------------------------------------
# TestGetPragmaIntSafe
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestGetPragmaIntSafe:
    """_get_pragma_int must validate the pragma name before building SQL."""

    def test_get_pragma_int_page_size(self) -> None:
        """page_size is a valid integer pragma and should return a positive int."""
        opt = _make_optimizer()
        page_size = opt._get_pragma_int("page_size")
        assert page_size > 0
        opt.close()

    @pytest.mark.parametrize(
        "bad_name",
        [
            "page_size; DROP TABLE users--",
            "'; SELECT * FROM sqlite_master",
            "page size",
            "page-size",
        ],
    )
    def test_get_pragma_int_with_injection_raises_value_error(self, bad_name: str) -> None:
        """_get_pragma_int must reject unsafe pragma names."""
        opt = _make_optimizer()
        with pytest.raises(ValueError, match="Invalid SQL identifier"):
            opt._get_pragma_int(bad_name)
        opt.close()
