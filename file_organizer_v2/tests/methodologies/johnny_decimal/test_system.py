"""
Tests for Johnny Decimal system module.

Tests system orchestration, configuration, and integration.
"""

import json
from pathlib import Path

import pytest

from file_organizer.methodologies.johnny_decimal.categories import (
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalNumber,
    NumberingScheme,
)
from file_organizer.methodologies.johnny_decimal.numbering import (
    InvalidNumberError,
)
from file_organizer.methodologies.johnny_decimal.system import (
    JohnnyDecimalSystem,
)


@pytest.fixture
def test_scheme():
    """Create a test numbering scheme."""
    scheme = NumberingScheme(name="Test", description="Test scheme")

    area = AreaDefinition(
        area_range_start=10,
        area_range_end=19,
        name="Finance",
        description="Financial matters",
        keywords=["budget", "invoice"],
    )
    scheme.add_area(area)

    category = CategoryDefinition(
        area=10,
        category=1,
        name="Budgets",
        description="Budget documents",
        keywords=["budget"],
    )
    scheme.add_category(category)

    return scheme


@pytest.fixture
def system(test_scheme):
    """Create a Johnny Decimal system."""
    return JohnnyDecimalSystem(scheme=test_scheme)


@pytest.fixture
def temp_dir(tmp_path):
    """Create a temporary directory for testing."""
    test_dir = tmp_path / "test_files"
    test_dir.mkdir()
    return test_dir


