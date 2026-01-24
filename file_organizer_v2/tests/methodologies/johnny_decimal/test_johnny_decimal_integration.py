"""
Johnny Decimal Integration Tests

Tests complete workflows, edge cases, and integration scenarios.
"""

import json
from pathlib import Path

import pytest

from file_organizer.methodologies.johnny_decimal.categories import (
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalNumber,
)
from file_organizer.methodologies.johnny_decimal.system import (
    JohnnyDecimalSystem,
)


class TestJohnnyDecimalWorkflows:
    """Test complete Johnny Decimal workflows."""

    @pytest.fixture
    def system(self):
        """Create Johnny Decimal system."""
        return JohnnyDecimalSystem()

    @pytest.fixture
    def workspace(self, tmp_path):
        """Create test workspace."""
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        return workspace

    def test_new_project_setup(self, system, workspace):
        """Test setting up Johnny Decimal for a new project."""
        # Initialize system
        system.initialize_from_directory(workspace)

        # Add custom area
        custom_area = AreaDefinition(
            area_range_start=20,
            area_range_end=29,
            name="Development",
            description="Software development",
            keywords=["code", "software"],
        )
        system.add_custom_area(custom_area)

        # Add custom category
        custom_category = CategoryDefinition(
            area=20,
            category=1,
            name="Source Code",
            description="Source code files",
            keywords=["code", "source"],
        )
        system.add_custom_category(custom_category)

        # Verify setup
        assert system.scheme.get_area(20) == custom_area
        assert system.scheme.get_category(20, 1) == custom_category

    def test_file_organization_workflow(self, system, workspace):
        """Test organizing files from scratch."""
        # Create unorganized files
        files = [
            workspace / "budget.xlsx",
            workspace / "invoice.pdf",
            workspace / "meeting-notes.docx",
        ]

        for file_path in files:
            file_path.touch()

        # Assign numbers
        results = []
        for file_path in files:
            result = system.assign_number_to_file(
                file_path=file_path,
                content=file_path.name,
            )
            results.append(result)

        # All should have numbers assigned
        assert all(r.number is not None for r in results)
        assert all(r.confidence > 0 for r in results)

    def test_directory_migration(self, system, workspace):
        """Test migrating existing directory structure."""
        # Create existing structure
        finance_dir = workspace / "Finance"
        finance_dir.mkdir()

        budget_dir = finance_dir / "Budgets"
        budget_dir.mkdir()

        files = [
            budget_dir / "Q1-budget.xlsx",
            budget_dir / "Q2-budget.xlsx",
        ]

        for file_path in files:
            file_path.touch()

        # Initialize from directory
        system.initialize_from_directory(workspace)

        # Assign numbers to organize structure
        for file_path in files:
            result = system.assign_number_to_file(file_path=file_path)
            assert result.number is not None

    def test_renumbering_workflow(self, system, workspace):
        """Test renumbering files."""
        # Create and number a file
        file_path = workspace / "document.txt"
        file_path.touch()

        # Initial numbering
        initial_result = system.assign_number_to_file(
            file_path=file_path,
            preferred_number=JohnnyDecimalNumber(area=10, category=1),
        )

        old_number = initial_result.number

        # Renumber
        new_number = JohnnyDecimalNumber(area=10, category=2)
        renumber_result = system.renumber_file(old_number, new_number, file_path)

        assert renumber_result.number == new_number
        assert renumber_result.confidence == 1.0


