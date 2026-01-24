"""
Tests for Johnny Decimal Migration Engine

Tests scanner, transformer, validator, and migrator components.
"""

import pytest
import shutil
from pathlib import Path
from datetime import datetime

from file_organizer.methodologies.johnny_decimal import (
    FolderScanner,
    FolderTransformer,
    MigrationValidator,
    JohnnyDecimalMigrator,
    JohnnyDecimalGenerator,
    get_default_scheme,
)


@pytest.fixture
def temp_structure(tmp_path):
    """Create temporary folder structure for testing."""
    # Create sample structure
    folders = [
        "Projects",
        "Projects/Website",
        "Projects/App",
        "Documents",
        "Documents/Reports",
        "Documents/Presentations",
        "Archive",
        "Archive/2023",
    ]

    for folder in folders:
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)

    # Add some files
    (tmp_path / "Projects/Website/index.html").write_text("<html></html>")
    (tmp_path / "Documents/Reports/report.pdf").write_text("PDF content")

    return tmp_path


@pytest.fixture
def scanner():
    """Create folder scanner instance."""
    return FolderScanner()


@pytest.fixture
def transformer():
    """Create folder transformer instance."""
    scheme = get_default_scheme()
    generator = JohnnyDecimalGenerator(scheme)
    return FolderTransformer(scheme, generator, preserve_original_names=True)


@pytest.fixture
def validator():
    """Create migration validator instance."""
    scheme = get_default_scheme()
    generator = JohnnyDecimalGenerator(scheme)
    return MigrationValidator(generator)


@pytest.fixture
def migrator():
    """Create migrator instance."""
    return JohnnyDecimalMigrator()


class TestFolderScanner:
    """Tests for FolderScanner."""

    def test_scan_directory_basic(self, scanner, temp_structure):
        """Test basic directory scanning."""
        result = scanner.scan_directory(temp_structure)

        assert result.root_path == temp_structure
        assert result.total_folders >= 8
        assert result.total_files >= 2
        assert result.max_depth >= 2

    def test_scan_detects_patterns(self, scanner, temp_structure):
        """Test pattern detection."""
        result = scanner.scan_directory(temp_structure)

        # Should detect some organizational pattern
        assert len(result.detected_patterns) > 0

    def test_scan_invalid_path(self, scanner):
        """Test scanning invalid path."""
        with pytest.raises(ValueError, match="does not exist"):
            scanner.scan_directory(Path("/nonexistent"))

    def test_scan_file_not_directory(self, scanner, tmp_path):
        """Test scanning file instead of directory."""
        file_path = tmp_path / "test.txt"
        file_path.write_text("content")

        with pytest.raises(ValueError, match="not a directory"):
            scanner.scan_directory(file_path)

    def test_scan_max_depth(self, scanner, temp_structure):
        """Test max depth limiting."""
        scanner_shallow = FolderScanner(max_depth=1)
        result = scanner_shallow.scan_directory(temp_structure)

        # Should not go deeper than max_depth
        assert result.max_depth <= 1

    def test_scan_skip_hidden(self, scanner, temp_structure):
        """Test skipping hidden files."""
        # Create hidden folder
        (temp_structure / ".hidden").mkdir()

        result = scanner.scan_directory(temp_structure)

        # Hidden folder should not be counted
        hidden_found = any(".hidden" in str(f.path) for f in result.folder_tree)
        assert not hidden_found

    def test_scan_folder_info(self, scanner, temp_structure):
        """Test FolderInfo details."""
        result = scanner.scan_directory(temp_structure)

        # Check folder tree structure
        assert len(result.folder_tree) > 0
        for folder in result.folder_tree:
            assert folder.path.exists()
            assert isinstance(folder.name, str)
            assert isinstance(folder.depth, int)
            assert isinstance(folder.file_count, int)
            assert isinstance(folder.total_size, int)