class TestJohnnyDecimalSystem:
    """Test JohnnyDecimalSystem class."""

    def test_initialization_default_scheme(self):
        """Test initializing with default scheme."""
        system = JohnnyDecimalSystem()
        assert system.scheme is not None
        assert len(system.scheme.areas) > 0

    def test_initialization_custom_scheme(self, test_scheme):
        """Test initializing with custom scheme."""
        system = JohnnyDecimalSystem(scheme=test_scheme)
        assert system.scheme == test_scheme

    def test_extract_number_from_path_area(self, system):
        """Test extracting area number from path."""
        path = Path("/test/10 Finance")
        number = system._extract_number_from_path(path)

        assert number is not None
        assert number.area == 10
        assert number.name == "Finance"

    def test_extract_number_from_path_category(self, system):
        """Test extracting category number from path."""
        path = Path("/test/10.01 Budgets")
        number = system._extract_number_from_path(path)

        assert number is not None
        assert number.area == 10
        assert number.category == 1
        assert number.name == "Budgets"

    def test_extract_number_from_path_id(self, system):
        """Test extracting ID number from path."""
        path = Path("/test/10.01.005 Q1 Budget.xlsx")
        number = system._extract_number_from_path(path)

        assert number is not None
        assert number.area == 10
        assert number.category == 1
        assert number.item_id == 5
        assert number.name == "Q1 Budget"

    def test_extract_number_from_path_no_number(self, system):
        """Test extracting from path with no number."""
        path = Path("/test/random_file.txt")
        number = system._extract_number_from_path(path)

        assert number is None

    def test_initialize_from_directory(self, system, temp_dir):
        """Test initializing from directory."""
        # Create test files with Johnny Decimal names
        (temp_dir / "10 Finance").mkdir()
        (temp_dir / "10.01 Budgets").mkdir()
        (temp_dir / "10.01.001 Q1 Budget.xlsx").touch()

        system.initialize_from_directory(temp_dir)

        assert system._initialized
        assert "10" in system.generator._used_numbers
        assert "10.01" in system.generator._used_numbers
        assert "10.01.001" in system.generator._used_numbers

    def test_initialize_from_nonexistent_directory(self, system):
        """Test initializing from non-existent directory."""
        with pytest.raises(ValueError, match="Directory does not exist"):
            system.initialize_from_directory(Path("/nonexistent"))

    def test_assign_number_to_file(self, system, temp_dir):
        """Test assigning number to a file."""
        file_path = temp_dir / "budget.xlsx"
        file_path.touch()

        result = system.assign_number_to_file(
            file_path=file_path,
            content="This is a budget document",
        )

        assert result.number is not None
        assert result.confidence > 0
        assert len(result.reasons) > 0
        assert not result.has_conflicts

    def test_assign_number_with_preferred(self, system, temp_dir):
        """Test assigning with preferred number."""
        file_path = temp_dir / "test.txt"
        file_path.touch()

        preferred = JohnnyDecimalNumber(area=10, category=5)
        result = system.assign_number_to_file(
            file_path=file_path,
            preferred_number=preferred,
        )

        assert result.number == preferred
        assert result.confidence > 0.9

    def test_assign_number_conflict_resolution(self, system, temp_dir):
        """Test assigning number with conflict resolution."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        file1.touch()
        file2.touch()

        preferred = JohnnyDecimalNumber(area=10, category=1)

        # Assign to first file
        system.assign_number_to_file(
            file_path=file1,
            preferred_number=preferred,
        )

        # Try to assign same number to second file - should resolve
        result = system.assign_number_to_file(
            file_path=file2,
            preferred_number=preferred,
        )

        assert result.number != preferred
        assert len(result.conflicts) > 0 or result.number.category != preferred.category

    def test_validate_number_assignment(self, system, temp_dir):
        """Test validating a number assignment."""
        file_path = temp_dir / "test.txt"
        file_path.touch()

        number = JohnnyDecimalNumber(area=10, category=1)
        result = system.validate_number_assignment(number, file_path)

        assert result.confidence == 1.0
        assert result.metadata["validation_only"]

    def test_validate_used_number(self, system, temp_dir):
        """Test validating an already used number."""
        file1 = temp_dir / "file1.txt"
        file2 = temp_dir / "file2.txt"
        file1.touch()
        file2.touch()

        number = JohnnyDecimalNumber(area=10, category=1)

        # Use the number
        system.assign_number_to_file(file_path=file1, preferred_number=number)

        # Try to validate for another file
        result = system.validate_number_assignment(number, file2)

        assert result.confidence == 0.0
        assert len(result.conflicts) > 0

    def test_renumber_file(self, system, temp_dir):
        """Test renumbering a file."""
        file_path = temp_dir / "test.txt"
        file_path.touch()

        old_number = JohnnyDecimalNumber(area=10, category=1)
        new_number = JohnnyDecimalNumber(area=10, category=2)

        # Assign initial number
        system.assign_number_to_file(file_path=file_path, preferred_number=old_number)

        # Renumber
        result = system.renumber_file(old_number, new_number, file_path)

        assert result.number == new_number
        assert "10.01" not in system.generator._used_numbers
        assert "10.02" in system.generator._used_numbers

    def test_renumber_nonexistent_number(self, system, temp_dir):
        """Test renumbering a non-registered number."""
        file_path = temp_dir / "test.txt"
        file_path.touch()

        old_number = JohnnyDecimalNumber(area=10, category=1)
        new_number = JohnnyDecimalNumber(area=10, category=2)

        with pytest.raises(InvalidNumberError, match="not registered"):
            system.renumber_file(old_number, new_number, file_path)

    def test_get_area_summary(self, system):
        """Test getting area summary."""
        # Register some numbers in area 10
        system.generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=1),
            Path("/test/file1.txt"),
        )
        system.generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=2),
            Path("/test/file2.txt"),
        )

        summary = system.get_area_summary(10)

        assert summary["area"] == 10
        assert summary["name"] == "Finance"
        assert summary["used_numbers"] == 2
        assert "10.01" in summary["numbers"]
        assert "10.02" in summary["numbers"]

    def test_get_all_areas_summary(self, system):
        """Test getting all areas summary."""
        summaries = system.get_all_areas_summary()

        assert len(summaries) > 0
        assert all("area" in s for s in summaries)
        assert all("name" in s for s in summaries)

    def test_get_usage_report(self, system):
        """Test getting usage report."""
        # Register some numbers
        system.generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=1),
            Path("/test/file.txt"),
        )

        report = system.get_usage_report()

        assert "statistics" in report
        assert "areas" in report
        assert "scheme_name" in report
        assert report["scheme_name"] == "Test"

    def test_add_custom_area(self, system):
        """Test adding custom area."""
        custom_area = AreaDefinition(
            area_range_start=30,
            area_range_end=39,
            name="Custom Area",
            description="Custom description",
        )

        system.add_custom_area(custom_area)

        assert system.scheme.get_area(30) == custom_area
        assert system.scheme.get_area(35) == custom_area

    def test_add_custom_category(self, system):
        """Test adding custom category."""
        custom_category = CategoryDefinition(
            area=10,
            category=5,
            name="Custom Category",
            description="Custom description",
        )

        system.add_custom_category(custom_category)

        assert system.scheme.get_category(10, 5) == custom_category

    def test_reserve_number_range(self, system):
        """Test reserving a number range."""
        start = JohnnyDecimalNumber(area=10, category=10)
        end = JohnnyDecimalNumber(area=10, category=15)

        system.reserve_number_range(start, end)

        # Check that numbers in range are reserved
        for cat in range(10, 16):
            num = JohnnyDecimalNumber(area=10, category=cat)
            assert system.scheme.is_number_reserved(num)

    def test_reserve_number_range_different_levels(self, system):
        """Test reserving range with different levels."""
        start = JohnnyDecimalNumber(area=10)
        end = JohnnyDecimalNumber(area=10, category=5)

        with pytest.raises(ValueError, match="same hierarchy level"):
            system.reserve_number_range(start, end)

    def test_clear_all_registrations(self, system):
        """Test clearing all registrations."""
        system.generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=1),
            Path("/test/file.txt"),
        )

        assert len(system.generator._used_numbers) > 0

        system.clear_all_registrations()

        assert len(system.generator._used_numbers) == 0
        assert not system._initialized


class TestConfiguration:
    """Test configuration save/load."""

    def test_save_configuration(self, system, temp_dir):
        """Test saving configuration."""
        config_path = temp_dir / "config.json"

        # Register some numbers
        system.generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=1),
            Path("/test/file.txt"),
        )

        system.save_configuration(config_path)

        assert config_path.exists()

        # Verify content
        with open(config_path) as f:
            config = json.load(f)

        assert "scheme" in config
        assert "used_numbers" in config
        assert "10.01" in config["used_numbers"]

    def test_load_configuration(self, system, temp_dir):
        """Test loading configuration."""
        config_path = temp_dir / "config.json"

        # Create config file
        config = {
            "scheme": {
                "name": "Test",
                "description": "Test",
                "allow_gaps": True,
                "auto_increment": True,
                "reserved_numbers": ["15.01", "15.02"],
            },
            "used_numbers": {
                "10.01": "/test/file1.txt",
                "10.02": "/test/file2.txt",
            },
            "statistics": {},
        }

        with open(config_path, "w") as f:
            json.dump(config, f)

        # Load config
        system.load_configuration(config_path)

        assert system._initialized
        assert "10.01" in system.generator._used_numbers
        assert "10.02" in system.generator._used_numbers
        assert "15.01" in system.scheme.reserved_numbers

    def test_save_load_roundtrip(self, system, temp_dir):
        """Test save and load roundtrip."""
        config_path = temp_dir / "config.json"

        # Register some numbers
        num1 = JohnnyDecimalNumber(area=10, category=1, name="Test1")
        num2 = JohnnyDecimalNumber(area=10, category=2, name="Test2")

        system.generator.register_existing_number(num1, Path("/test/file1.txt"))
        system.generator.register_existing_number(num2, Path("/test/file2.txt"))

        # Reserve a number
        reserved = JohnnyDecimalNumber(area=15, category=1)
        system.scheme.reserve_number(reserved)

        # Save
        system.save_configuration(config_path)

        # Create new system and load
        new_system = JohnnyDecimalSystem(scheme=system.scheme)
        new_system.load_configuration(config_path)

        # Verify
        assert "10.01" in new_system.generator._used_numbers
        assert "10.02" in new_system.generator._used_numbers
        assert "15.01" in new_system.scheme.reserved_numbers

    def test_load_nonexistent_file(self, system):
        """Test loading from non-existent file."""
        with pytest.raises(FileNotFoundError):
            system.load_configuration(Path("/nonexistent/config.json"))


class TestIntegrationScenarios:
    """Test complete integration scenarios."""

    def test_organize_directory(self, system, temp_dir):
        """Test organizing a directory of files."""
        # Create test files
        files = [
            "budget-2024.xlsx",
            "invoice-123.pdf",
            "expense-report.docx",
        ]

        for filename in files:
            (temp_dir / filename).touch()

        # Initialize from directory
        system.initialize_from_directory(temp_dir)

        # Assign numbers to new files
        new_file = temp_dir / "new-budget.xlsx"
        new_file.touch()

        result = system.assign_number_to_file(
            file_path=new_file,
            content="Budget document for Q2 2024",
        )

        assert result.number is not None
        assert not result.has_conflicts

    def test_migration_scenario(self, system, temp_dir):
        """Test migrating files to Johnny Decimal system."""
        # Create unorganized files
        files = {
            "random1.txt": "budget information",
            "random2.pdf": "invoice document",
            "random3.docx": "expense report",
        }

        results = []
        for filename, content in files.items():
            file_path = temp_dir / filename
            file_path.touch()

            result = system.assign_number_to_file(
                file_path=file_path,
                content=content,
            )
            results.append(result)

        # All should have numbers
        assert all(r.number is not None for r in results)

        # Finance area (10-19) should be used for these files
        assert all(r.number.area in range(10, 20) for r in results)

    def test_concurrent_numbering(self, system, temp_dir):
        """Test handling concurrent number assignments."""
        files = [temp_dir / f"file{i}.txt" for i in range(10)]
        for f in files:
            f.touch()

        results = []
        for file_path in files:
            result = system.assign_number_to_file(file_path=file_path)
            results.append(result)

        # All should have unique numbers
        numbers = [r.number.formatted_number for r in results]
        assert len(numbers) == len(set(numbers))

    def test_hierarchical_organization(self, system, temp_dir):
        """Test organizing files hierarchically."""
        # Create area-level folder
        area_result = system.assign_number_to_file(
            file_path=temp_dir / "Finance",
            preferred_number=JohnnyDecimalNumber(area=10, name="Finance"),
        )

        # Create category-level folders
        cat_result = system.assign_number_to_file(
            file_path=temp_dir / "Budgets",
            preferred_number=JohnnyDecimalNumber(area=10, category=1, name="Budgets"),
        )

        # Create file-level items
        file_result = system.assign_number_to_file(
            file_path=temp_dir / "Q1-Budget.xlsx",
            preferred_number=JohnnyDecimalNumber(
                area=10, category=1, item_id=1, name="Q1 Budget"
            ),
        )

        assert area_result.number.level.value == "area"
        assert cat_result.number.level.value == "category"
        assert file_result.number.level.value == "id"
