"""
Tests for Johnny Decimal categories module.

Tests data models, validation, and category definitions.
"""

import pytest
from pathlib import Path

from file_organizer.methodologies.johnny_decimal.categories import (
    AreaDefinition,
    CategoryDefinition,
    JohnnyDecimalNumber,
    NumberingResult,
    NumberingScheme,
    NumberLevel,
    get_default_scheme,
)


class TestJohnnyDecimalNumber:
    """Test JohnnyDecimalNumber data class."""

    def test_area_only_number(self):
        """Test creating an area-only number."""
        number = JohnnyDecimalNumber(area=10, name="Finance")
        assert number.area == 10
        assert number.category is None
        assert number.item_id is None
        assert number.level == NumberLevel.AREA
        assert number.formatted_number == "10"
        assert str(number) == "10 Finance"

    def test_category_number(self):
        """Test creating a category number."""
        number = JohnnyDecimalNumber(area=10, category=1, name="Budgets")
        assert number.area == 10
        assert number.category == 1
        assert number.item_id is None
        assert number.level == NumberLevel.CATEGORY
        assert number.formatted_number == "10.01"
        assert str(number) == "10.01 Budgets"

    def test_full_id_number(self):
        """Test creating a full ID number."""
        number = JohnnyDecimalNumber(
            area=10, category=1, item_id=5, name="Q1 Budget"
        )
        assert number.area == 10
        assert number.category == 1
        assert number.item_id == 5
        assert number.level == NumberLevel.ID
        assert number.formatted_number == "10.01.005"
        assert str(number) == "10.01.005 Q1 Budget"

    def test_area_validation(self):
        """Test area number validation."""
        with pytest.raises(ValueError, match="Area must be between 0 and 99"):
            JohnnyDecimalNumber(area=100)

        with pytest.raises(ValueError, match="Area must be between 0 and 99"):
            JohnnyDecimalNumber(area=-1)

    def test_category_validation(self):
        """Test category number validation."""
        with pytest.raises(ValueError, match="Category must be between 0 and 99"):
            JohnnyDecimalNumber(area=10, category=100)

    def test_item_id_validation(self):
        """Test item ID validation."""
        with pytest.raises(ValueError, match="Item ID must be between 0 and 999"):
            JohnnyDecimalNumber(area=10, category=1, item_id=1000)

        with pytest.raises(ValueError, match="Cannot have item_id without category"):
            JohnnyDecimalNumber(area=10, item_id=1)

    def test_parent_number(self):
        """Test parent number calculation."""
        area = JohnnyDecimalNumber(area=10)
        assert area.parent_number is None

        category = JohnnyDecimalNumber(area=10, category=1)
        assert category.parent_number == "10"

        item = JohnnyDecimalNumber(area=10, category=1, item_id=5)
        assert item.parent_number == "10.01"

    def test_from_string_parsing(self):
        """Test parsing numbers from strings."""
        area = JohnnyDecimalNumber.from_string("10")
        assert area.area == 10
        assert area.category is None
        assert area.item_id is None

        category = JohnnyDecimalNumber.from_string("10.01")
        assert category.area == 10
        assert category.category == 1

        item = JohnnyDecimalNumber.from_string("10.01.005")
        assert item.area == 10
        assert item.category == 1
        assert item.item_id == 5

    def test_from_string_invalid(self):
        """Test parsing invalid strings."""
        with pytest.raises(ValueError, match="Invalid Johnny Decimal format"):
            JohnnyDecimalNumber.from_string("10.01.005.001")

        with pytest.raises(ValueError):
            JohnnyDecimalNumber.from_string("invalid")

    def test_equality(self):
        """Test number equality comparison."""
        num1 = JohnnyDecimalNumber(area=10, category=1, name="A")
        num2 = JohnnyDecimalNumber(area=10, category=1, name="B")
        num3 = JohnnyDecimalNumber(area=10, category=2)

        assert num1 == num2  # Names don't affect equality
        assert num1 != num3

    def test_sorting(self):
        """Test number sorting."""
        numbers = [
            JohnnyDecimalNumber(area=20),
            JohnnyDecimalNumber(area=10, category=5),
            JohnnyDecimalNumber(area=10, category=1),
            JohnnyDecimalNumber(area=10, category=1, item_id=5),
            JohnnyDecimalNumber(area=10, category=1, item_id=1),
        ]

        sorted_nums = sorted(numbers)

        # Sorting treats missing values as 0, so:
        # 10 (10, 0, 0) comes before 10.01 (10, 1, 0)
        assert sorted_nums[0].formatted_number == "10.01"  # (10, 1, 0)
        assert sorted_nums[1].formatted_number == "10.01.001"  # (10, 1, 1)
        assert sorted_nums[2].formatted_number == "10.01.005"  # (10, 1, 5)
        assert sorted_nums[3].formatted_number == "10.05"  # (10, 5, 0)
        assert sorted_nums[4].formatted_number == "20"  # (20, 0, 0)

    def test_hashable(self):
        """Test that numbers are hashable."""
        num = JohnnyDecimalNumber(area=10, category=1)
        number_set = {num, num}  # Should only contain one
        assert len(number_set) == 1


