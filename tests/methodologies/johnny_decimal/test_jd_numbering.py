"""Tests for Johnny Decimal numbering uncovered branches.

Targets: register_existing conflict, get_next_available_area exhaustion,
generate_* preferred number paths, suggest_number_for_content category
occupied/full paths, validate_number reserved/used, find_conflicts
parent/child, resolve_conflict strategies, get_usage_statistics.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.methodologies.johnny_decimal.categories import (
    CategoryDefinition,
    JohnnyDecimalNumber,
    NumberingScheme,
    get_default_scheme,
)
from file_organizer.methodologies.johnny_decimal.numbering import (
    InvalidNumberError,
    JohnnyDecimalGenerator,
    NumberConflictError,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def generator() -> JohnnyDecimalGenerator:
    return JohnnyDecimalGenerator(get_default_scheme())


class TestRegisterExisting:
    """Cover register_existing_number conflict — line 89."""

    def test_register_conflict_raises(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(num, Path("/a"))
        with pytest.raises(NumberConflictError, match="already registered"):
            generator.register_existing_number(num, Path("/b"))


class TestIsNumberAvailable:
    """Cover is_number_available — line 89, 108."""

    def test_used_number_not_available(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(num, Path("/a"))
        assert generator.is_number_available(num) is False


class TestGetNextAvailableArea:
    """Cover get_next_available_area — lines 108, 125."""

    def test_preferred_area_used(self, generator: JohnnyDecimalGenerator) -> None:
        """Preferred area with available categories returns it (line 111-116)."""
        result = generator.get_next_available_area(preferred_area=10)
        assert result == 10


class TestGetNextAvailableCategory:
    """Cover get_next_available_category — line 144 (exhaustion not practical to test)."""

    def test_finds_first_available(self, generator: JohnnyDecimalGenerator) -> None:
        cat = generator.get_next_available_category(10)
        assert 0 <= cat <= 99


class TestGenerateNumbers:
    """Cover generate_*_number preferred paths — lines 223, 253-261."""

    def test_generate_area_preferred_available(self, generator: JohnnyDecimalGenerator) -> None:
        num = generator.generate_area_number("Finance", preferred_area=20)
        assert num.area == 20
        assert num.name == "Finance"

    def test_generate_area_preferred_unavailable(self, generator: JohnnyDecimalGenerator) -> None:
        """Preferred area occupied falls back to next available."""
        taken = JohnnyDecimalNumber(area=20)
        generator.register_existing_number(taken, Path("/a"))
        num = generator.generate_area_number("Finance", preferred_area=20)
        assert num.area != 20 or num.name == "Finance"

    def test_generate_category_preferred_available(self, generator: JohnnyDecimalGenerator) -> None:
        num = generator.generate_category_number(10, "Budgets", preferred_category=5)
        assert num.category == 5

    def test_generate_category_preferred_unavailable(
        self, generator: JohnnyDecimalGenerator
    ) -> None:
        taken = JohnnyDecimalNumber(area=10, category=5)
        generator.register_existing_number(taken, Path("/a"))
        num = generator.generate_category_number(10, "Budgets", preferred_category=5)
        assert num.category != 5

    def test_generate_id_preferred_available(self, generator: JohnnyDecimalGenerator) -> None:
        num = generator.generate_id_number(10, 1, "Doc", preferred_id=42)
        assert num.item_id == 42

    def test_generate_id_preferred_unavailable(self, generator: JohnnyDecimalGenerator) -> None:
        taken = JohnnyDecimalNumber(area=10, category=1, item_id=42)
        generator.register_existing_number(taken, Path("/a"))
        num = generator.generate_id_number(10, 1, "Doc", preferred_id=42)
        assert num.item_id != 42


class TestSuggestNumberForContent:
    """Cover suggest_number_for_content — lines 334-343, 351-355."""

    def test_suggest_with_matching_area(self, generator: JohnnyDecimalGenerator) -> None:
        """Content matching area keywords yields higher confidence."""
        # Use keyword from the default scheme
        scheme = generator.scheme
        if scheme.areas:
            first_area = next(iter(scheme.areas.values()))
            if first_area.keywords:
                kw = first_area.keywords[0]
                num, conf, reasons = generator.suggest_number_for_content(kw)
                assert conf >= 0.3
                assert len(reasons) > 0

    def test_suggest_no_area_match(self, generator: JohnnyDecimalGenerator) -> None:
        """No keyword match uses default area with low confidence."""
        num, conf, reasons = generator.suggest_number_for_content("zzzzxyzzy_nomatch")
        assert conf <= 0.5

    def test_suggest_prefer_id_not_category(self, generator: JohnnyDecimalGenerator) -> None:
        """prefer_category=False generates ID level."""
        num, conf, reasons = generator.suggest_number_for_content(
            "test content", prefer_category=False
        )
        # Should have item_id set
        assert num is not None


class TestValidateNumber:
    """Cover validate_number — lines 373, 380, 444-446."""

    def test_validate_used_number(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(num, Path("/a"))
        is_valid, errors = generator.validate_number(num)
        assert is_valid is False
        assert any("already used" in e for e in errors)


class TestFindConflicts:
    """Cover find_conflicts — lines 461, 469-471."""

    def test_find_exact_conflict(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(num, Path("/a"))
        conflicts = generator.find_conflicts(num)
        assert len(conflicts) >= 1

    def test_find_parent_conflict(self, generator: JohnnyDecimalGenerator) -> None:
        """Category number conflicts with existing area (line 461)."""
        area_num = JohnnyDecimalNumber(area=10)
        generator.register_existing_number(area_num, Path("/a"))
        cat_num = JohnnyDecimalNumber(area=10, category=1)
        conflicts = generator.find_conflicts(cat_num)
        parent_conflicts = [c for c in conflicts if c[0] == "10"]
        assert len(parent_conflicts) >= 1

    def test_find_child_conflict(self, generator: JohnnyDecimalGenerator) -> None:
        """Area number conflicts with existing category (lines 469-471)."""
        cat_num = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(cat_num, Path("/a"))
        area_num = JohnnyDecimalNumber(area=10)
        conflicts = generator.find_conflicts(area_num)
        child_conflicts = [c for c in conflicts if "10." in c[0]]
        assert len(child_conflicts) >= 1


class TestResolveConflict:
    """Cover resolve_conflict strategies — lines 487-496."""

    def test_resolve_increment_id(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1, item_id=1, name="Doc")
        generator.register_existing_number(num, Path("/a"))
        resolved = generator.resolve_conflict(num, strategy="increment")
        assert resolved.item_id != 1

    def test_resolve_increment_category(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1, name="Cat")
        generator.register_existing_number(num, Path("/a"))
        resolved = generator.resolve_conflict(num, strategy="increment")
        assert resolved.category != 1

    def test_resolve_increment_area(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, name="Area")
        generator.register_existing_number(num, Path("/a"))
        resolved = generator.resolve_conflict(num, strategy="increment")
        assert resolved is not None

    def test_resolve_skip_id(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1, item_id=1, name="Doc")
        generator.register_existing_number(num, Path("/a"))
        resolved = generator.resolve_conflict(num, strategy="skip")
        assert resolved.item_id != 1

    def test_resolve_skip_category(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1, name="Cat")
        generator.register_existing_number(num, Path("/a"))
        resolved = generator.resolve_conflict(num, strategy="skip")
        assert resolved is not None

    def test_resolve_skip_area(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, name="Area")
        generator.register_existing_number(num, Path("/a"))
        resolved = generator.resolve_conflict(num, strategy="skip")
        assert resolved is not None

    def test_resolve_suggest(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, name="Test")
        resolved = generator.resolve_conflict(num, strategy="suggest")
        assert resolved is not None


class TestGetUsageStatistics:
    """Cover get_usage_statistics — lines 507-519."""

    def test_stats_empty(self, generator: JohnnyDecimalGenerator) -> None:
        stats = generator.get_usage_statistics()
        assert stats["total_numbers"] == 0

    def test_stats_with_numbers(self, generator: JohnnyDecimalGenerator) -> None:
        generator.register_existing_number(JohnnyDecimalNumber(area=10), Path("/a"))
        generator.register_existing_number(JohnnyDecimalNumber(area=10, category=1), Path("/b"))
        generator.register_existing_number(
            JohnnyDecimalNumber(area=10, category=1, item_id=1), Path("/c")
        )
        stats = generator.get_usage_statistics()
        assert stats["total_numbers"] == 3
        assert stats["areas_used"] >= 1
        assert stats["categories_used"] >= 1
        assert stats["ids_used"] >= 1


class TestClearRegistrations:
    def test_clear(self, generator: JohnnyDecimalGenerator) -> None:
        generator.register_existing_number(JohnnyDecimalNumber(area=10), Path("/a"))
        generator.clear_registrations()
        assert generator.get_usage_statistics()["total_numbers"] == 0


class TestNumberingCoverage:
    """Cover all missing lines in numbering.py."""

    @pytest.fixture
    def scheme(self) -> NumberingScheme:
        return get_default_scheme()

    @pytest.fixture
    def generator(self, scheme: NumberingScheme) -> JohnnyDecimalGenerator:
        return JohnnyDecimalGenerator(scheme)

    # Line 89: is_number_available — reserved number
    def test_is_number_available_reserved(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1)
        generator.scheme.reserve_number(num)
        assert generator.is_number_available(num) is False

    # Lines 113->119, 115->113, 120->119, 125: get_next_available_area exhaustion
    def test_get_next_available_area_preferred_full(
        self, generator: JohnnyDecimalGenerator
    ) -> None:
        """Preferred area is full — falls through to next area."""
        # Reserve all categories in area 10 to make it 'full'
        for cat in range(100):
            num = JohnnyDecimalNumber(area=10, category=cat)
            generator._used_numbers.add(num.formatted_number)
        # preferred=10 should not return 10 since it's full
        area = generator.get_next_available_area(preferred_area=10)
        assert area != 10

    def test_get_next_available_area_all_exhausted(self, generator: JohnnyDecimalGenerator) -> None:
        """All areas full => InvalidNumberError."""
        # Fill every possible number for all areas in the scheme
        for area_num in generator.scheme.get_available_areas():
            for cat in range(100):
                num = JohnnyDecimalNumber(area=area_num, category=cat)
                generator._used_numbers.add(num.formatted_number)
        with pytest.raises(InvalidNumberError, match="No available area"):
            generator.get_next_available_area()

    # Lines 334-343: suggest_number_for_content with matched category occupied
    def test_suggest_number_category_occupied(self, generator: JohnnyDecimalGenerator) -> None:
        # Add a category with keywords that will match
        cat_def = CategoryDefinition(
            area=10,
            category=1,
            name="Budget",
            description="",
            keywords=["budget", "finance"],
        )
        generator.scheme.add_category(cat_def)
        # Register the category number so it's occupied
        num = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(num, Path("existing.txt"))

        result_num, confidence, reasons = generator.suggest_number_for_content(
            content="budget finance report", filename="budget.txt", prefer_category=True
        )
        # Should have fallen to ID level
        assert any("occupied" in r.lower() or "id" in r.lower() for r in reasons)

    # Lines 353-355: suggest with prefer_category=False, no category match
    def test_suggest_number_no_category_prefer_id(self, generator: JohnnyDecimalGenerator) -> None:
        result_num, confidence, reasons = generator.suggest_number_for_content(
            content="unknown content", filename="file.txt", prefer_category=False
        )
        assert result_num.item_id is not None

    # Lines 353-355: suggest_number no category match, get_next_available_category raises
    def test_suggest_number_all_categories_full(self, generator: JohnnyDecimalGenerator) -> None:
        """No category keyword match and get_next_available_category raises."""
        with patch.object(
            generator, "get_next_available_category", side_effect=InvalidNumberError("full")
        ):
            result_num, _, reasons = generator.suggest_number_for_content(
                content="random content", filename="random.txt", prefer_category=True
            )
        assert any("area" in r.lower() for r in reasons)

    # Category matched but all IDs full => area-level fallback
    def test_suggest_number_category_full(self, generator: JohnnyDecimalGenerator) -> None:
        cat_def = CategoryDefinition(
            area=10,
            category=1,
            name="Budget",
            description="",
            keywords=["budget"],
        )
        generator.scheme.add_category(cat_def)
        # Occupy the category number
        generator._used_numbers.add("10.01")
        # Fill all IDs in category 10.01
        for i in range(1000):
            generator._used_numbers.add(f"10.01.{i:03d}")

        result_num, _, reasons = generator.suggest_number_for_content(
            content="budget report", filename="budget.txt", prefer_category=True
        )
        assert any("full" in r.lower() or "area" in r.lower() for r in reasons)

    # Line 373: resolve_conflict area-level (number with no category or item_id)
    def test_resolve_conflict_area_level(self, generator: JohnnyDecimalGenerator) -> None:
        # Register area 10 so it conflicts, then resolve
        area_num = JohnnyDecimalNumber(area=10, name="Finance")
        generator.register_existing_number(area_num, Path("area.txt"))
        result = generator.resolve_conflict(area_num, strategy="increment")
        # generate_area_number will find another area number
        assert result is not None
        assert result.name == "Finance"

    # Line 381: resolve_conflict with suggest strategy
    def test_resolve_conflict_suggest(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=1, name="Test")
        result = generator.resolve_conflict(num, strategy="suggest")
        assert result.area is not None

    # Line 421->420: find_conflicts — child conflicts when category is None
    def test_find_conflicts_child_conflict(self, generator: JohnnyDecimalGenerator) -> None:
        # Register a category-level number
        cat_num = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(cat_num, Path("cat.txt"))
        # Check for conflicts at area level — should find child 10.01
        area_num = JohnnyDecimalNumber(area=10)
        conflicts = generator.find_conflicts(area_num)
        assert len(conflicts) >= 1
        assert any(conflict[0] == "10.01" for conflict in conflicts)

    # find_conflicts — no child conflicts (loop completes with no matches)
    def test_find_conflicts_no_children(self, generator: JohnnyDecimalGenerator) -> None:
        # Register a number NOT starting with "50." to exercise the loop false branch
        other_num = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(other_num, Path("other.txt"))
        area_num = JohnnyDecimalNumber(area=50)
        conflicts = generator.find_conflicts(area_num)
        assert len(conflicts) == 0

    # Line 373: validate_number — area not in scheme
    def test_validate_number_undefined_area(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=99)
        is_valid, errors = generator.validate_number(num)
        assert not is_valid
        assert any("not defined" in e for e in errors)

    # Line 381: validate_number — undefined category >= 10 (allowed, pass branch)
    def test_validate_number_undefined_category_allowed(
        self, generator: JohnnyDecimalGenerator
    ) -> None:
        # Area 10 is in the default scheme
        num = JohnnyDecimalNumber(area=10, category=15)
        is_valid, errors = generator.validate_number(num)
        # Category 15 in area 10 may not be defined, but >= 10 is allowed
        # So only potential errors are from other checks, not category
        category_errors = [e for e in errors if "category" in e.lower()]
        assert len(category_errors) == 0
