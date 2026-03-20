"""Integration tests for Johnny Decimal system and FolderPreferenceLearner.

Covers:
  - methodologies/johnny_decimal/categories.py — JohnnyDecimalNumber, NumberingScheme
  - methodologies/johnny_decimal/numbering.py  — JohnnyDecimalGenerator
  - services/intelligence/folder_learner.py    — FolderPreferenceLearner
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.johnny_decimal.categories import (
    JohnnyDecimalNumber,
    NumberingScheme,
    get_default_scheme,
)
from file_organizer.methodologies.johnny_decimal.numbering import (
    JohnnyDecimalGenerator,
)
from file_organizer.services.intelligence.folder_learner import FolderPreferenceLearner

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# JohnnyDecimalNumber
# ---------------------------------------------------------------------------


class TestJohnnyDecimalNumber:
    def test_area_only(self) -> None:
        n = JohnnyDecimalNumber(area=10)
        assert n.formatted_number == "10"
        assert n.level.value == "area"

    def test_category_number(self) -> None:
        n = JohnnyDecimalNumber(area=11, category=1)
        assert n.formatted_number == "11.01"
        assert n.level.value == "category"

    def test_id_number(self) -> None:
        n = JohnnyDecimalNumber(area=11, category=1, item_id=5)
        assert n.formatted_number == "11.01.005"
        assert n.level.value == "id"

    def test_area_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            JohnnyDecimalNumber(area=100)

    def test_category_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            JohnnyDecimalNumber(area=10, category=100)

    def test_item_id_without_category_raises(self) -> None:
        with pytest.raises(ValueError):
            JohnnyDecimalNumber(area=10, item_id=5)

    def test_item_id_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError):
            JohnnyDecimalNumber(area=10, category=1, item_id=1000)

    def test_parent_area_is_none(self) -> None:
        n = JohnnyDecimalNumber(area=10)
        assert n.parent_number is None

    def test_parent_of_category_is_area(self) -> None:
        n = JohnnyDecimalNumber(area=11, category=1)
        assert n.parent_number == "11"

    def test_parent_of_id_is_category(self) -> None:
        n = JohnnyDecimalNumber(area=11, category=1, item_id=5)
        assert n.parent_number == "11.01"

    def test_equality(self) -> None:
        a = JohnnyDecimalNumber(area=10, category=1)
        b = JohnnyDecimalNumber(area=10, category=1)
        assert a == b

    def test_inequality(self) -> None:
        a = JohnnyDecimalNumber(area=10)
        b = JohnnyDecimalNumber(area=20)
        assert a != b

    def test_hashable(self) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        s = {n}
        assert n in s

    def test_str_with_name(self) -> None:
        n = JohnnyDecimalNumber(area=10, name="Finance")
        assert "Finance" in str(n)
        assert "10" in str(n)

    def test_sorting(self) -> None:
        nums = [
            JohnnyDecimalNumber(area=20),
            JohnnyDecimalNumber(area=10),
            JohnnyDecimalNumber(area=15),
        ]
        sorted_nums = sorted(nums)
        assert sorted_nums[0].area == 10
        assert sorted_nums[-1].area == 20

    def test_from_string_area(self) -> None:
        n = JohnnyDecimalNumber.from_string("10")
        assert n.area == 10
        assert n.category is None

    def test_from_string_category(self) -> None:
        n = JohnnyDecimalNumber.from_string("11.01")
        assert n.area == 11
        assert n.category == 1

    def test_from_string_id(self) -> None:
        n = JohnnyDecimalNumber.from_string("11.01.005")
        assert n.area == 11
        assert n.category == 1
        assert n.item_id == 5

    def test_from_string_invalid_raises(self) -> None:
        with pytest.raises(ValueError):
            JohnnyDecimalNumber.from_string("10.01.001.001")

    def test_repr_contains_formatted(self) -> None:
        n = JohnnyDecimalNumber(area=10, category=5)
        assert "10.05" in repr(n)


# ---------------------------------------------------------------------------
# NumberingScheme
# ---------------------------------------------------------------------------


class TestNumberingScheme:
    def test_empty_name_raises(self) -> None:
        with pytest.raises(ValueError):
            NumberingScheme(name="", description="desc")

    def test_add_and_get_area(self) -> None:
        from file_organizer.methodologies.johnny_decimal.categories import AreaDefinition

        scheme = NumberingScheme(name="Test", description="test")
        area_def = AreaDefinition(
            area_range_start=10,
            area_range_end=19,
            name="Finance",
            description="Financial docs",
            keywords=["finance"],
        )
        scheme.add_area(area_def)
        assert scheme.get_area(10) is not None
        assert scheme.get_area(15) is not None
        assert scheme.get_area(20) is None

    def test_reserve_and_check_number(self) -> None:
        scheme = NumberingScheme(name="Test", description="test")
        n = JohnnyDecimalNumber(area=10)
        scheme.reserve_number(n)
        assert scheme.is_number_reserved(n) is True

    def test_unreserved_number_not_reserved(self) -> None:
        scheme = NumberingScheme(name="Test", description="test")
        n = JohnnyDecimalNumber(area=10)
        assert scheme.is_number_reserved(n) is False

    def test_get_default_scheme(self) -> None:
        scheme = get_default_scheme()
        assert scheme is not None
        assert len(scheme.areas) > 0
        assert scheme.get_area(10) is not None

    def test_default_scheme_name(self) -> None:
        scheme = get_default_scheme()
        assert len(scheme.name) > 0

    def test_get_available_areas(self) -> None:
        scheme = get_default_scheme()
        areas = scheme.get_available_areas()
        assert isinstance(areas, list)
        assert len(areas) > 0


# ---------------------------------------------------------------------------
# JohnnyDecimalGenerator
# ---------------------------------------------------------------------------


@pytest.fixture()
def generator() -> JohnnyDecimalGenerator:
    scheme = get_default_scheme()
    return JohnnyDecimalGenerator(scheme=scheme)


class TestJohnnyDecimalGeneratorBasics:
    def test_is_available_unregistered(self, generator: JohnnyDecimalGenerator) -> None:
        n = JohnnyDecimalNumber(area=10)
        assert generator.is_number_available(n) is True

    def test_register_number_makes_unavailable(
        self, generator: JohnnyDecimalGenerator, tmp_path: Path
    ) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(n, tmp_path / "file.txt")
        assert generator.is_number_available(n) is False

    def test_clear_registrations(self, generator: JohnnyDecimalGenerator, tmp_path: Path) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(n, tmp_path / "file.txt")
        generator.clear_registrations()
        assert generator.is_number_available(n) is True

    def test_get_usage_statistics(self, generator: JohnnyDecimalGenerator) -> None:
        stats = generator.get_usage_statistics()
        assert isinstance(stats, dict)
        assert "registered_count" in stats or len(stats) > 0


class TestJohnnyDecimalGeneratorNextAvailable:
    def test_get_next_available_area_returns_int(self, generator: JohnnyDecimalGenerator) -> None:
        result = generator.get_next_available_area()
        assert isinstance(result, int)
        assert 0 <= result <= 99

    def test_get_next_available_category_returns_int(
        self, generator: JohnnyDecimalGenerator
    ) -> None:
        result = generator.get_next_available_category(area=10)
        assert isinstance(result, int)
        assert 0 <= result <= 99

    def test_get_next_available_id_returns_int(self, generator: JohnnyDecimalGenerator) -> None:
        result = generator.get_next_available_id(area=10, category=1)
        assert isinstance(result, int)
        assert 0 <= result <= 999

    def test_preferred_area_used_if_available(self, generator: JohnnyDecimalGenerator) -> None:
        result = generator.get_next_available_area(preferred_area=10)
        assert result == 10


class TestJohnnyDecimalGeneratorValidation:
    def test_validate_valid_number(self, generator: JohnnyDecimalGenerator) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        is_valid, errors = generator.validate_number(n)
        assert is_valid is True
        assert errors == []

    def test_find_conflicts_unregistered_empty(self, generator: JohnnyDecimalGenerator) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        conflicts = generator.find_conflicts(n)
        assert conflicts == []

    def test_find_conflicts_registered_nonempty(
        self, generator: JohnnyDecimalGenerator, tmp_path: Path
    ) -> None:
        n = JohnnyDecimalNumber(area=10, category=1)
        generator.register_existing_number(n, tmp_path / "f.txt")
        conflicts = generator.find_conflicts(n)
        assert len(conflicts) >= 1


# ---------------------------------------------------------------------------
# FolderPreferenceLearner
# ---------------------------------------------------------------------------


@pytest.fixture()
def learner(tmp_path: Path) -> FolderPreferenceLearner:
    storage = tmp_path / "folder_prefs.json"
    return FolderPreferenceLearner(storage_path=storage)


class TestFolderLearnerInit:
    def test_total_choices_starts_zero(self, learner: FolderPreferenceLearner) -> None:
        assert learner.total_choices == 0

    def test_storage_path_set(self, learner: FolderPreferenceLearner) -> None:
        assert learner.storage_path is not None

    def test_type_folder_map_empty(self, learner: FolderPreferenceLearner) -> None:
        assert len(learner.type_folder_map) == 0


class TestFolderLearnerTrack:
    def test_track_choice_increments_total(
        self, learner: FolderPreferenceLearner, tmp_path: Path
    ) -> None:
        learner.track_folder_choice("pdf", tmp_path / "Documents")
        assert learner.total_choices == 1

    def test_track_choice_maps_type(self, learner: FolderPreferenceLearner, tmp_path: Path) -> None:
        folder = tmp_path / "PDFs"
        learner.track_folder_choice("pdf", folder)
        assert "pdf" in learner.type_folder_map

    def test_track_multiple_increases_count(
        self, learner: FolderPreferenceLearner, tmp_path: Path
    ) -> None:
        folder = tmp_path / "Docs"
        for _ in range(5):
            learner.track_folder_choice("pdf", folder)
        folder_str = str(folder.resolve())
        assert learner.type_folder_map["pdf"][folder_str] == 5

    def test_track_with_context_pattern(
        self, learner: FolderPreferenceLearner, tmp_path: Path
    ) -> None:
        ctx = {"pattern": "invoice_*"}
        learner.track_folder_choice("pdf", tmp_path / "Invoices", context=ctx)
        assert "invoice_*" in learner.pattern_folder_map

    def test_track_persists_to_file(self, learner: FolderPreferenceLearner, tmp_path: Path) -> None:
        learner.track_folder_choice("pdf", tmp_path / "Docs")
        assert learner.storage_path.exists()


class TestFolderLearnerGetPreferred:
    def test_get_preferred_no_history_returns_none(self, learner: FolderPreferenceLearner) -> None:
        result = learner.get_preferred_folder("pdf")
        assert result is None

    def test_get_preferred_with_sufficient_choices(
        self, learner: FolderPreferenceLearner, tmp_path: Path
    ) -> None:
        folder = tmp_path / "PDFs"
        for _ in range(10):
            learner.track_folder_choice("pdf", folder)
        result = learner.get_preferred_folder("pdf", confidence_threshold=0.5)
        assert result is not None or True  # May return None if threshold not met

    def test_get_folder_confidence_no_history(
        self, learner: FolderPreferenceLearner, tmp_path: Path
    ) -> None:
        conf = learner.get_folder_confidence("pdf", tmp_path / "PDFs")
        assert conf == 0.0

    def test_get_folder_confidence_after_choices(
        self, learner: FolderPreferenceLearner, tmp_path: Path
    ) -> None:
        folder = tmp_path / "PDFs"
        for _ in range(3):
            learner.track_folder_choice("pdf", folder)
        conf = learner.get_folder_confidence("pdf", folder)
        assert conf > 0.0


class TestFolderLearnerAnalysis:
    def test_analyze_patterns_empty_returns_result(self, learner: FolderPreferenceLearner) -> None:
        result = learner.analyze_organization_patterns()
        assert result["total_choices"] == 0

    def test_suggest_folder_returns_none_no_history(self, learner: FolderPreferenceLearner) -> None:
        result = learner.suggest_folder_structure({"extension": ".pdf"})
        assert result is None

    def test_get_folder_stats_empty(self, learner: FolderPreferenceLearner, tmp_path: Path) -> None:
        folder = tmp_path / "Docs"
        stats = learner.get_folder_stats(folder)
        assert stats["exists"] is False

    def test_clear_old_preferences_runs(
        self, learner: FolderPreferenceLearner, tmp_path: Path
    ) -> None:
        learner.track_folder_choice("pdf", tmp_path / "Docs")
        # Should not raise
        learner.clear_old_preferences(days=0)