class TestAreaDefinition:
    """Test AreaDefinition class."""

    def test_valid_area_definition(self):
        """Test creating a valid area definition."""
        area = AreaDefinition(
            area_range_start=10,
            area_range_end=19,
            name="Finance",
            description="Financial matters",
            keywords=["budget", "invoice"],
            examples=["Budget spreadsheet"],
        )

        assert area.area_range_start == 10
        assert area.area_range_end == 19
        assert area.name == "Finance"

    def test_area_validation(self):
        """Test area definition validation."""
        with pytest.raises(ValueError, match="Area start must be 0-99"):
            AreaDefinition(
                area_range_start=100,
                area_range_end=110,
                name="Test",
                description="Test",
            )

        with pytest.raises(ValueError, match="Area start.*must be <= end"):
            AreaDefinition(
                area_range_start=20,
                area_range_end=10,
                name="Test",
                description="Test",
            )

        with pytest.raises(ValueError, match="Area name cannot be empty"):
            AreaDefinition(
                area_range_start=10,
                area_range_end=19,
                name="",
                description="Test",
            )

    def test_contains_method(self):
        """Test contains method."""
        area = AreaDefinition(
            area_range_start=10,
            area_range_end=19,
            name="Finance",
            description="Finance",
        )

        assert area.contains(10)
        assert area.contains(15)
        assert area.contains(19)
        assert not area.contains(9)
        assert not area.contains(20)

    def test_matches_keyword(self):
        """Test keyword matching."""
        area = AreaDefinition(
            area_range_start=10,
            area_range_end=19,
            name="Finance",
            description="Finance",
            keywords=["budget", "invoice", "expense"],
        )

        assert area.matches_keyword("This is a budget document")
        assert area.matches_keyword("Invoice #123")
        assert area.matches_keyword("EXPENSE REPORT")
        assert not area.matches_keyword("Marketing plan")


class TestCategoryDefinition:
    """Test CategoryDefinition class."""

    def test_valid_category_definition(self):
        """Test creating a valid category definition."""
        category = CategoryDefinition(
            area=10,
            category=1,
            name="Budgets",
            description="Budget documents",
            keywords=["budget", "forecast"],
            patterns=["budget-*", "*-forecast"],
        )

        assert category.area == 10
        assert category.category == 1
        assert category.name == "Budgets"
        assert category.formatted_number == "10.01"

    def test_category_validation(self):
        """Test category validation."""
        with pytest.raises(ValueError, match="Area must be 0-99"):
            CategoryDefinition(
                area=100,
                category=1,
                name="Test",
                description="Test",
            )

        with pytest.raises(ValueError, match="Category name cannot be empty"):
            CategoryDefinition(
                area=10,
                category=1,
                name="",
                description="Test",
            )

    def test_matches_keyword(self):
        """Test keyword matching."""
        category = CategoryDefinition(
            area=10,
            category=1,
            name="Budgets",
            description="Budgets",
            keywords=["budget", "financial plan"],
        )

        assert category.matches_keyword("Annual budget")
        assert category.matches_keyword("Financial Plan 2024")
        assert not category.matches_keyword("Marketing campaign")

    def test_matches_pattern(self):
        """Test pattern matching."""
        category = CategoryDefinition(
            area=10,
            category=1,
            name="Budgets",
            description="Budgets",
            patterns=["budget-*", "*-forecast.xlsx"],
        )

        assert category.matches_pattern("budget-2024.xlsx")
        assert category.matches_pattern("q1-forecast.xlsx")
        assert not category.matches_pattern("invoice-123.pdf")