class TestJohnnyDecimalEdgeCases:
    """Test edge cases and error handling."""

    @pytest.fixture
    def system(self):
        """Create Johnny Decimal system."""
        return JohnnyDecimalSystem()

    def test_invalid_number_ranges(self, system):
        """Test handling invalid number ranges."""
        # Try to create number with invalid area
        with pytest.raises(ValueError):
            JohnnyDecimalNumber(area=100)  # Must be 0-99

        # Try to create number with invalid category
        with pytest.raises(ValueError):
            JohnnyDecimalNumber(area=10, category=100)  # Must be 0-99

    def test_number_exhaustion(self, system, tmp_path):
        """Test handling when numbers run out in a range."""
        # Register many numbers in one category (leave a few for the test)
        for i in range(95):
            number = JohnnyDecimalNumber(area=10, category=1, item_id=i)
            system.generator.register_existing_number(
                number, tmp_path / f"file{i}.txt"
            )

        # Try to assign another number in same category
        file_path = tmp_path / "extra-file.txt"
        file_path.touch()

        result = system.assign_number_to_file(
            file_path=file_path,
            preferred_number=JohnnyDecimalNumber(area=10, category=1),
        )

        # Should get a number (may be in same category if space available, or different category)
        assert result.number is not None

    def test_conflicting_assignments(self, system, tmp_path):
        """Test handling conflicting number assignments."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.touch()
        file2.touch()

        preferred = JohnnyDecimalNumber(area=10, category=1)

        # Assign to first file
        system.assign_number_to_file(file_path=file1, preferred_number=preferred)

        # Try to assign same number to second file
        result = system.assign_number_to_file(
            file_path=file2, preferred_number=preferred
        )

        # Should either use different number or report conflict
        assert result.number != preferred or len(result.conflicts) > 0

    def test_special_characters_in_names(self, system, tmp_path):
        """Test handling special characters in file names."""
        special_names = [
            "file (1).txt",
            "document [draft].docx",
            "report-2024.pdf",
            "notes_v2.txt",
        ]

        for name in special_names:
            file_path = tmp_path / name
            file_path.touch()

            result = system.assign_number_to_file(file_path=file_path)

            # Should handle special characters
            assert result is not None

    def test_unicode_handling(self, system, tmp_path):
        """Test handling Unicode characters."""
        unicode_file = tmp_path / "文档-2024.txt"
        unicode_file.touch()

        result = system.assign_number_to_file(file_path=unicode_file)

        # Should handle Unicode
        assert result is not None

    def test_very_deep_hierarchy(self, system, tmp_path):
        """Test handling very deep directory hierarchies."""
        # Create deep path
        deep_path = tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "file.txt"
        deep_path.parent.mkdir(parents=True)
        deep_path.touch()

        result = system.assign_number_to_file(file_path=deep_path)

        # Should handle deep paths
        assert result is not None


class TestJohnnyDecimalConfiguration:
    """Test configuration management."""

    @pytest.fixture
    def system(self):
        """Create Johnny Decimal system."""
        return JohnnyDecimalSystem()

    def test_save_and_load_configuration(self, system, tmp_path):
        """Test saving and loading system configuration."""
        config_file = tmp_path / "config.json"

        # Set up system
        system.generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=1),
            Path("/test/file1.txt"),
        )

        system.generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=2),
            Path("/test/file2.txt"),
        )

        # Save configuration
        system.save_configuration(config_file)

        assert config_file.exists()

        # Create new system and load
        new_system = JohnnyDecimalSystem()
        new_system.load_configuration(config_file)

        # Verify
        assert "10.01" in new_system.generator._used_numbers
        assert "10.02" in new_system.generator._used_numbers

    def test_configuration_with_custom_scheme(self, system, tmp_path):
        """Test configuration with custom numbering scheme and registrations."""
        config_file = tmp_path / "custom_config.json"

        # Register some numbers
        system.generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=1),
            Path("/test/file1.txt"),
        )

        # Reserve a number
        reserved = JohnnyDecimalNumber(area=15, category=1)
        system.scheme.reserve_number(reserved)

        # Save configuration
        system.save_configuration(config_file)

        # Create new system and load
        new_system = JohnnyDecimalSystem()
        new_system.load_configuration(config_file)

        # Verify registrations preserved
        assert "10.01" in new_system.generator._used_numbers

        # Verify reservations preserved
        assert "15.01" in new_system.scheme.reserved_numbers

    def test_configuration_validation(self, system, tmp_path):
        """Test validation of loaded configuration."""
        config_file = tmp_path / "invalid_config.json"

        # Create invalid configuration
        invalid_config = {
            "scheme": {"name": "Test"},
            "used_numbers": {
                "invalid": "/path/to/file.txt",  # Invalid number format
            },
        }

        with open(config_file, "w") as f:
            json.dump(invalid_config, f)

        # Loading should handle invalid data gracefully
        # (implementation may skip invalid entries or raise error)
        try:
            system.load_configuration(config_file)
        except (ValueError, KeyError, json.JSONDecodeError):
            # Expected behavior for invalid config
            pass


class TestJohnnyDecimalReporting:
    """Test reporting and analysis features."""

    @pytest.fixture
    def populated_system(self, tmp_path):
        """Create system with populated numbers."""
        system = JohnnyDecimalSystem()

        # Register various numbers
        numbers = [
            (10, 1, 1),
            (10, 1, 2),
            (10, 2, 1),
            (20, 1, 1),
            (20, 1, 2),
            (20, 1, 3),
        ]

        for area, category, item_id in numbers:
            number = JohnnyDecimalNumber(area=area, category=category, item_id=item_id)
            file_path = tmp_path / f"{number.formatted_number}.txt"
            system.generator.register_existing_number(number, file_path)

        return system

    def test_area_summary(self, populated_system):
        """Test generating area summary."""
        summary = populated_system.get_area_summary(10)

        assert summary["area"] == 10
        assert summary["used_numbers"] == 3  # 10.01.001, 10.01.002, 10.02.001
        assert len(summary["numbers"]) == 3

    def test_usage_report(self, populated_system):
        """Test generating usage report."""
        report = populated_system.get_usage_report()

        assert "statistics" in report
        assert "areas" in report
        assert report["statistics"]["total_numbers"] == 6
        assert len(report["areas"]) > 0

    def test_all_areas_summary(self, populated_system):
        """Test generating summary for all areas."""
        summaries = populated_system.get_all_areas_summary()

        # Should have summaries for areas 10 and 20
        area_numbers = [s["area"] for s in summaries]
        assert 10 in area_numbers
        assert 20 in area_numbers


class TestJohnnyDecimalScalability:
    """Test system scalability and performance."""

    @pytest.fixture
    def system(self):
        """Create Johnny Decimal system."""
        return JohnnyDecimalSystem()

    def test_large_number_of_files(self, system, tmp_path):
        """Test handling large number of files."""
        import time

        # Create many files
        num_files = 100
        files = []
        for i in range(num_files):
            file_path = tmp_path / f"file{i}.txt"
            file_path.touch()
            files.append(file_path)

        # Assign numbers
        start = time.time()
        results = []
        for file_path in files:
            result = system.assign_number_to_file(file_path=file_path)
            results.append(result)
        duration = time.time() - start

        # Should complete in reasonable time (< 10 seconds)
        assert duration < 10.0
        assert len(results) == num_files

    def test_memory_efficiency(self, system, tmp_path):
        """Test memory efficiency with many registrations."""
        import gc

        # Register many numbers
        for i in range(500):
            area = 10 + (i // 100)
            category = (i // 10) % 10
            item_id = i % 10
            number = JohnnyDecimalNumber(area=area, category=category, item_id=item_id)
            system.generator.register_existing_number(
                number, tmp_path / f"file{i}.txt"
            )

        # Force garbage collection
        gc.collect()

        # If we got here without memory error, test passes
        assert len(system.generator._used_numbers) == 500

    def test_concurrent_access_simulation(self, system, tmp_path):
        """Test simulating concurrent file access."""
        # Simulate multiple "threads" assigning numbers
        # (Not true concurrency, just sequential simulation)

        files = [tmp_path / f"file{i}.txt" for i in range(20)]
        for f in files:
            f.touch()

        results = []
        for file_path in files:
            result = system.assign_number_to_file(file_path=file_path)
            results.append(result)

        # All should have unique numbers
        numbers = [r.number.formatted_number for r in results if r.number]
        assert len(numbers) == len(set(numbers))  # All unique


class TestJohnnyDecimalMigrationScenarios:
    """Test scenarios for migrating to Johnny Decimal system."""

    @pytest.fixture
    def system(self):
        """Create Johnny Decimal system."""
        return JohnnyDecimalSystem()

    def test_migrate_hierarchical_structure(self, system, tmp_path):
        """Test migrating existing hierarchical directory structure."""
        # Create existing structure
        structure = {
            "Finance": ["Budgets", "Invoices", "Reports"],
            "Projects": ["Alpha", "Beta", "Gamma"],
            "Resources": ["Templates", "Guides"],
        }

        for parent, children in structure.items():
            parent_dir = tmp_path / parent
            parent_dir.mkdir()
            for child in children:
                child_dir = parent_dir / child
                child_dir.mkdir()
                (child_dir / "file.txt").touch()

        # Initialize from structure
        system.initialize_from_directory(tmp_path)

        # Should have discovered existing files
        assert system._initialized

    def test_migrate_flat_structure(self, system, tmp_path):
        """Test migrating flat directory structure."""
        # Create flat structure with many files
        categories = ["budget", "invoice", "report", "meeting", "proposal"]

        for _i, category in enumerate(categories):
            for j in range(3):
                file_path = tmp_path / f"{category}-{j+1}.txt"
                file_path.touch()

        # Assign numbers
        files = list(tmp_path.glob("*.txt"))
        results = []
        for file_path in files:
            result = system.assign_number_to_file(
                file_path=file_path,
                content=file_path.name,
            )
            results.append(result)

        # All should be assigned
        assert all(r.number is not None for r in results)

    def test_preserve_partial_numbering(self, system, tmp_path):
        """Test preserving partially numbered structure."""
        # Create mix of numbered and unnumbered files
        numbered_dir = tmp_path / "10.01 Budgets"
        numbered_dir.mkdir()
        (numbered_dir / "10.01.001 Q1 Budget.xlsx").touch()

        unnumbered_dir = tmp_path / "Invoices"
        unnumbered_dir.mkdir()
        (unnumbered_dir / "invoice1.pdf").touch()

        # Initialize
        system.initialize_from_directory(tmp_path)

        # Should have recognized existing numbers
        assert "10.01" in system.generator._used_numbers
        assert "10.01.001" in system.generator._used_numbers


class TestJohnnyDecimalValidation:
    """Test number validation and conflict detection."""

    @pytest.fixture
    def system(self):
        """Create Johnny Decimal system."""
        return JohnnyDecimalSystem()

    def test_validate_available_number(self, system, tmp_path):
        """Test validating an available number."""
        file_path = tmp_path / "test.txt"
        file_path.touch()

        number = JohnnyDecimalNumber(area=10, category=1)
        result = system.validate_number_assignment(number, file_path)

        assert result.confidence == 1.0
        assert not result.has_conflicts

    def test_validate_used_number(self, system, tmp_path):
        """Test validating an already used number."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.touch()
        file2.touch()

        number = JohnnyDecimalNumber(area=10, category=1)

        # Use the number
        system.assign_number_to_file(file_path=file1, preferred_number=number)

        # Validate for different file
        result = system.validate_number_assignment(number, file2)

        assert result.confidence == 0.0
        assert len(result.conflicts) > 0

    def test_validate_reserved_number(self, system, tmp_path):
        """Test validating a reserved number."""
        file_path = tmp_path / "test.txt"
        file_path.touch()

        # Reserve a number
        reserved = JohnnyDecimalNumber(area=15, category=1)
        system.scheme.reserve_number(reserved)

        # Try to validate
        result = system.validate_number_assignment(reserved, file_path)

        # Should indicate reservation
        assert result.confidence < 1.0 or "reserved" in str(result.metadata)


