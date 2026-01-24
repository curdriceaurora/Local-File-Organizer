"""
Tests for PARA migration manager.

Tests file migration from flat structures to PARA organization.
"""

import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.migration_manager import (
    MigrationFile,
    MigrationPlan,
    MigrationReport,
    PARAMigrationManager,
)


class TestPARAMigrationManager:
    """Test PARA migration functionality."""

    @pytest.fixture
    def temp_source(self):
        """Create temporary source directory with test files."""
        temp_path = Path(tempfile.mkdtemp())

        # Create test files
        (temp_path / "project_plan.txt").write_text("Project plan content")
        (temp_path / "meeting_notes.txt").write_text("Meeting notes")
        (temp_path / "reference_doc.pdf").write_text("Reference")
        (temp_path / "old_file.txt").write_text("Old content")

        # Create nested structure
        subdir = temp_path / "subdir"
        subdir.mkdir()
        (subdir / "nested_file.txt").write_text("Nested content")

        yield temp_path

        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def temp_target(self):
        """Create temporary target directory."""
        temp_path = Path(tempfile.mkdtemp())
        yield temp_path

        # Cleanup
        if temp_path.exists():
            shutil.rmtree(temp_path)

    @pytest.fixture
    def config(self):
        """Create test configuration."""
        return PARAConfig(
            project_dir="Projects",
            area_dir="Areas",
            resource_dir="Resources",
            archive_dir="Archive",
        )

    @pytest.fixture
    def migration_manager(self, config):
        """Create migration manager instance."""
        return PARAMigrationManager(config)

    def test_initialization(self, config):
        """Test migration manager initialization."""
        manager = PARAMigrationManager(config)
        assert manager.config == config
        assert manager.heuristic_engine is not None
        assert manager.folder_generator is not None

        # Test default config
        default_manager = PARAMigrationManager()
        assert default_manager.config is not None

    def test_analyze_source_basic(self, migration_manager, temp_source, temp_target):
        """Test analyzing source directory."""
        plan = migration_manager.analyze_source(
            temp_source, temp_target, recursive=False
        )

        assert isinstance(plan, MigrationPlan)
        assert plan.total_count == 4  # 4 files in root
        assert plan.estimated_size > 0
        assert isinstance(plan.created_at, datetime)

    def test_analyze_source_recursive(self, migration_manager, temp_source, temp_target):
        """Test recursive source analysis."""
        plan = migration_manager.analyze_source(
            temp_source, temp_target, recursive=True
        )

        assert plan.total_count == 5  # 4 in root + 1 in subdir
        assert len(plan.files) == 5

    def test_analyze_source_file_extensions_filter(
        self, migration_manager, temp_source, temp_target
    ):
        """Test filtering by file extensions."""
        plan = migration_manager.analyze_source(
            temp_source, temp_target, recursive=False, file_extensions=[".txt"]
        )

        # Only .txt files
        assert all(f.source_path.suffix == ".txt" for f in plan.files)
        assert plan.total_count < 4  # Less than all files

    def test_migration_plan_categories(
        self, migration_manager, temp_source, temp_target
    ):
        """Test that migration plan includes category breakdown."""
        plan = migration_manager.analyze_source(temp_source, temp_target)

        # Check by_category dict has all categories
        assert PARACategory.PROJECT in plan.by_category
        assert PARACategory.AREA in plan.by_category
        assert PARACategory.RESOURCE in plan.by_category
        assert PARACategory.ARCHIVE in plan.by_category

        # Total should match sum of categories
        total_by_cat = sum(plan.by_category.values())
        assert total_by_cat == plan.total_count

    def test_migration_file_details(
        self, migration_manager, temp_source, temp_target
    ):
        """Test migration file contains required details."""
        plan = migration_manager.analyze_source(temp_source, temp_target)

        for migration_file in plan.files:
            assert isinstance(migration_file, MigrationFile)
            assert migration_file.source_path.exists()
            assert isinstance(migration_file.target_category, PARACategory)
            assert migration_file.target_path is not None
            assert 0.0 <= migration_file.confidence <= 1.0
            assert isinstance(migration_file.reasoning, list)

    def test_execute_migration_dry_run(
        self, migration_manager, temp_source, temp_target
    ):
        """Test dry run migration doesn't move files."""
        plan = migration_manager.analyze_source(temp_source, temp_target)

        report = migration_manager.execute_migration(plan, dry_run=True)

        assert isinstance(report, MigrationReport)
        assert report.success is True
        assert len(report.migrated) == plan.total_count
        assert len(report.failed) == 0

        # Files should still be in source
        assert (temp_source / "project_plan.txt").exists()
        assert (temp_source / "meeting_notes.txt").exists()

    def test_execute_migration_actual(
        self, migration_manager, temp_source, temp_target
    ):
        """Test actual file migration."""
        # Create target PARA structure first
        migration_manager.folder_generator.generate_structure(temp_target)

        plan = migration_manager.analyze_source(
            temp_source, temp_target, recursive=False
        )

        report = migration_manager.execute_migration(
            plan, dry_run=False, create_backup=False
        )

        assert report.success is True
        assert len(report.migrated) > 0

        # Check files were moved to target
        for migration_file in plan.files:
            # Source should be moved (may not exist)
            # Target should exist
            assert (
                migration_file.target_path.exists()
                or migration_file.source_path in [f[0] for f in report.failed]
            )

    def test_execute_migration_skip_existing(
        self, migration_manager, temp_source, temp_target
    ):
        """Test that existing target files are skipped."""
        # Create target structure
        migration_manager.folder_generator.generate_structure(temp_target)

        plan = migration_manager.analyze_source(temp_source, temp_target)

        # Create one target file to cause skip
        if plan.files:
            first_migration = plan.files[0]
            first_migration.target_path.parent.mkdir(parents=True, exist_ok=True)
            first_migration.target_path.write_text("Existing content")

            report = migration_manager.execute_migration(
                plan, dry_run=False, create_backup=False
            )

            assert len(report.skipped) >= 1
            assert first_migration.source_path in report.skipped

    def test_execute_migration_preserve_timestamps(
        self, migration_manager, temp_source, temp_target
    ):
        """Test that file timestamps are preserved."""
        # Create target structure
        migration_manager.folder_generator.generate_structure(temp_target)

        # Get original timestamp
        test_file = temp_source / "project_plan.txt"
        original_mtime = test_file.stat().st_mtime

        plan = migration_manager.analyze_source(
            temp_source, temp_target, recursive=False
        )

        migration_manager.execute_migration(
            plan, dry_run=False, create_backup=False, preserve_timestamps=True
        )

        # Find the migrated file
        for migration_file in plan.files:
            if migration_file.source_path == test_file:
                if migration_file.target_path.exists():
                    new_mtime = migration_file.target_path.stat().st_mtime
                    # Timestamps should be close (within 1 second)
                    assert abs(new_mtime - original_mtime) < 1.0
                    break

    def test_migration_report_details(
        self, migration_manager, temp_source, temp_target
    ):
        """Test migration report contains all details."""
        migration_manager.folder_generator.generate_structure(temp_target)

        plan = migration_manager.analyze_source(temp_source, temp_target)
        report = migration_manager.execute_migration(plan, dry_run=True)

        assert isinstance(report, MigrationReport)
        assert report.plan == plan
        assert isinstance(report.migrated, list)
        assert isinstance(report.failed, list)
        assert isinstance(report.skipped, list)
        assert report.duration_seconds >= 0
        assert isinstance(report.success, bool)

    def test_generate_preview(self, migration_manager, temp_source, temp_target):
        """Test generating migration preview."""
        plan = migration_manager.analyze_source(temp_source, temp_target)

        preview = migration_manager.generate_preview(plan)

        assert isinstance(preview, str)
        assert "PARA Migration Plan" in preview
        assert f"Total files: {plan.total_count}" in preview
        assert "Distribution by Category" in preview

        # Check category names appear
        for category in PARACategory:
            assert category.value in preview.lower()

    def test_preview_shows_sample_files(
        self, migration_manager, temp_source, temp_target
    ):
        """Test that preview shows sample file mappings."""
        plan = migration_manager.analyze_source(temp_source, temp_target)

        preview = migration_manager.generate_preview(plan)

        # Should show file names and categories
        for migration_file in plan.files[:3]:  # Check first few
            assert migration_file.source_path.name in preview


