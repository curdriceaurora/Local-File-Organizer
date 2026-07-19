"""End-to-end integration tests for the Johnny Decimal migrator.

Unlike the unit tests in ``tests/methodologies/johnny_decimal/``, these
exercise :class:`JohnnyDecimalMigrator` against a real on-disk directory
tree: scanning, planning, validating, executing real folder renames,
creating a real backup, persisting rollback metadata, and rolling back —
with only the data directory redirected to a temp path.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.johnny_decimal import JohnnyDecimalMigrator

pytestmark = [pytest.mark.integration, pytest.mark.ci]


@pytest.fixture
def source_tree(tmp_path: Path) -> Path:
    """Create a realistic folder structure with files to migrate."""
    root = tmp_path / "workspace"
    folders = [
        "Projects/Website",
        "Projects/MobileApp",
        "Documents/Reports",
        "Documents/Invoices",
        "Archive/2023",
    ]
    for folder in folders:
        (root / folder).mkdir(parents=True, exist_ok=True)

    (root / "Projects/Website/index.html").write_text("<html></html>", encoding="utf-8")
    (root / "Documents/Reports/q1.pdf").write_text("report", encoding="utf-8")
    (root / "Documents/Invoices/jan.txt").write_text("invoice", encoding="utf-8")
    return root


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the migrator's data directory to a temp path."""
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setattr(
        "file_organizer.config.path_manager.get_data_dir",
        lambda: data,
    )
    return data


def test_dry_run_leaves_disk_untouched(source_tree: Path) -> None:
    """A dry run reports transformations but changes nothing on disk."""
    migrator = JohnnyDecimalMigrator()
    plan, scan_result = migrator.create_migration_plan(source_tree)

    assert plan.rules, "expected at least one transformation rule"
    assert scan_result.total_folders >= 5
    assert scan_result.total_files >= 3

    before = sorted(p.relative_to(source_tree).as_posix() for p in source_tree.rglob("*"))

    result = migrator.execute_migration(plan, dry_run=True, create_backup=True)

    assert result.transformed_count == len(plan.rules)
    assert result.failed_count == 0
    assert result.backup_path is None  # no backup for a dry run

    after = sorted(p.relative_to(source_tree).as_posix() for p in source_tree.rglob("*"))
    assert before == after, "dry run must not mutate the tree"


def test_real_migration_renames_folders_and_preserves_files(
    source_tree: Path, data_dir: Path
) -> None:
    """A real migration renames folders per the plan and keeps file contents."""
    migrator = JohnnyDecimalMigrator()
    plan, _ = migrator.create_migration_plan(source_tree)
    validation = migrator.validate_plan(plan)
    assert validation.is_valid, validation.errors

    # Record the file payloads keyed by name so we can confirm they survive.
    original_files = {p.name: p.read_text(encoding="utf-8") for p in source_tree.rglob("*.pdf")}
    original_files.update(
        {p.name: p.read_text(encoding="utf-8") for p in source_tree.rglob("*.txt")}
    )
    original_files.update(
        {p.name: p.read_text(encoding="utf-8") for p in source_tree.rglob("*.html")}
    )

    result = migrator.execute_migration(plan, dry_run=False, create_backup=True)

    assert result.success, result.failed_paths
    assert result.failed_count == 0
    assert result.transformed_count > 0

    # Every top-level rule target should now exist on disk.
    top_level_rules = [r for r in plan.rules if r.source_path.parent == source_tree]
    assert top_level_rules
    for rule in top_level_rules:
        target = source_tree / rule.target_name
        assert target.exists(), f"expected renamed folder {target}"
        assert rule.target_name != rule.source_path.name or target == rule.source_path

    # A real backup directory was created as a sibling of the root.
    assert result.backup_path is not None
    assert result.backup_path.exists()
    assert result.backup_path.parent == source_tree.parent

    # File contents survived the migration.
    surviving = {
        p.name: p.read_text(encoding="utf-8") for p in source_tree.rglob("*") if p.is_file()
    }
    for name, content in original_files.items():
        assert surviving.get(name) == content

    # Rollback metadata was persisted to the redirected data dir.
    rollback_files = list((data_dir / "rollback").glob("*.json"))
    assert rollback_files, "expected a rollback manifest to be written"


def test_rollback_restores_original_names(source_tree: Path, data_dir: Path) -> None:
    """Rolling back the latest migration restores the original folder names."""
    migrator = JohnnyDecimalMigrator()
    plan, _ = migrator.create_migration_plan(source_tree)

    original_top_level = sorted(p.name for p in source_tree.iterdir() if p.is_dir())

    result = migrator.execute_migration(plan, dry_run=False, create_backup=True)
    assert result.success

    renamed_top_level = sorted(p.name for p in source_tree.iterdir() if p.is_dir())
    # The backup dir is a sibling, not inside the root, so the root's
    # top-level names should have actually changed.
    assert renamed_top_level != original_top_level

    assert migrator.rollback() is True

    restored_top_level = sorted(p.name for p in source_tree.iterdir() if p.is_dir())
    for name in original_top_level:
        assert name in restored_top_level


def test_rollback_without_history_returns_false(source_tree: Path) -> None:
    """Rollback with no recorded migration fails cleanly."""
    migrator = JohnnyDecimalMigrator()
    assert migrator.rollback() is False


def test_generate_preview_and_report(source_tree: Path, data_dir: Path) -> None:
    """Preview and report render real plan/result data end-to-end."""
    migrator = JohnnyDecimalMigrator()
    plan, scan_result = migrator.create_migration_plan(source_tree)
    validation = migrator.validate_plan(plan)

    preview = migrator.generate_preview(plan, scan_result, validation)
    assert "Johnny Decimal Migration Preview" in preview
    assert str(scan_result.root_path) in preview

    result = migrator.execute_migration(plan, dry_run=False, create_backup=True)
    report = migrator.generate_report(result)
    assert "Migration Execution Report" in report
    assert ("SUCCESS" if result.success else "FAILED") in report