class TestNumberingResult:
    """Test NumberingResult class."""

    def test_valid_result(self):
        """Test creating a valid numbering result."""
        number = JohnnyDecimalNumber(area=10, category=1)
        result = NumberingResult(
            file_path=Path("/test/file.txt"),
            number=number,
            confidence=0.85,
            reasons=["Matched keywords", "High confidence"],
        )

        assert result.file_path == Path("/test/file.txt")
        assert result.number == number
        assert result.confidence == 0.85
        assert result.is_confident
        assert not result.requires_review
        assert not result.has_conflicts

    def test_result_validation(self):
        """Test result validation."""
        number = JohnnyDecimalNumber(area=10)

        with pytest.raises(ValueError, match="confidence must be between 0.0 and 1.0"):
            NumberingResult(
                file_path=Path("/test/file.txt"),
                number=number,
                confidence=1.5,
                reasons=["Test"],
            )

        with pytest.raises(ValueError, match="reasons list cannot be empty"):
            NumberingResult(
                file_path=Path("/test/file.txt"),
                number=number,
                confidence=0.8,
                reasons=[],
            )

    def test_confidence_thresholds(self):
        """Test confidence threshold properties."""
        number = JohnnyDecimalNumber(area=10)

        high_confidence = NumberingResult(
            file_path=Path("/test/file.txt"),
            number=number,
            confidence=0.85,
            reasons=["High"],
        )
        assert high_confidence.is_confident
        assert not high_confidence.requires_review

        low_confidence = NumberingResult(
            file_path=Path("/test/file.txt"),
            number=number,
            confidence=0.5,
            reasons=["Low"],
        )
        assert not low_confidence.is_confident
        assert low_confidence.requires_review

    def test_conflicts(self):
        """Test conflict handling."""
        number = JohnnyDecimalNumber(area=10)
        result = NumberingResult(
            file_path=Path("/test/file.txt"),
            number=number,
            confidence=0.8,
            reasons=["Test"],
            conflicts=["Number already in use"],
        )

        assert result.has_conflicts
        assert result.requires_review

    def test_to_dict(self):
        """Test dictionary conversion."""
        number = JohnnyDecimalNumber(area=10, category=1, name="Test")
        result = NumberingResult(
            file_path=Path("/test/file.txt"),
            number=number,
            confidence=0.8,
            reasons=["Reason 1"],
            alternative_numbers={"10.02": 0.6},
            conflicts=["Conflict 1"],
        )

        result_dict = result.to_dict()

        assert result_dict["file_path"] == "/test/file.txt"
        assert result_dict["number"] == "10.01"
        assert result_dict["number_name"] == "Test"
        assert result_dict["confidence"] == 0.8
        assert "Reason 1" in result_dict["reasons"]
        assert "10.02" in result_dict["alternative_numbers"]
        assert "Conflict 1" in result_dict["conflicts"]


class TestNumberingScheme:
    """Test NumberingScheme class."""

    def test_create_scheme(self):
        """Test creating a numbering scheme."""
        scheme = NumberingScheme(
            name="Test Scheme",
            description="Test description",
        )

        assert scheme.name == "Test Scheme"
        assert scheme.allow_gaps
        assert scheme.auto_increment
        assert len(scheme.areas) == 0

    def test_add_area(self):
        """Test adding area definitions."""
        scheme = NumberingScheme(name="Test", description="Test")
        area = AreaDefinition(
            area_range_start=10,
            area_range_end=19,
            name="Finance",
            description="Finance",
        )

        scheme.add_area(area)

        assert len(scheme.areas) == 10  # 10-19
        assert scheme.get_area(10) == area
        assert scheme.get_area(15) == area
        assert scheme.get_area(20) is None

    def test_add_category(self):
        """Test adding category definitions."""
        scheme = NumberingScheme(name="Test", description="Test")
        category = CategoryDefinition(
            area=10,
            category=1,
            name="Budgets",
            description="Budgets",
        )

        scheme.add_category(category)

        assert len(scheme.categories) == 1
        assert scheme.get_category(10, 1) == category
        assert scheme.get_category(10, 2) is None

    def test_reserve_numbers(self):
        """Test reserving numbers."""
        scheme = NumberingScheme(name="Test", description="Test")
        number = JohnnyDecimalNumber(area=10, category=1)

        scheme.reserve_number(number)

        assert scheme.is_number_reserved(number)
        assert "10.01" in scheme.reserved_numbers

    def test_get_available_areas(self):
        """Test getting available areas."""
        scheme = NumberingScheme(name="Test", description="Test")
        area1 = AreaDefinition(10, 19, "Area1", "Area1")
        area2 = AreaDefinition(20, 29, "Area2", "Area2")

        scheme.add_area(area1)
        scheme.add_area(area2)

        available = scheme.get_available_areas()
        assert 10 in available
        assert 15 in available
        assert 20 in available

    def test_get_available_categories(self):
        """Test getting available categories in an area."""
        scheme = NumberingScheme(name="Test", description="Test")
        cat1 = CategoryDefinition(10, 1, "Cat1", "Cat1")
        cat2 = CategoryDefinition(10, 2, "Cat2", "Cat2")
        cat3 = CategoryDefinition(20, 1, "Cat3", "Cat3")

        scheme.add_category(cat1)
        scheme.add_category(cat2)
        scheme.add_category(cat3)

        area10_cats = scheme.get_available_categories(10)
        assert len(area10_cats) == 2
        assert "10.01" in area10_cats
        assert "10.02" in area10_cats

        area20_cats = scheme.get_available_categories(20)
        assert len(area20_cats) == 1


class TestDefaultScheme:
    """Test default scheme configuration."""

    def test_get_default_scheme(self):
        """Test getting the default scheme."""
        scheme = get_default_scheme()

        assert scheme.name == "Default Johnny Decimal Scheme"
        assert len(scheme.areas) > 0
        assert scheme.allow_gaps
        assert scheme.auto_increment

    def test_default_areas_defined(self):
        """Test that default areas are properly defined."""
        scheme = get_default_scheme()

        # Check that common areas exist
        finance_area = scheme.get_area(10)
        assert finance_area is not None
        assert "Finance" in finance_area.name

        marketing_area = scheme.get_area(20)
        assert marketing_area is not None
        assert "Marketing" in marketing_area.name
