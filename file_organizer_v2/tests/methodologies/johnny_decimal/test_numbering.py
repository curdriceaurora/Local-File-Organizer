"""
Tests for Johnny Decimal numbering module.

Tests number generation, validation, and conflict resolution.
"""

import pytest
from pathlib import Path

from file_organizer.methodologies.johnny_decimal.categories import (
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalNumber,
    NumberingScheme,
    get_default_scheme,
)
from file_organizer.methodologies.johnny_decimal.numbering import (
    JohnnyDecimalGenerator,
    NumberConflictError,
    InvalidNumberError,
)


@pytest.fixture
def test_scheme():
    """Create a test numbering scheme."""
    scheme = NumberingScheme(name="Test", description="Test scheme")

    # Add test areas
    area1 = AreaDefinition(
        area_range_start=10,
        area_range_end=19,
        name="Finance",
        description="Financial matters",
        keywords=["budget", "invoice", "expense"],
    )
    area2 = AreaDefinition(
        area_range_start=20,
        area_range_end=29,
        name="Marketing",
        description="Marketing materials",
        keywords=["campaign", "promotion", "brand"],
    )

    scheme.add_area(area1)
    scheme.add_area(area2)

    # Add test categories
    cat1 = CategoryDefinition(
        area=10,
        category=1,
        name="Budgets",
        description="Budget documents",
        keywords=["budget", "forecast"],
        patterns=["budget-*"],
    )
    cat2 = CategoryDefinition(
        area=10,
        category=2,
        name="Invoices",
        description="Invoice documents",
        keywords=["invoice"],
        patterns=["invoice-*"],
    )

    scheme.add_category(cat1)
    scheme.add_category(cat2)

    return scheme


@pytest.fixture
def generator(test_scheme):
    """Create a generator with test scheme."""
    return JohnnyDecimalGenerator(test_scheme)


