"""Tests for Johnny Decimal migrator uncovered branches.

Targets: execute_migration real move + rollback, backup failure,
skipped paths, generate_report branches.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.methodologies.johnny_decimal.categories import (
    JohnnyDecimalNumber,
)
from file_organizer.methodologies.johnny_decimal.migrator import (
    JohnnyDecimalMigrator,
    MigrationResult,
    RollbackInfo,
)
from file_organizer.methodologies.johnny_decimal.transformer import (
    TransformationPlan,
    TransformationRule,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def migrator() -> JohnnyDecimalMigrator:
    return JohnnyDecimalMigrator()


class TestExecuteMigration:
    """Cover execute_migration branches — lines 163-165, 207-210."""

    def test_execute_backup_failure_returns_failed(
        self, migrator: JohnnyDecimalMigrator, tmp_path: Path
    ) -> None:
        """Backup creation failure returns failed result (lines 163-165)."""
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
        )
        with patch.object(migrator, "_create_backup", side_effect=OSError("backup failed")):
            result = migrator.execute_migration(plan, dry_run=False, create_backup=True)
        assert result.success is False

    def test_execute_real_rename(self, migrator: JohnnyDecimalMigrator, tmp_path: Path) -> None:
        """Real rename execution (lines 190-210)."""
        folder = tmp_path / "Finance"
        folder.mkdir()
        jd_num = JohnnyDecimalNumber(area=10)
        rule = TransformationRule(
            source_path=folder,
            target_name="10 Finance",
            jd_number=jd_num,
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)

        with patch.object(migrator, "_save_rollback_info"):
            result = migrator.execute_migration(plan, dry_run=False, create_backup=False)
        assert result.success is True
        assert result.transformed_count == 1
        assert (tmp_path / "10 Finance").exists()

    def test_execute_skip_existing_target(
        self, migrator: JohnnyDecimalMigrator, tmp_path: Path
    ) -> None:
        """Target exists and differs from source => skip (lines 190-193)."""
        folder = tmp_path / "Finance"
        folder.mkdir()
        existing = tmp_path / "10 Finance"
        existing.mkdir()

        jd_num = JohnnyDecimalNumber(area=10)
        rule = TransformationRule(
            source_path=folder,
            target_name="10 Finance",
            jd_number=jd_num,
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)

        with patch.object(migrator, "_save_rollback_info"):
            result = migrator.execute_migration(plan, dry_run=False, create_backup=False)
        assert result.skipped_count == 1

    def test_execute_transform_failure(
        self, migrator: JohnnyDecimalMigrator, tmp_path: Path
    ) -> None:
        """Rename failure => failed path (lines 207-210)."""
        non_existent = tmp_path / "Nonexistent"
        jd_num = JohnnyDecimalNumber(area=10)
        rule = TransformationRule(
            source_path=non_existent,
            target_name="10 Nonexistent",
            jd_number=jd_num,
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)

        with patch.object(migrator, "_save_rollback_info"):
            result = migrator.execute_migration(plan, dry_run=False, create_backup=False)
        assert result.failed_count == 1


class TestRollback:
    """Cover rollback branches — lines 257-288."""

    def test_rollback_no_history(self, migrator: JohnnyDecimalMigrator) -> None:
        """No migration history => returns False (line 253)."""
        assert migrator.rollback() is False

    def test_rollback_by_id_not_found(self, migrator: JohnnyDecimalMigrator) -> None:
        """Migration ID not found raises ValueError (line 264)."""
        migrator._rollback_history = [
            RollbackInfo(
                migration_id="abc",
                timestamp=MagicMock(),
                original_structure={},
                backup_path=None,
            )
        ]
        with pytest.raises(ValueError, match="not found"):
            migrator.rollback("xyz")

    def test_rollback_success(self, migrator: JohnnyDecimalMigrator, tmp_path: Path) -> None:
        """Successful rollback restores original names (lines 270-284)."""
        renamed = tmp_path / "10 Finance"
        renamed.mkdir()
        original = tmp_path / "Finance"

        migrator._rollback_history = [
            RollbackInfo(
                migration_id="test",
                timestamp=MagicMock(),
                original_structure={str(original): (str(renamed), "Finance")},
                backup_path=None,
            )
        ]
        result = migrator.rollback()
        assert result is True
        assert original.exists()

    def test_rollback_failure(self, migrator: JohnnyDecimalMigrator, tmp_path: Path) -> None:
        """Rollback exception returns False (line 287-288)."""
        existing = tmp_path / "10 Finance"
        existing.mkdir()
        # Target original path is in a non-writable location to force OSError
        migrator._rollback_history = [
            RollbackInfo(
                migration_id="test",
                timestamp=MagicMock(),
                original_structure={
                    "/nonexistent/deep/nested/original": (str(existing), "original")
                },
                backup_path=None,
            )
        ]
        # rename to non-existent parent dir raises OSError
        result = migrator.rollback()
        assert result is False


class TestGenerateReport:
    """Cover generate_report branches — lines 423, 432-435, 438-443."""

    def test_report_with_backup(self, migrator: JohnnyDecimalMigrator) -> None:
        result = MigrationResult(
            success=True,
            transformed_count=5,
            failed_count=0,
            skipped_count=0,
            duration_seconds=1.5,
            backup_path=Path("/backup/loc"),
        )
        report = migrator.generate_report(result)
        assert "Backup" in report
        assert "/backup/loc" in report

    def test_report_with_failures(self, migrator: JohnnyDecimalMigrator) -> None:
        result = MigrationResult(
            success=False,
            transformed_count=3,
            failed_count=2,
            skipped_count=0,
            duration_seconds=2.0,
            failed_paths=[(Path("/a"), "err1"), (Path("/b"), "err2")],
        )
        report = migrator.generate_report(result)
        assert "Failures" in report
        assert "err1" in report

    def test_report_with_many_skipped(self, migrator: JohnnyDecimalMigrator) -> None:
        """More than 10 skipped shows truncation (lines 438-443)."""
        result = MigrationResult(
            success=True,
            transformed_count=0,
            failed_count=0,
            skipped_count=15,
            duration_seconds=0.5,
            skipped_paths=[Path(f"/skip/{i}") for i in range(15)],
        )
        report = migrator.generate_report(result)
        assert "Skipped" in report
        assert "... and 5 more" in report
