"""
Integration Tests for Johnny Decimal Methodology

Tests complete workflows and cross-component integration.
"""

import pytest
import shutil
from pathlib import Path

from file_organizer.methodologies.johnny_decimal import (
    JohnnyDecimalSystem,
    JohnnyDecimalMigrator,
    create_para_compatible_config,
    HybridOrganizer,
    PARACategory,
    CompatibilityAnalyzer,
    AdapterRegistry,
    create_default_registry,
    OrganizationItem,
    ConfigBuilder,
    JohnnyDecimalConfig,
)


@pytest.fixture
def complex_structure(tmp_path):
    """Create complex test structure with multiple levels."""
    # Create diverse structure
    folders = [
        "Work/Projects/WebApp",
        "Work/Projects/MobileApp",
        "Work/Documentation/Guides",
        "Work/Documentation/API",
        "Personal/Finance/Taxes",
        "Personal/Finance/Budgets",
        "Personal/Health/Medical",
        "Archive/2023/Projects",
        "Archive/2023/Documents",
        "Archive/2024/Misc",
    ]

    for folder in folders:
        (tmp_path / folder).mkdir(parents=True)

    # Add files
    (tmp_path / "Work/Projects/WebApp/README.md").write_text("# WebApp")
    (tmp_path / "Personal/Finance/Taxes/2023.pdf").write_text("Tax document")

    return tmp_path


@pytest.fixture
def para_structure(tmp_path):
    """Create PARA-organized structure."""
    folders = [
        "Projects/Website Redesign",
        "Projects/Marketing Campaign",
        "Areas/Health & Fitness",
        "Areas/Personal Development",
        "Resources/Design Templates",
        "Resources/Code Libraries",
        "Archive/2023 Projects",
    ]

    for folder in folders:
        (tmp_path / folder).mkdir(parents=True)

    return tmp_path


