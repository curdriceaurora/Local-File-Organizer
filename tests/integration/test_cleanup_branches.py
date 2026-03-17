"""Integration tests for history/cleanup.py branch coverage.

Targets uncovered branches in:
  - should_cleanup: size-based cleanup trigger (lines 82-87)
  - cleanup_by_count: fetch_one returns None early return (lines 168-170)
  - cleanup_by_size: entire method body (lines 195-249)
  - auto_cleanup: not needed early return (lines 325-327),
                  cleanup_by_size call branch (lines 344-346)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_db(tmp_path: Path):
    from file_organizer.history.database import DatabaseManager

    db = DatabaseManager(tmp_path / "history.db")
    db.initialize()
    return db


def _make_cleanup(tmp_path: Path, config=None):
    from file_organizer.history.cleanup import HistoryCleanup

    db = _make_db(tmp_path)
    cleanup = HistoryCleanup(db, config)
    return db, cleanup


def _insert_operations(db, count: int) -> None:
    """Insert `count` completed operations into the DB."""
    query = (
        "INSERT INTO operations "
        "(operation_type, source_path, timestamp, status) "
        "VALUES (?, ?, ?, ?)"
    )
    params = [
        ("move", f"/src/file{i}.txt", f"2026-01-{i + 1:02d}T00:00:00Z", "completed")
        for i in range(count)
    ]
    db.execute_many(query, params)


# ---------------------------------------------------------------------------
# should_cleanup — size branch
# ---------------------------------------------------------------------------


class TestShouldCleanupSizeBranch:
    def test_should_cleanup_false_when_disabled(self, tmp_path: Path) -> None:
        """auto_cleanup_enabled=False always returns False."""
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(
            tmp_path, config=HistoryCleanupConfig(auto_cleanup_enabled=False)
        )
        assert cleanup.should_cleanup() is False

    def test_should_cleanup_true_when_count_exceeded(self, tmp_path: Path) -> None:
        """Returns True when operation count >= max_operations."""
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(tmp_path, config=HistoryCleanupConfig(max_operations=2))
        _insert_operations(db, 3)
        assert cleanup.should_cleanup() is True

    def test_should_cleanup_true_when_size_exceeded(self, tmp_path: Path) -> None:
        """Returns True when db size exceeds max_size_mb (lines 82-87).

        Mock get_database_size to return > max_size_mb bytes.
        """
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(
            tmp_path,
            config=HistoryCleanupConfig(max_operations=10000, max_size_mb=1),
        )
        # Return 2MB in bytes — exceeds 1MB limit
        with patch.object(db, "get_database_size", return_value=2 * 1024 * 1024):
            result = cleanup.should_cleanup()
        assert result is True

    def test_should_cleanup_false_when_within_limits(self, tmp_path: Path) -> None:
        """Returns False when both count and size are within limits."""
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(
            tmp_path,
            config=HistoryCleanupConfig(max_operations=10000, max_size_mb=500),
        )
        assert cleanup.should_cleanup() is False


# ---------------------------------------------------------------------------
# cleanup_by_count — result is None early return
# ---------------------------------------------------------------------------


class TestCleanupByCountBranches:
    def test_cleanup_by_count_no_cleanup_needed(self, tmp_path: Path) -> None:
        """current_count <= max_operations → returns 0 without deleting."""
        db, cleanup = _make_cleanup(tmp_path)
        _insert_operations(db, 3)
        deleted = cleanup.cleanup_by_count(max_operations=10)
        assert deleted == 0
        assert db.get_operation_count() == 3

    def test_cleanup_by_count_deletes_oldest(self, tmp_path: Path) -> None:
        """Keeps exactly N most-recent operations, deletes older ones.

        With 5 distinct-timestamp ops and max=3: the cutoff is the 3rd-newest
        timestamp (OFFSET=2); DELETE WHERE timestamp < cutoff removes the 2 oldest,
        leaving exactly 3 rows.
        """
        db, cleanup = _make_cleanup(tmp_path)
        _insert_operations(db, 5)
        deleted = cleanup.cleanup_by_count(max_operations=3)
        assert deleted == 2
        assert db.get_operation_count() == 3

    def test_cleanup_by_count_max_zero_deletes_all(self, tmp_path: Path) -> None:
        """max_operations=0 → special case: delete all operations."""
        db, cleanup = _make_cleanup(tmp_path)
        _insert_operations(db, 4)
        deleted = cleanup.cleanup_by_count(max_operations=0)
        assert deleted == 4
        assert db.get_operation_count() == 0

    def test_cleanup_by_count_negative_raises(self, tmp_path: Path) -> None:
        """Negative max_operations raises ValueError."""
        _, cleanup = _make_cleanup(tmp_path)
        with pytest.raises(ValueError, match="non-negative"):
            cleanup.cleanup_by_count(max_operations=-1)

    def test_cleanup_by_count_fetch_one_none_returns_zero(self, tmp_path: Path) -> None:
        """fetch_one returns None → early return 0 (lines 168-170).

        Simulates race-condition / unexpected empty result from the
        timestamp-cutoff query.
        """
        db, cleanup = _make_cleanup(tmp_path)
        _insert_operations(db, 5)

        with patch.object(db, "fetch_one", return_value=None):
            deleted = cleanup.cleanup_by_count(max_operations=3)
        assert deleted == 0

    def test_cleanup_by_count_uses_config_default(self, tmp_path: Path) -> None:
        """max_operations=None falls through to config.max_operations."""
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(tmp_path, config=HistoryCleanupConfig(max_operations=2))
        _insert_operations(db, 5)
        deleted = cleanup.cleanup_by_count()  # uses config default of 2
        # With 5 ops and max=2 (OFFSET=1 → cutoff=2nd-newest timestamp), 3 are deleted
        assert deleted == 3
        assert db.get_operation_count() == 2


# ---------------------------------------------------------------------------
# cleanup_by_size — entire method body
# ---------------------------------------------------------------------------


class TestCleanupBySizeBranches:
    def test_cleanup_by_size_within_limit_returns_zero(self, tmp_path: Path) -> None:
        """DB size <= max_size_mb → returns 0 (line 200-204)."""
        db, cleanup = _make_cleanup(tmp_path)
        deleted = cleanup.cleanup_by_size(max_size_mb=1000)
        assert deleted == 0

    def test_cleanup_by_size_uses_config_default(self, tmp_path: Path) -> None:
        """max_size_mb=None uses config.max_size_mb."""
        db, cleanup = _make_cleanup(tmp_path)
        # Config default is 100MB; fresh DB is well under that
        deleted = cleanup.cleanup_by_size()
        assert deleted == 0

    def test_cleanup_by_size_deletes_operations_to_reduce_size(self, tmp_path: Path) -> None:
        """DB size exceeds limit → operations deleted until size acceptable or no more rows.

        Since an empty SQLite DB is always > 0MB, set max_size_mb=0 to force
        the cleanup loop. The loop exits via `if not rows: break` once all
        operations are deleted.
        """
        db, cleanup = _make_cleanup(tmp_path)
        _insert_operations(db, 10)

        deleted = cleanup.cleanup_by_size(max_size_mb=0)
        # All 10 operations should have been deleted (loop runs until no rows)
        assert deleted >= 10
        assert db.get_operation_count() == 0

    def test_cleanup_by_size_empty_db_breaks_immediately(self, tmp_path: Path) -> None:
        """Empty DB with size > limit → loop runs once, no rows found → breaks.

        Uses max_size_mb=0 to enter the loop, then `if not rows: break` exits.
        """
        db, cleanup = _make_cleanup(tmp_path)
        # No operations — loop enters but immediately breaks (no rows)
        deleted = cleanup.cleanup_by_size(max_size_mb=0)
        assert deleted == 0


# ---------------------------------------------------------------------------
# auto_cleanup — branches
# ---------------------------------------------------------------------------


class TestAutoCleanupBranches:
    def test_auto_cleanup_not_needed_returns_zeros(self, tmp_path: Path) -> None:
        """should_cleanup() returns False → early return with zero stats (lines 325-327)."""
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(
            tmp_path,
            config=HistoryCleanupConfig(
                max_operations=10000, max_size_mb=500, auto_cleanup_enabled=True
            ),
        )
        # Nothing inserted; count=0 and size is tiny — well within limits
        stats = cleanup.auto_cleanup()
        assert stats["deleted_operations"] == 0
        assert stats["deleted_transactions"] == 0

    def test_auto_cleanup_by_age_when_count_exceeded(self, tmp_path: Path) -> None:
        """auto_cleanup runs age cleanup first; all 5 ops (in the past) are purged."""
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(
            tmp_path,
            config=HistoryCleanupConfig(max_operations=2, max_age_days=0),
        )
        _insert_operations(db, 5)
        stats = cleanup.auto_cleanup()
        # max_age_days=0 deletes everything older than today; all 5 past-dated ops removed
        assert stats["deleted_operations"] == 5
        assert db.get_operation_count() == 0

    def test_auto_cleanup_triggers_cleanup_by_size(self, tmp_path: Path) -> None:
        """cleanup_by_size branch called when DB size still over limit (lines 344-346).

        Mock get_database_size to return a large value so the size branch fires.
        """
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(
            tmp_path,
            config=HistoryCleanupConfig(max_operations=10000, max_size_mb=0),
        )
        _insert_operations(db, 5)

        # should_cleanup() checks size; make it return True
        # Then auto_cleanup runs age+count (no deletions since count<10000+age>90d)
        # Then size check still fires since max_size_mb=0
        stats = cleanup.auto_cleanup()
        # size branch fires (max_size_mb=0); all 5 ops deleted to attempt size reduction
        assert stats["deleted_operations"] == 5
        assert db.get_operation_count() == 0

    def test_auto_cleanup_disabled_returns_zeros(self, tmp_path: Path) -> None:
        """auto_cleanup_enabled=False → auto_cleanup returns early via should_cleanup."""
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(
            tmp_path,
            config=HistoryCleanupConfig(auto_cleanup_enabled=False),
        )
        _insert_operations(db, 100)
        stats = cleanup.auto_cleanup()
        assert stats["deleted_operations"] == 0


# ---------------------------------------------------------------------------
# cleanup_old_operations, cleanup_failed_operations, clear_all, get_statistics
# ---------------------------------------------------------------------------


class TestCleanupMiscBranches:
    def test_cleanup_old_operations_uses_config_default(self, tmp_path: Path) -> None:
        """max_age_days=None uses config.max_age_days."""
        from file_organizer.history.cleanup import HistoryCleanupConfig

        db, cleanup = _make_cleanup(tmp_path, config=HistoryCleanupConfig(max_age_days=9999))
        _insert_operations(db, 3)
        deleted = cleanup.cleanup_old_operations()  # 9999 days — nothing deleted
        assert deleted == 0

    def test_cleanup_failed_operations_deletes_old_failures(self, tmp_path: Path) -> None:
        """Deletes failed operations older than older_than_days."""
        db, cleanup = _make_cleanup(tmp_path)
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO operations (operation_type, source_path, timestamp, status) "
                "VALUES ('move', '/fail.txt', '2020-01-01T00:00:00Z', 'failed')"
            )
        deleted = cleanup.cleanup_failed_operations(older_than_days=1)
        assert deleted >= 1

    def test_clear_all_without_confirm_returns_false(self, tmp_path: Path) -> None:
        """clear_all(confirm=False) → returns False, nothing deleted."""
        db, cleanup = _make_cleanup(tmp_path)
        _insert_operations(db, 3)
        result = cleanup.clear_all(confirm=False)
        assert result is False
        assert db.get_operation_count() == 3

    def test_clear_all_with_confirm_deletes_everything(self, tmp_path: Path) -> None:
        """clear_all(confirm=True) → deletes all operations, returns True."""
        db, cleanup = _make_cleanup(tmp_path)
        _insert_operations(db, 5)
        result = cleanup.clear_all(confirm=True)
        assert result is True
        assert db.get_operation_count() == 0

    def test_get_statistics_empty_db(self, tmp_path: Path) -> None:
        """get_statistics on empty DB returns zeros."""
        _, cleanup = _make_cleanup(tmp_path)
        stats = cleanup.get_statistics()
        assert stats["total_operations"] == 0

    def test_get_statistics_with_operations(self, tmp_path: Path) -> None:
        """get_statistics reflects inserted operations."""
        db, cleanup = _make_cleanup(tmp_path)
        _insert_operations(db, 3)
        stats = cleanup.get_statistics()
        assert stats["total_operations"] == 3
        assert stats["database_size_mb"] > 0