class TestJohnnyDecimalGenerator:
    """Test JohnnyDecimalGenerator class."""

    def test_initialization(self, test_scheme):
        """Test generator initialization."""
        gen = JohnnyDecimalGenerator(test_scheme)
        assert gen.scheme == test_scheme
        assert len(gen._used_numbers) == 0

    def test_register_existing_number(self, generator):
        """Test registering an existing number."""
        number = JohnnyDecimalNumber(area=10, category=1)
        file_path = Path("/test/file.txt")

        generator.register_existing_number(number, file_path)

        assert "10.01" in generator._used_numbers
        assert generator._number_mappings["10.01"] == file_path

    def test_register_duplicate_number(self, generator):
        """Test that registering duplicate number raises error."""
        number = JohnnyDecimalNumber(area=10, category=1)
        file1 = Path("/test/file1.txt")
        file2 = Path("/test/file2.txt")

        generator.register_existing_number(number, file1)

        with pytest.raises(NumberConflictError, match="already registered"):
            generator.register_existing_number(number, file2)

    def test_is_number_available(self, generator):
        """Test checking number availability."""
        number = JohnnyDecimalNumber(area=10, category=1)
        assert generator.is_number_available(number)

        generator.register_existing_number(number, Path("/test/file.txt"))
        assert not generator.is_number_available(number)

    def test_get_next_available_area(self, generator):
        """Test getting next available area."""
        area = generator.get_next_available_area()
        assert area in [10, 20]  # Should be one of the defined areas

    def test_get_next_available_area_preferred(self, generator):
        """Test getting area with preference."""
        area = generator.get_next_available_area(preferred_area=20)
        assert area == 20

    def test_get_next_available_category(self, generator):
        """Test getting next available category."""
        category = generator.get_next_available_category(area=10)
        assert 0 <= category <= 99

    def test_get_next_available_category_with_used(self, generator):
        """Test getting category when some are used."""
        # Register some categories
        for i in range(5):
            num = JohnnyDecimalNumber(area=10, category=i)
            generator.register_existing_number(num, Path(f"/test/file{i}.txt"))

        # Next available should be 5
        category = generator.get_next_available_category(area=10)
        assert category == 5

    def test_get_next_available_id(self, generator):
        """Test getting next available ID."""
        item_id = generator.get_next_available_id(area=10, category=1)
        assert 0 <= item_id <= 999

    def test_generate_area_number(self, generator):
        """Test generating an area number."""
        number = generator.generate_area_number(
            name="Test Area",
            description="Test description",
        )

        assert number.area in [10, 20]
        assert number.category is None
        assert number.item_id is None
        assert number.name == "Test Area"

    def test_generate_area_number_with_preference(self, generator):
        """Test generating area with preferred number."""
        number = generator.generate_area_number(
            name="Test Area",
            preferred_area=20,
        )

        assert number.area == 20

    def test_generate_category_number(self, generator):
        """Test generating a category number."""
        number = generator.generate_category_number(
            area=10,
            name="Test Category",
        )

        assert number.area == 10
        assert number.category is not None
        assert number.item_id is None
        assert number.name == "Test Category"

    def test_generate_id_number(self, generator):
        """Test generating an ID number."""
        number = generator.generate_id_number(
            area=10,
            category=1,
            name="Test ID",
        )

        assert number.area == 10
        assert number.category == 1
        assert number.item_id is not None
        assert number.name == "Test ID"

    def test_suggest_number_for_content(self, generator):
        """Test suggesting number based on content."""
        content = "This is a budget document for Q1 2024"
        filename = "budget-q1-2024.xlsx"

        number, confidence, reasons = generator.suggest_number_for_content(
            content=content,
            filename=filename,
        )

        # Should match Finance area (10-19) due to "budget" keyword
        assert number.area in range(10, 20)
        assert confidence > 0.5
        assert len(reasons) > 0

    def test_suggest_number_category_match(self, generator):
        """Test suggestion matching category keywords."""
        content = "Invoice for services rendered"
        filename = "invoice-123.pdf"

        number, confidence, reasons = generator.suggest_number_for_content(
            content=content,
            filename=filename,
        )

        # Should match Finance area and Invoices category
        assert number.area in range(10, 20)
        assert confidence > 0.6

    def test_validate_number(self, generator):
        """Test number validation."""
        number = JohnnyDecimalNumber(area=10, category=1)
        is_valid, errors = generator.validate_number(number)

        assert is_valid
        assert len(errors) == 0

    def test_validate_number_already_used(self, generator):
        """Test validating an already used number."""
        number = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(number, Path("/test/file.txt"))

        is_valid, errors = generator.validate_number(number)

        assert not is_valid
        assert len(errors) > 0
        assert "already used" in errors[0]

    def test_validate_number_reserved(self, generator):
        """Test validating a reserved number."""
        number = JohnnyDecimalNumber(area=10, category=1)
        generator.scheme.reserve_number(number)

        is_valid, errors = generator.validate_number(number)

        assert not is_valid
        assert any("reserved" in error for error in errors)

    def test_find_conflicts_exact(self, generator):
        """Test finding exact number conflicts."""
        number = JohnnyDecimalNumber(area=10, category=1)
        file_path = Path("/test/file.txt")

        generator.register_existing_number(number, file_path)

        conflicts = generator.find_conflicts(number)
        assert len(conflicts) == 1
        assert conflicts[0][0] == "10.01"
        assert conflicts[0][1] == file_path

    def test_find_conflicts_parent(self, generator):
        """Test finding parent conflicts."""
        # Register parent (area only)
        parent = JohnnyDecimalNumber(area=10)
        generator.register_existing_number(parent, Path("/test/parent.txt"))

        # Try to use child (category)
        child = JohnnyDecimalNumber(area=10, category=1)
        conflicts = generator.find_conflicts(child)

        assert len(conflicts) == 1
        assert "10" in conflicts[0][0]

    def test_find_conflicts_children(self, generator):
        """Test finding child conflicts."""
        # Register children (categories)
        child1 = JohnnyDecimalNumber(area=10, category=1)
        child2 = JohnnyDecimalNumber(area=10, category=2)
        generator.register_existing_number(child1, Path("/test/child1.txt"))
        generator.register_existing_number(child2, Path("/test/child2.txt"))

        # Try to use parent (area)
        parent = JohnnyDecimalNumber(area=10)
        conflicts = generator.find_conflicts(parent)

        assert len(conflicts) == 2

    def test_resolve_conflict_increment(self, generator):
        """Test resolving conflict with increment strategy."""
        # Register some numbers
        for i in range(3):
            num = JohnnyDecimalNumber(area=10, category=i)
            generator.register_existing_number(num, Path(f"/test/file{i}.txt"))

        # Resolve conflict for category 2
        conflicting = JohnnyDecimalNumber(area=10, category=2, name="Test")
        resolved = generator.resolve_conflict(conflicting, strategy="increment")

        assert resolved.area == 10
        assert resolved.category == 3  # Next available
        assert resolved.name == "Test"

    def test_resolve_conflict_skip(self, generator):
        """Test resolving conflict with skip strategy."""
        # Register 0, 1, 2, skip 3, register 4
        for i in [0, 1, 2, 4]:
            num = JohnnyDecimalNumber(area=10, category=i)
            generator.register_existing_number(num, Path(f"/test/file{i}.txt"))

        # Resolve should find 3
        conflicting = JohnnyDecimalNumber(area=10, category=2)
        resolved = generator.resolve_conflict(conflicting, strategy="skip")

        assert resolved.category == 3

    def test_get_usage_statistics(self, generator):
        """Test getting usage statistics."""
        # Register some numbers
        generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=1),
            Path("/test/file1.txt"),
        )
        generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=2),
            Path("/test/file2.txt"),
        )
        generator.register_existing_number(
            JohnnyDecimalNumber(area=20, category=1),
            Path("/test/file3.txt"),
        )

        stats = generator.get_usage_statistics()

        assert stats["total_numbers"] == 3
        assert stats["areas_used"] == 2
        assert stats["categories_used"] == 3

    def test_clear_registrations(self, generator):
        """Test clearing all registrations."""
        # Register some numbers
        generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=1),
            Path("/test/file.txt"),
        )

        assert len(generator._used_numbers) == 1

        generator.clear_registrations()

        assert len(generator._used_numbers) == 0
        assert len(generator._number_mappings) == 0


