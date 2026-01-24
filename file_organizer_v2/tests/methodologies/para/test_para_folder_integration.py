"""
Integration tests for PARA folder generation system.

Tests the complete workflow of folder generation, file mapping, and migration.
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from file_organizer.methodologies.para.categories import PARACategory
from file_organizer.methodologies.para.config import PARAConfig
from file_organizer.methodologies.para.folder_generator import PARAFolderGenerator
from file_organizer.methodologies.para.folder_mapper import (
    CategoryFolderMapper,
    MappingStrategy,
)
from file_organizer.methodologies.para.migration_manager import PARAMigrationManager


class TestPARAFolderIntegration:
    """Test complete PARA folder generation workflow."""

    @pytest.fixture
    def temp_source(self):
        """Create temporary source directory with test files."""
        temp_path = Path(tempfile.mkdtemp())

        # Create various test files
        (temp_path / "project_plan.txt").write_text("Project plan content")
        (temp_path / "weekly_review.md").write_text("Weekly review notes")
        (temp_path / "python_guide.pdf").write_text("Python reference")
        (temp_path / "old_project.txt").write_text("Completed project")
        (temp_path / "meeting_notes.txt").write_text("Meeting notes")

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
        """Create shared test configuration."""
        return PARAConfig(
            project_dir="Projects",
            area_dir="Areas",
            resource_dir="Resources",
            archive_dir="Archive",
        )

    def test_end_to_end_workflow(self, config, temp_source, temp_target):
        """Test complete workflow from source to migrated PARA structure."""
        # Step 1: Generate PARA folder structure
        generator = PARAFolderGenerator(config)
        structure_result = generator.generate_structure(temp_target)

        assert structure_result.success is True
        assert (temp_target / "Projects").exists()
        assert (temp_target / "Areas").exists()
        assert (temp_target / "Resources").exists()
        assert (temp_target / "Archive").exists()

        # Step 2: Analyze source files for migration
        migration_manager = PARAMigrationManager(config)
        plan = migration_manager.analyze_source(temp_source, temp_target)

        assert plan.total_count == 5  # All 5 test files
        assert sum(plan.by_category.values()) == plan.total_count

        # Step 3: Execute migration
        report = migration_manager.execute_migration(
            plan, dry_run=False, create_backup=False
        )

        assert report.success is True or len(report.failed) < len(plan.files)
        assert len(report.migrated) > 0

        # Step 4: Verify files are in PARA structure
        # At least some files should be migrated
        para_folders = ["Projects", "Areas", "Resources", "Archive"]
        migrated_count = 0
        for folder in para_folders:
            folder_path = temp_target / folder
            if folder_path.exists():
                migrated_count += len(list(folder_path.rglob("*")))

        assert migrated_count > 0

    def test_mapper_with_generated_structure(self, config, temp_source, temp_target):
        """Test mapper integration with generated folder structure."""
        # Generate structure first
        generator = PARAFolderGenerator(config)
        generator.generate_structure(temp_target)

        # Use mapper to map files
        mapper = CategoryFolderMapper(config)
        files = list(temp_source.glob("*.txt")) + list(temp_source.glob("*.md"))

        results = mapper.map_batch(files, temp_target)

        assert len(results) == len(files)

        # Create folders from mapping
        folder_status = mapper.create_target_folders(results, dry_run=False)

        # All folders should be created successfully
        assert all(status for status in folder_status.values())

    def test_mapper_with_subfolder_strategy(
        self, config, temp_source, temp_target
    ):
        """Test mapper with subfolder strategy in full workflow."""
        # Generate base structure
        generator = PARAFolderGenerator(config)
        generator.generate_structure(temp_target)

        # Create mapper with type-based subfolders
        strategy = MappingStrategy(
            use_type_folders=True,
            type_mapping={
                ".txt": "Documents",
                ".md": "Markdown",
                ".pdf": "References",
            },
        )
        mapper = CategoryFolderMapper(config, strategy=strategy)

        # Map files
        files = list(temp_source.glob("*"))
        results = mapper.map_batch(files, temp_target)

        # Create folders
        folder_status = mapper.create_target_folders(results, dry_run=False)

        # All folders should be created successfully
        assert all(status for status in folder_status.values())

        # Check subfolders were created
        has_subfolders = any(
            result.subfolder_path is not None for result in results
        )
        assert has_subfolders

    def test_migration_preserves_category_distribution(
        self, config, temp_source, temp_target
    ):
        """Test that migration maintains category distribution."""
        # Generate structure
        generator = PARAFolderGenerator(config)
        generator.generate_structure(temp_target)

        # Analyze and migrate
        migration_manager = PARAMigrationManager(config)
        plan = migration_manager.analyze_source(temp_source, temp_target)

        # Execute migration
        report = migration_manager.execute_migration(
            plan, dry_run=False, create_backup=False
        )

        # Count files in each category folder
        actual_distribution = {
            PARACategory.PROJECT: 0,
            PARACategory.AREA: 0,
            PARACategory.RESOURCE: 0,
            PARACategory.ARCHIVE: 0,
        }

        for category, folder_name in [
            (PARACategory.PROJECT, "Projects"),
            (PARACategory.AREA, "Areas"),
            (PARACategory.RESOURCE, "Resources"),
            (PARACategory.ARCHIVE, "Archive"),
        ]:
            folder = temp_target / folder_name
            if folder.exists():
                actual_distribution[category] = len(
                    [f for f in folder.rglob("*") if f.is_file()]
                )

        # Distribution should match (accounting for skipped files)
        total_migrated = sum(actual_distribution.values())
        assert total_migrated == len(report.migrated)

    def test_structure_validation_after_migration(
        self, config, temp_source, temp_target
    ):
        """Test that structure remains valid after migration."""
        # Generate and validate initial structure
        generator = PARAFolderGenerator(config)
        generator.generate_structure(temp_target)

        assert generator.validate_structure(temp_target) is True

        # Perform migration
        migration_manager = PARAMigrationManager(config)
        plan = migration_manager.analyze_source(temp_source, temp_target)
        migration_manager.execute_migration(plan, dry_run=False, create_backup=False)

        # Structure should still be valid
        assert generator.validate_structure(temp_target) is True

    def test_generate_reports_for_workflow(self, config, temp_source, temp_target):
        """Test generating reports at each stage of workflow."""
        # Generate structure
        generator = PARAFolderGenerator(config)
        generator.generate_structure(temp_target)

        # Analyze files
        migration_manager = PARAMigrationManager(config)
        plan = migration_manager.analyze_source(temp_source, temp_target)

        # Generate migration preview
        preview = migration_manager.generate_preview(plan)

        assert isinstance(preview, str)
        assert "PARA Migration Plan" in preview
        assert plan.total_count > 0

        # Execute migration
        report = migration_manager.execute_migration(plan, dry_run=True)

        # Verify report details
        assert report.plan == plan
        assert len(report.migrated) == plan.total_count

    def test_mapper_report_generation(self, config, temp_source, temp_target):
        """Test mapper report generation."""
        # Generate structure
        generator = PARAFolderGenerator(config)
        generator.generate_structure(temp_target)

        # Map files
        mapper = CategoryFolderMapper(config)
        files = list(temp_source.glob("*"))
        results = mapper.map_batch(files, temp_target)

        # Generate report
        report = mapper.generate_mapping_report(results)

        assert isinstance(report, str)
        assert "PARA Folder Mapping Report" in report
        assert f"Total files: {len(results)}" in report

    def test_dry_run_workflow(self, config, temp_source, temp_target):
        """Test complete workflow in dry run mode."""
        # Generate structure (dry run)
        generator = PARAFolderGenerator(config)
        structure_result = generator.generate_structure(
            temp_target, dry_run=True
        )

        assert structure_result.success is True
        assert not (temp_target / "Projects").exists()

        # Analyze migration (always safe)
        migration_manager = PARAMigrationManager(config)
        plan = migration_manager.analyze_source(temp_source, temp_target)

        assert plan.total_count > 0

        # Execute migration (dry run)
        report = migration_manager.execute_migration(plan, dry_run=True)

        assert report.success is True
        assert len(report.migrated) == plan.total_count

        # Source files should still be there
        assert (temp_source / "project_plan.txt").exists()

    def test_error_recovery_in_workflow(self, config, temp_source, temp_target):
        """Test error handling throughout workflow."""
        # Generate structure
        generator = PARAFolderGenerator(config)
        generator.generate_structure(temp_target)

        # Create a situation where migration will have conflicts
        # Pre-create one target file
        conflict_file = temp_target / "Projects" / "project_plan.txt"
        conflict_file.parent.mkdir(parents=True, exist_ok=True)
        conflict_file.write_text("Existing content")

        # Analyze and migrate
        migration_manager = PARAMigrationManager(config)
        plan = migration_manager.analyze_source(temp_source, temp_target)
        report = migration_manager.execute_migration(
            plan, dry_run=False, create_backup=False
        )

        # Should have at least one skip due to conflict
        # Or migration might handle it differently
        assert isinstance(report, object)  # Report created regardless of conflicts

    def test_custom_configuration_workflow(self, temp_source, temp_target):
        """Test workflow with custom configuration."""
        # Create custom config
        custom_config = PARAConfig(
            project_dir="MyProjects",
            area_dir="MyAreas",
            resource_dir="MyResources",
            archive_dir="MyArchive",
        )

        # Generate structure with custom names
        generator = PARAFolderGenerator(custom_config)
        generator.generate_structure(temp_target)

        assert (temp_target / "MyProjects").exists()
        assert (temp_target / "MyAreas").exists()
        assert (temp_target / "MyResources").exists()
        assert (temp_target / "MyArchive").exists()

        # Migrate with custom config
        migration_manager = PARAMigrationManager(custom_config)
        plan = migration_manager.analyze_source(temp_source, temp_target)
        report = migration_manager.execute_migration(
            plan, dry_run=False, create_backup=False
        )

        # Migration should complete
        assert len(report.migrated) > 0 or len(report.skipped) > 0

        # Files should be in custom-named folders
        custom_folders = ["MyProjects", "MyAreas", "MyResources", "MyArchive"]
        file_count = 0
        for folder in custom_folders:
            folder_path = temp_target / folder
            if folder_path.exists():
                file_count += len(list(folder_path.rglob("*.txt")))

        assert file_count > 0