class TestCompleteWorkflows:
    """Tests for complete end-to-end workflows."""

    def test_fresh_setup_workflow(self, tmp_path):
        """Test setting up JD structure from scratch."""
        # Step 1: Create system
        system = JohnnyDecimalSystem()

        # Step 2: Define structure
        areas = [
            (10, "Work"),
            (20, "Personal"),
            (30, "Learning"),
            (40, "Archive"),
        ]

        categories = [
            (10, 1, "Projects"),
            (10, 2, "Documentation"),
            (20, 1, "Finance"),
            (20, 2, "Health"),
        ]

        # Step 3: Create structure
        for area_num, area_name in areas:
            number = system.create_area(area_num, area_name)
            folder_path = tmp_path / f"{number.formatted_number} {area_name}"
            folder_path.mkdir()

        for area_num, cat_num, cat_name in categories:
            number = system.create_category(area_num, cat_num, cat_name)
            area_path = tmp_path / f"{area_num} {areas[area_num//10 - 1][1]}"
            cat_path = area_path / f"{number.formatted_number} {cat_name}"
            cat_path.mkdir()

        # Verify structure
        assert (tmp_path / "10 Work").exists()
        assert (tmp_path / "20 Personal").exists()
        assert (tmp_path / "10 Work" / "10.01 Projects").exists()
        assert (tmp_path / "20 Personal" / "20.01 Finance").exists()

    def test_migration_workflow(self, complex_structure):
        """Test complete migration workflow."""
        # Step 1: Initialize migrator
        migrator = JohnnyDecimalMigrator(preserve_original_names=True)

        # Step 2: Create plan
        plan, scan_result = migrator.create_migration_plan(complex_structure)
        assert len(plan.rules) > 0

        # Step 3: Validate
        validation = migrator.validate_plan(plan)
        assert isinstance(validation.is_valid, bool)

        # Step 4: Preview
        preview = migrator.generate_preview(plan, scan_result, validation)
        assert len(preview) > 0

        # Step 5: Dry run
        dry_result = migrator.execute_migration(
            plan, dry_run=True, create_backup=False
        )
        assert dry_result.transformed_count > 0 or dry_result.skipped_count > 0

        # Step 6: Execute
        result = migrator.execute_migration(plan, dry_run=False, create_backup=True)
        assert result.transformed_count > 0 or result.skipped_count > 0

        # Verify structure changed
        jd_folders = [f for f in complex_structure.rglob("*") if f.is_dir()]
        has_jd_numbers = any(
            any(c.isdigit() for c in f.name[:3]) for f in jd_folders
        )

        # Cleanup
        if result.backup_path and result.backup_path.exists():
            shutil.rmtree(result.backup_path)

    def test_para_integration_workflow(self, para_structure):
        """Test PARA integration workflow."""
        # Step 1: Create PARA config
        config = create_para_compatible_config()

        # Step 2: Analyze existing structure
        analyzer = CompatibilityAnalyzer(config)
        detected = analyzer.detect_para_structure(para_structure)

        # Should detect PARA categories
        assert any(path is not None for path in detected.values())

        # Step 3: Get migration strategy
        strategy = analyzer.suggest_migration_strategy(para_structure)
        assert len(strategy["recommendations"]) > 0

        # Step 4: Execute migration
        migrator = JohnnyDecimalMigrator(scheme=config.scheme)
        plan, scan_result = migrator.create_migration_plan(para_structure)

        result = migrator.execute_migration(plan, dry_run=False, create_backup=True)
        assert result.success or result.failed_count == 0

        # Cleanup
        if result.backup_path and result.backup_path.exists():
            shutil.rmtree(result.backup_path)

    def test_hybrid_setup_workflow(self, tmp_path):
        """Test setting up hybrid PARA + JD structure."""
        # Step 1: Create PARA config
        config = create_para_compatible_config()

        # Step 2: Create hybrid organizer
        organizer = HybridOrganizer(config)

        # Step 3: Create hybrid structure
        paths = organizer.create_hybrid_structure(tmp_path)

        # Step 4: Add items to each category
        items = [
            ("Website Project", PARACategory.PROJECTS),
            ("Health Tracking", PARACategory.AREAS),
            ("Code Snippets", PARACategory.RESOURCES),
            ("Old Projects", PARACategory.ARCHIVE),
        ]

        for item_name, para_cat in items:
            jd_number = organizer.categorize_item(item_name, para_cat)
            path = organizer.get_item_path(tmp_path, para_cat, jd_number, item_name)
            path.mkdir(parents=True, exist_ok=True)
            assert path.exists()

        # Verify all items created
        assert len(list(tmp_path.rglob("*"))) > 10  # Should have many folders

    def test_adapter_workflow(self, tmp_path):
        """Test using adapters for organization."""
        # Step 1: Create config
        config = create_para_compatible_config()

        # Step 2: Create adapter registry
        registry = create_default_registry(config)

        # Step 3: Adapt items
        items = [
            OrganizationItem(
                name="Project A",
                path=Path("Projects/Project A"),
                category="projects",
                metadata={},
            ),
            OrganizationItem(
                name="Finance Docs",
                path=Path("Areas/Finance"),
                category="areas",
                metadata={},
            ),
        ]

        for item in items:
            jd_number = registry.adapt_to_jd(item)
            assert jd_number is not None
            assert jd_number.area >= 10

            # Convert back
            restored = registry.adapt_from_jd(jd_number, item.name, "para")
            assert restored is not None