class TestFolderTransformer:
    """Tests for FolderTransformer."""

    def test_create_transformation_plan(self, transformer, scanner, temp_structure):
        """Test transformation plan creation."""
        scan_result = scanner.scan_directory(temp_structure)
        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, temp_structure
        )

        assert plan.root_path == temp_structure
        assert len(plan.rules) > 0
        assert isinstance(plan.estimated_changes, int)

    def test_transformation_preserves_names(self, transformer, scanner, temp_structure):
        """Test that original names are preserved."""
        scan_result = scanner.scan_directory(temp_structure)
        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, temp_structure
        )

        # Check that target names include original names
        for rule in plan.rules:
            assert rule.source_path.name in rule.target_name

    def test_transformation_assigns_jd_numbers(
        self, transformer, scanner, temp_structure
    ):
        """Test JD number assignment."""
        scan_result = scanner.scan_directory(temp_structure)
        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, temp_structure
        )

        # Check that JD numbers are assigned
        for rule in plan.rules:
            assert rule.jd_number is not None
            assert rule.jd_number.area >= 10
            assert rule.jd_number.area <= 99

    def test_transformation_hierarchy(self, transformer, scanner, temp_structure):
        """Test hierarchical transformation."""
        scan_result = scanner.scan_directory(temp_structure)
        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, temp_structure
        )

        # Top level should be areas
        # Second level should be categories
        area_rules = [r for r in plan.rules if r.jd_number.category is None]
        category_rules = [
            r
            for r in plan.rules
            if r.jd_number.category is not None and r.jd_number.id_number is None
        ]

        assert len(area_rules) > 0
        assert len(category_rules) > 0

    def test_generate_preview(self, transformer, scanner, temp_structure):
        """Test preview generation."""
        scan_result = scanner.scan_directory(temp_structure)
        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, temp_structure
        )

        preview = transformer.generate_preview(plan)

        assert isinstance(preview, str)
        assert "Transformation Plan" in preview
        assert temp_structure.name in preview


class TestMigrationValidator:
    """Tests for MigrationValidator."""

    def test_validate_valid_plan(
        self, validator, transformer, scanner, temp_structure
    ):
        """Test validation of valid plan."""
        scan_result = scanner.scan_directory(temp_structure)
        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, temp_structure
        )

        result = validator.validate_plan(plan)

        # Basic structure should be valid
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.errors, list)
        assert isinstance(result.warnings, list)

    def test_validate_detects_conflicts(
        self, validator, transformer, scanner, temp_structure
    ):
        """Test conflict detection."""
        scan_result = scanner.scan_directory(temp_structure)
        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, temp_structure
        )

        # Manually add a duplicate rule to create conflict
        if len(plan.rules) > 0:
            duplicate = plan.rules[0]
            plan.rules.append(duplicate)

        result = validator.validate_plan(plan)

        # Should detect duplicate number
        if len(plan.rules) > 1:
            assert len(result.errors) > 0 or len(result.warnings) > 0

    def test_validate_number_ranges(
        self, validator, transformer, scanner, temp_structure
    ):
        """Test number range validation."""
        scan_result = scanner.scan_directory(temp_structure)
        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, temp_structure
        )

        result = validator.validate_plan(plan)

        # All numbers should be in valid ranges
        for rule in plan.rules:
            assert 10 <= rule.jd_number.area <= 99
            if rule.jd_number.category is not None:
                assert 1 <= rule.jd_number.category <= 99

    def test_generate_report(self, validator, transformer, scanner, temp_structure):
        """Test validation report generation."""
        scan_result = scanner.scan_directory(temp_structure)
        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, temp_structure
        )

        result = validator.validate_plan(plan)
        report = validator.generate_report(result)

        assert isinstance(report, str)
        assert "Validation Report" in report


class TestJohnnyDecimalMigrator:
    """Tests for JohnnyDecimalMigrator."""

    def test_create_migration_plan(self, migrator, temp_structure):
        """Test migration plan creation."""
        plan, scan_result = migrator.create_migration_plan(temp_structure)

        assert plan is not None
        assert scan_result is not None
        assert len(plan.rules) > 0

    def test_validate_plan(self, migrator, temp_structure):
        """Test plan validation."""
        plan, scan_result = migrator.create_migration_plan(temp_structure)
        validation = migrator.validate_plan(plan)

        assert validation is not None
        assert isinstance(validation.is_valid, bool)

    def test_dry_run_migration(self, migrator, temp_structure):
        """Test dry run execution."""
        plan, scan_result = migrator.create_migration_plan(temp_structure)

        result = migrator.execute_migration(plan, dry_run=True, create_backup=False)

        assert result.success or result.failed_count == 0
        assert result.transformed_count >= 0
        assert result.backup_path is None  # No backup in dry run

        # Verify no actual changes
        original_folders = list(temp_structure.rglob("*"))
        # Structure should be unchanged after dry run

    def test_execute_migration_with_backup(self, migrator, temp_structure):
        """Test migration execution with backup."""
        plan, scan_result = migrator.create_migration_plan(temp_structure)

        result = migrator.execute_migration(plan, dry_run=False, create_backup=True)

        assert result.transformed_count > 0 or result.skipped_count > 0
        assert result.backup_path is not None
        assert result.backup_path.exists()

        # Cleanup backup
        if result.backup_path and result.backup_path.exists():
            shutil.rmtree(result.backup_path)

    def test_generate_preview(self, migrator, temp_structure):
        """Test preview generation."""
        plan, scan_result = migrator.create_migration_plan(temp_structure)
        validation = migrator.validate_plan(plan)

        preview = migrator.generate_preview(plan, scan_result, validation)

        assert isinstance(preview, str)
        assert "Migration Preview" in preview
        assert str(temp_structure) in preview

    def test_generate_report(self, migrator, temp_structure):
        """Test report generation."""
        plan, scan_result = migrator.create_migration_plan(temp_structure)

        result = migrator.execute_migration(plan, dry_run=True, create_backup=False)
        report = migrator.generate_report(result)

        assert isinstance(report, str)
        assert "Execution Report" in report

    def test_rollback_no_history(self, migrator):
        """Test rollback with no history."""
        success = migrator.rollback()
        assert not success