class TestMigrationFile:
    """Test MigrationFile dataclass."""

    def test_valid_migration_file(self):
        """Test creating valid migration file."""
        migration_file = MigrationFile(
            source_path=Path("/source/file.txt"),
            target_category=PARACategory.PROJECT,
            target_path=Path("/target/Projects/file.txt"),
            confidence=0.85,
            reasoning=["Reason 1", "Reason 2"],
        )

        assert migration_file.source_path == Path("/source/file.txt")
        assert migration_file.target_category == PARACategory.PROJECT
        assert migration_file.confidence == 0.85
        assert len(migration_file.reasoning) == 2


class TestMigrationPlan:
    """Test MigrationPlan dataclass."""

    def test_valid_migration_plan(self):
        """Test creating valid migration plan."""
        files = [
            MigrationFile(
                source_path=Path("/source/file1.txt"),
                target_category=PARACategory.PROJECT,
                target_path=Path("/target/Projects/file1.txt"),
                confidence=0.8,
                reasoning=[],
            ),
            MigrationFile(
                source_path=Path("/source/file2.txt"),
                target_category=PARACategory.RESOURCE,
                target_path=Path("/target/Resources/file2.txt"),
                confidence=0.7,
                reasoning=[],
            ),
        ]

        by_category = {
            PARACategory.PROJECT: 1,
            PARACategory.AREA: 0,
            PARACategory.RESOURCE: 1,
            PARACategory.ARCHIVE: 0,
        }

        plan = MigrationPlan(
            files=files,
            total_count=2,
            by_category=by_category,
            estimated_size=1024,
            created_at=datetime.now(),
        )

        assert len(plan.files) == 2
        assert plan.total_count == 2
        assert plan.by_category[PARACategory.PROJECT] == 1
        assert plan.estimated_size == 1024


class TestMigrationReport:
    """Test MigrationReport dataclass."""

    def test_successful_report(self):
        """Test successful migration report."""
        plan = MigrationPlan(
            files=[],
            total_count=0,
            by_category={},
            estimated_size=0,
            created_at=datetime.now(),
        )

        report = MigrationReport(
            plan=plan,
            migrated=[Path("/target/file1.txt")],
            failed=[],
            skipped=[],
            duration_seconds=1.5,
            success=True,
        )

        assert report.success is True
        assert len(report.migrated) == 1
        assert len(report.failed) == 0
        assert report.duration_seconds == 1.5

    def test_failed_report(self):
        """Test report with failures."""
        plan = MigrationPlan(
            files=[],
            total_count=0,
            by_category={},
            estimated_size=0,
            created_at=datetime.now(),
        )

        report = MigrationReport(
            plan=plan,
            migrated=[],
            failed=[(Path("/source/file.txt"), "Permission denied")],
            skipped=[],
            duration_seconds=0.5,
            success=False,
        )

        assert report.success is False
        assert len(report.failed) == 1
        assert report.failed[0][1] == "Permission denied"