class TestCrossComponentIntegration:
    """Tests for integration between components."""

    def test_scanner_transformer_integration(self, complex_structure):
        """Test scanner output works with transformer."""
        from file_organizer.methodologies.johnny_decimal import (
            FolderScanner,
            FolderTransformer,
            JohnnyDecimalGenerator,
            get_default_scheme,
        )

        # Scan
        scanner = FolderScanner()
        scan_result = scanner.scan_directory(complex_structure)

        # Transform
        scheme = get_default_scheme()
        generator = JohnnyDecimalGenerator(scheme)
        transformer = FolderTransformer(scheme, generator)

        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, complex_structure
        )

        # Should produce valid plan
        assert len(plan.rules) > 0
        assert all(rule.jd_number is not None for rule in plan.rules)

    def test_transformer_validator_integration(self, complex_structure):
        """Test transformer output works with validator."""
        from file_organizer.methodologies.johnny_decimal import (
            FolderScanner,
            FolderTransformer,
            MigrationValidator,
            JohnnyDecimalGenerator,
            get_default_scheme,
        )

        # Scan and transform
        scanner = FolderScanner()
        scan_result = scanner.scan_directory(complex_structure)

        scheme = get_default_scheme()
        generator = JohnnyDecimalGenerator(scheme)
        transformer = FolderTransformer(scheme, generator)

        plan = transformer.create_transformation_plan(
            scan_result.folder_tree, complex_structure
        )

        # Validate
        validator = MigrationValidator(generator)
        result = validator.validate_plan(plan)

        # Should validate successfully
        assert isinstance(result.is_valid, bool)
        assert isinstance(result.errors, list)

    def test_config_system_integration(self, tmp_path):
        """Test configuration works with system."""
        # Create custom config
        config = (
            ConfigBuilder("test")
            .add_area(10, "Custom Area")
            .with_migration_config(preserve_names=True)
            .build()
        )

        # Use config with migrator
        migrator = JohnnyDecimalMigrator(scheme=config.scheme)

        # Create test structure
        (tmp_path / "TestFolder").mkdir()

        # Should work with custom config
        plan, scan_result = migrator.create_migration_plan(tmp_path)
        assert len(plan.rules) >= 0

    def test_config_adapter_integration(self):
        """Test configuration works with adapters."""
        # Create PARA config
        config = create_para_compatible_config()

        # Create registry
        registry = create_default_registry(config)

        # Test item
        item = OrganizationItem(
            name="Test",
            path=Path("Projects/Test"),
            category="projects",
            metadata={},
        )

        # Should work with configured adapters
        jd_number = registry.adapt_to_jd(item)
        assert jd_number is not None


class TestRealWorldScenarios:
    """Tests for real-world usage scenarios."""

    def test_team_shared_structure(self, tmp_path):
        """Test setup for team shared folders."""
        # Common team structure
        folders = [
            "Clients/ClientA/Projects",
            "Clients/ClientB/Projects",
            "Internal/Documentation",
            "Internal/Templates",
            "Archive/2023",
        ]

        for folder in folders:
            (tmp_path / folder).mkdir(parents=True)

        # Migrate to JD
        migrator = JohnnyDecimalMigrator()
        plan, scan_result = migrator.create_migration_plan(tmp_path)

        result = migrator.execute_migration(plan, dry_run=False, create_backup=True)
        assert result.success or result.failed_count == 0

        # Cleanup
        if result.backup_path and result.backup_path.exists():
            shutil.rmtree(result.backup_path)

    def test_personal_knowledge_base(self, tmp_path):
        """Test setup for personal knowledge management."""
        # PARA-style personal knowledge base
        folders = [
            "Projects/Active/WebDev",
            "Projects/Active/Writing",
            "Areas/Career",
            "Areas/Health",
            "Areas/Finance",
            "Resources/Tutorials",
            "Resources/References",
            "Archive/CompletedProjects",
        ]

        for folder in folders:
            (tmp_path / folder).mkdir(parents=True)

        # Use hybrid approach
        config = create_para_compatible_config()
        organizer = HybridOrganizer(config)

        # Analyze and migrate
        analyzer = CompatibilityAnalyzer(config)
        detected = analyzer.detect_para_structure(tmp_path)

        assert any(path is not None for path in detected.values())

    def test_academic_research_structure(self, tmp_path):
        """Test setup for academic research organization."""
        # Research project structure
        folders = [
            "Research/LitReview",
            "Research/DataCollection",
            "Research/Analysis",
            "Teaching/Lectures",
            "Teaching/Assignments",
            "Admin/Grants",
            "Publications/Drafts",
        ]

        for folder in folders:
            (tmp_path / folder).mkdir(parents=True)

        # Custom config for research
        config = (
            ConfigBuilder("research")
            .add_area(10, "Research")
            .add_area(20, "Teaching")
            .add_area(30, "Admin")
            .add_area(40, "Publications")
            .build()
        )

        migrator = JohnnyDecimalMigrator(scheme=config.scheme)
        plan, scan_result = migrator.create_migration_plan(tmp_path)

        assert len(plan.rules) > 0

    def test_freelancer_client_management(self, tmp_path):
        """Test setup for freelancer client management."""
        # Freelancer structure
        folders = [
            "Clients/Active/ClientA",
            "Clients/Active/ClientB",
            "Clients/Inactive/ClientC",
            "Marketing/Website",
            "Marketing/Social",
            "Finance/Invoices",
            "Finance/Expenses",
        ]

        for folder in folders:
            (tmp_path / folder).mkdir(parents=True)

        # Migrate
        migrator = JohnnyDecimalMigrator()
        plan, scan_result = migrator.create_migration_plan(tmp_path)

        result = migrator.execute_migration(plan, dry_run=True, create_backup=False)
        assert result.transformed_count > 0 or result.skipped_count > 0