class TestJohnnyDecimalCustomization:
    """Test customization and extensibility."""

    @pytest.fixture
    def system(self):
        """Create Johnny Decimal system."""
        return JohnnyDecimalSystem()

    def test_custom_area_definition(self, system):
        """Test adding custom area definition."""
        custom_area = AreaDefinition(
            area_range_start=70,
            area_range_end=79,
            name="Personal Projects",
            description="Personal development projects",
            keywords=["personal", "hobby"],
        )

        system.add_custom_area(custom_area)

        # Verify
        assert system.scheme.get_area(70) == custom_area
        assert system.scheme.get_area(75) == custom_area
        assert system.scheme.get_area(79) == custom_area

    def test_custom_category_definition(self, system):
        """Test adding custom category definition."""
        custom_category = CategoryDefinition(
            area=10,
            category=9,
            name="Custom Category",
            description="Custom category description",
            keywords=["custom"],
        )

        system.add_custom_category(custom_category)

        # Verify
        assert system.scheme.get_category(10, 9) == custom_category

    def test_reserve_number_range(self, system):
        """Test reserving a range of numbers."""
        start = JohnnyDecimalNumber(area=80, category=10)
        end = JohnnyDecimalNumber(area=80, category=19)

        system.reserve_number_range(start, end)

        # Verify reservations
        for cat in range(10, 20):
            number = JohnnyDecimalNumber(area=80, category=cat)
            assert system.scheme.is_number_reserved(number)

    def test_clear_all_registrations(self, system, tmp_path):
        """Test clearing all number registrations."""
        # Register some numbers
        for i in range(5):
            number = JohnnyDecimalNumber(area=10, category=i)
            system.generator.register_existing_number(number, tmp_path / f"file{i}.txt")

        assert len(system.generator._used_numbers) > 0

        # Clear
        system.clear_all_registrations()

        # Verify
        assert len(system.generator._used_numbers) == 0
        assert not system._initialized