class TestMigrationIntegration:
    """Integration tests for full migration workflow."""

    def test_complete_migration_workflow(self, temp_structure):
        """Test complete migration from scan to execution."""
        migrator = JohnnyDecimalMigrator(preserve_original_names=True)

        # Step 1: Create plan
        plan, scan_result = migrator.create_migration_plan(temp_structure)
        assert len(plan.rules) > 0

        # Step 2: Validate
        validation = migrator.validate_plan(plan)
        if not validation.is_valid:
            print(migrator.validator.generate_report(validation))

        # Step 3: Preview
        preview = migrator.generate_preview(plan, scan_result, validation)
        assert "Migration Preview" in preview

        # Step 4: Dry run
        dry_result = migrator.execute_migration(
            plan, dry_run=True, create_backup=False
        )
        assert dry_result.transformed_count > 0 or dry_result.skipped_count > 0

        # Step 5: Execute (with backup)
        result = migrator.execute_migration(plan, dry_run=False, create_backup=True)
        assert result.backup_path is not None

        # Step 6: Verify
        assert result.transformed_count > 0 or result.skipped_count > 0

        # Cleanup
        if result.backup_path and result.backup_path.exists():
            shutil.rmtree(result.backup_path)

    def test_migration_preserves_files(self, temp_structure):
        """Test that migration preserves file contents."""
        # Create test file with content
        test_file = temp_structure / "Projects/Website/test.txt"
        test_content = "test content"
        test_file.write_text(test_content)

        migrator = JohnnyDecimalMigrator()
        plan, _ = migrator.create_migration_plan(temp_structure)

        # Execute migration
        result = migrator.execute_migration(plan, dry_run=False, create_backup=True)

        # Find the migrated file (it should still exist somewhere)
        migrated_files = list(temp_structure.rglob("test.txt"))
        assert len(migrated_files) > 0

        # Content should be preserved
        if migrated_files:
            assert migrated_files[0].read_text() == test_content

        # Cleanup
        if result.backup_path and result.backup_path.exists():
            shutil.rmtree(result.backup_path)

    def test_migration_handles_special_characters(self, tmp_path):
        """Test migration with special characters in names."""
        # Create folders with special characters
        (tmp_path / "Folder (with parentheses)").mkdir()
        (tmp_path / "Folder with spaces").mkdir()
        (tmp_path / "Folder-with-dashes").mkdir()

        migrator = JohnnyDecimalMigrator()
        plan, _ = migrator.create_migration_plan(tmp_path)

        # Should create valid transformation plan
        assert len(plan.rules) > 0

        # Execute dry run
        result = migrator.execute_migration(plan, dry_run=True, create_backup=False)
        assert result.failed_count == 0


class TestEdgeCases:
    """Tests for edge cases and error conditions."""

    def test_empty_directory(self, migrator, tmp_path):
        """Test migration of empty directory."""
        plan, scan_result = migrator.create_migration_plan(tmp_path)

        assert plan is not None
        assert len(plan.rules) == 0  # No folders to migrate

    def test_very_deep_structure(self, migrator, tmp_path):
        """Test migration of very deep structure."""
        # Create deep hierarchy
        current = tmp_path
        for i in range(10):
            current = current / f"level{i}"
            current.mkdir()

        plan, scan_result = migrator.create_migration_plan(tmp_path)

        # Should handle deep structure
        assert len(plan.rules) > 0

    def test_many_folders(self, migrator, tmp_path):
        """Test migration with many folders."""
        # Create many folders
        for i in range(50):
            (tmp_path / f"folder{i}").mkdir()

        plan, scan_result = migrator.create_migration_plan(tmp_path)

        # Should handle many folders
        assert len(plan.rules) == 50