class TestAdvancedScenarios:
    """Test advanced numbering scenarios."""

    def test_full_category_fallback(self, generator):
        """Test behavior when category is full."""
        # Fill up all IDs in a category
        for i in range(1000):
            num = JohnnyDecimalNumber(area=10, category=1, item_id=i)
            generator.register_existing_number(num, Path(f"/test/file{i}.txt"))

        # Try to get next ID - should raise error
        with pytest.raises(InvalidNumberError, match="No available ID numbers"):
            generator.get_next_available_id(area=10, category=1)

    def test_full_area_handling(self, generator):
        """Test behavior when area is full."""
        # Fill up all categories in area 10
        for i in range(100):
            num = JohnnyDecimalNumber(area=10, category=i)
            generator.register_existing_number(num, Path(f"/test/file{i}.txt"))

        # Try to get next category - should raise error
        with pytest.raises(InvalidNumberError, match="No available category numbers"):
            generator.get_next_available_category(area=10)

    def test_mixed_level_registrations(self, generator):
        """Test registering numbers at different levels."""
        # Register at different levels
        area = JohnnyDecimalNumber(area=15)
        category = JohnnyDecimalNumber(area=16, category=1)
        item = JohnnyDecimalNumber(area=17, category=1, item_id=5)

        generator.register_existing_number(area, Path("/test/area.txt"))
        generator.register_existing_number(category, Path("/test/category.txt"))
        generator.register_existing_number(item, Path("/test/item.txt"))

        # All should be registered
        assert "15" in generator._used_numbers
        assert "16.01" in generator._used_numbers
        assert "17.01.005" in generator._used_numbers

    def test_preferred_number_fallback(self, generator):
        """Test fallback when preferred number is taken."""
        # Register preferred number
        preferred = JohnnyDecimalNumber(area=10, category=5)
        generator.register_existing_number(preferred, Path("/test/existing.txt"))

        # Try to generate with same preference
        new_number = generator.generate_category_number(
            area=10,
            name="New",
            preferred_category=5,
        )

        # Should get different category
        assert new_number.category != 5
        assert new_number.area == 10