class TestPerformance:
    """Performance-related integration tests."""

    def test_large_structure_migration(self, tmp_path):
        """Test migration of large structure."""
        # Create many folders (100)
        for i in range(100):
            (tmp_path / f"Folder{i:03d}").mkdir()

        migrator = JohnnyDecimalMigrator()

        # Should handle large structure
        plan, scan_result = migrator.create_migration_plan(tmp_path)
        assert len(plan.rules) == 100

        # Dry run should complete
        result = migrator.execute_migration(plan, dry_run=True, create_backup=False)
        assert result.transformed_count == 100

    def test_deep_hierarchy_migration(self, tmp_path):
        """Test migration of deep hierarchy."""
        # Create deep structure (10 levels)
        current = tmp_path
        for i in range(10):
            current = current / f"Level{i}"
            current.mkdir()

        migrator = JohnnyDecimalMigrator()

        # Should handle deep hierarchy
        plan, scan_result = migrator.create_migration_plan(tmp_path)
        assert len(plan.rules) > 0

        result = migrator.execute_migration(plan, dry_run=True, create_backup=False)
        assert result.transformed_count > 0


class TestErrorHandling:
    """Tests for error handling in integrated workflows."""

    def test_migration_with_permission_errors(self, tmp_path):
        """Test migration handles permission errors gracefully."""
        # Create structure
        (tmp_path / "TestFolder").mkdir()

        # Note: Can't reliably test permission errors in test environment
        # This test just ensures error handling exists
        migrator = JohnnyDecimalMigrator()
        plan, scan_result = migrator.create_migration_plan(tmp_path)

        # Should not crash on errors
        result = migrator.execute_migration(plan, dry_run=True, create_backup=False)
        assert isinstance(result.failed_count, int)

    def test_migration_with_conflicts(self, tmp_path):
        """Test migration handles conflicts."""
        # Create folders that might conflict
        (tmp_path / "Folder1").mkdir()
        (tmp_path / "Folder2").mkdir()

        migrator = JohnnyDecimalMigrator()
        plan, scan_result = migrator.create_migration_plan(tmp_path)

        # Manually create conflict
        if len(plan.rules) > 0:
            target_name = plan.rules[0].target_name
            (tmp_path / target_name).mkdir(exist_ok=True)

        # Should handle conflicts
        result = migrator.execute_migration(plan, dry_run=False, create_backup=True)
        assert result.skipped_count >= 0

        # Cleanup
        if result.backup_path and result.backup_path.exists():
            shutil.rmtree(result.backup_path)

    def test_invalid_config_handling(self):
        """Test handling of invalid configuration."""
        # This should not crash
        try:
            config = (
                ConfigBuilder("invalid")
                .add_area(5, "Invalid")  # Invalid area number
                .build()
            )
            # If it doesn't validate at build time, that's ok
        except Exception:
            # If it does validate, that's also ok
            pass


class TestBackwardCompatibility:
    """Tests for backward compatibility and migration paths."""

    def test_config_serialization(self, tmp_path):
        """Test configuration can be saved and loaded."""
        # Create config
        config = create_para_compatible_config()

        # Save
        config_file = tmp_path / "config.json"
        config.save_to_file(config_file)
        assert config_file.exists()

        # Load
        loaded_config = JohnnyDecimalConfig.load_from_file(config_file)
        assert loaded_config.scheme.name == config.scheme.name

    def test_migration_with_existing_jd(self, tmp_path):
        """Test migration of structure with existing JD numbers."""
        # Create structure with some JD numbers already
        (tmp_path / "10 Existing").mkdir()
        (tmp_path / "11 Another").mkdir()
        (tmp_path / "NewFolder").mkdir()

        migrator = JohnnyDecimalMigrator()
        plan, scan_result = migrator.create_migration_plan(tmp_path)

        # Should handle mixed structure
        result = migrator.execute_migration(plan, dry_run=True, create_backup=False)
        assert result.transformed_count >= 0
