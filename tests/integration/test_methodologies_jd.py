"""Integration tests for the Johnny Decimal methodology package.

Covers JohnnyDecimalNumber, AreaDefinition, CategoryDefinition, NumberingScheme,
NumberingResult, JohnnyDecimalGenerator, JohnnyDecimalConfig, ConfigBuilder,
PARAJohnnyDecimalBridge, CompatibilityAnalyzer, HybridOrganizer, adapters,
and related validation data classes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# NumberLevel
# ---------------------------------------------------------------------------


class TestNumberLevel:
    """Tests for NumberLevel enum."""

    def test_all_levels_exist(self) -> None:
        """Verify all three NumberLevel values (area, category, id) are present."""
        from file_organizer.methodologies.johnny_decimal.categories import NumberLevel

        assert NumberLevel.AREA.value == "area"
        assert NumberLevel.CATEGORY.value == "category"
        assert NumberLevel.ID.value == "id"

    def test_three_levels_total(self) -> None:
        """Verify exactly three NumberLevel members are defined."""
        from file_organizer.methodologies.johnny_decimal.categories import NumberLevel

        assert len(NumberLevel) == 3


# ---------------------------------------------------------------------------
# JohnnyDecimalNumber
# ---------------------------------------------------------------------------


class TestJohnnyDecimalNumber:
    """Tests for JohnnyDecimalNumber dataclass."""

    def test_area_level(self) -> None:
        """Verify a number with only area is classified as AREA level."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberLevel,
        )

        n = JohnnyDecimalNumber(area=10)
        assert n.level == NumberLevel.AREA
        assert n.formatted_number == "10"

    def test_category_level(self) -> None:
        """Verify a number with area + category is classified as CATEGORY level."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberLevel,
        )

        n = JohnnyDecimalNumber(area=11, category=1)
        assert n.level == NumberLevel.CATEGORY
        assert n.formatted_number == "11.01"

    def test_id_level(self) -> None:
        """Verify a number with area, category, and item_id is classified as ID level."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberLevel,
        )

        n = JohnnyDecimalNumber(area=11, category=1, item_id=5)
        assert n.level == NumberLevel.ID
        assert n.formatted_number == "11.01.005"

    def test_from_string_area(self) -> None:
        """Verify from_string parses a bare area number correctly."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberLevel,
        )

        n = JohnnyDecimalNumber.from_string("10")
        assert n.area == 10
        assert n.level == NumberLevel.AREA

    def test_from_string_category(self) -> None:
        """Verify from_string parses an area.category string correctly."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberLevel,
        )

        n = JohnnyDecimalNumber.from_string("11.01")
        assert n.area == 11
        assert n.category == 1
        assert n.level == NumberLevel.CATEGORY

    def test_from_string_id(self) -> None:
        """Verify from_string parses a full area.category.id string correctly."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberLevel,
        )

        n = JohnnyDecimalNumber.from_string("11.01.005")
        assert n.area == 11
        assert n.category == 1
        assert n.item_id == 5
        assert n.level == NumberLevel.ID

    def test_invalid_area_raises(self) -> None:
        """Verify an out-of-range area value raises ValueError."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )

        with pytest.raises(ValueError):
            JohnnyDecimalNumber(area=200)

    def test_item_id_without_category_raises(self) -> None:
        """Verify specifying item_id without category raises ValueError."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )

        with pytest.raises(ValueError):
            JohnnyDecimalNumber(area=10, item_id=5)

    def test_equality(self) -> None:
        """Verify two numbers with same area and category are equal regardless of name."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )

        a = JohnnyDecimalNumber(area=11, category=1, name="A")
        b = JohnnyDecimalNumber(area=11, category=1, name="B")
        assert a == b

    def test_ordering(self) -> None:
        """Verify numbers with smaller area values compare as less than larger ones."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )

        n10 = JohnnyDecimalNumber(area=10)
        n20 = JohnnyDecimalNumber(area=20)
        assert n10 < n20

    def test_hashable(self) -> None:
        """Verify JohnnyDecimalNumber instances can be stored in a set."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )

        n = JohnnyDecimalNumber(area=11, category=1)
        s = {n}
        assert len(s) == 1

    def test_parent_number(self) -> None:
        """Verify parent_number returns the area.category string for an ID-level number."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )

        n = JohnnyDecimalNumber(area=11, category=1, item_id=5)
        assert n.parent_number == "11.01"

    def test_area_has_no_parent(self) -> None:
        """Verify parent_number is None for an area-level number."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )

        n = JohnnyDecimalNumber(area=10)
        assert n.parent_number is None


# ---------------------------------------------------------------------------
# AreaDefinition
# ---------------------------------------------------------------------------


class TestAreaDefinition:
    """Tests for AreaDefinition dataclass."""

    def test_contains_in_range(self) -> None:
        """Verify contains returns True for numbers inside the range and False outside."""
        from file_organizer.methodologies.johnny_decimal.categories import AreaDefinition

        area = AreaDefinition(
            area_range_start=10,
            area_range_end=19,
            name="Finance",
            description="Financial docs",
        )
        assert area.contains(10) is True
        assert area.contains(15) is True
        assert area.contains(19) is True
        assert area.contains(20) is False

    def test_matches_keyword_case_insensitive(self) -> None:
        """Verify keyword matching against area name is case-insensitive."""
        from file_organizer.methodologies.johnny_decimal.categories import AreaDefinition

        area = AreaDefinition(
            area_range_start=10,
            area_range_end=19,
            name="Finance",
            description="Finances",
            keywords=["invoice", "budget"],
        )
        assert area.matches_keyword("Annual Invoice 2025") is True
        assert area.matches_keyword("BUDGET report") is True
        assert area.matches_keyword("random file") is False

    def test_empty_name_raises(self) -> None:
        """Verify an empty name raises ValueError."""
        from file_organizer.methodologies.johnny_decimal.categories import AreaDefinition

        with pytest.raises(ValueError):
            AreaDefinition(area_range_start=10, area_range_end=19, name="", description="d")

    def test_start_gt_end_raises(self) -> None:
        """Verify start > end raises ValueError."""
        from file_organizer.methodologies.johnny_decimal.categories import AreaDefinition

        with pytest.raises(ValueError):
            AreaDefinition(area_range_start=19, area_range_end=10, name="X", description="d")


# ---------------------------------------------------------------------------
# CategoryDefinition (JD)
# ---------------------------------------------------------------------------


class TestJDCategoryDefinition:
    """Tests for JD CategoryDefinition dataclass."""

    def test_formatted_number(self) -> None:
        """Verify formatted_number returns the area.category string."""
        from file_organizer.methodologies.johnny_decimal.categories import CategoryDefinition

        cat = CategoryDefinition(area=11, category=1, name="Invoices", description="d")
        assert cat.formatted_number == "11.01"

    def test_matches_keyword(self) -> None:
        """Verify keyword matching returns True for matching text and False otherwise."""
        from file_organizer.methodologies.johnny_decimal.categories import CategoryDefinition

        cat = CategoryDefinition(
            area=11,
            category=1,
            name="Invoices",
            description="d",
            keywords=["invoice", "receipt"],
        )
        assert cat.matches_keyword("invoice 2025") is True
        assert cat.matches_keyword("unrelated doc") is False

    def test_matches_pattern(self) -> None:
        """Verify glob pattern matching returns True for matching filenames."""
        from file_organizer.methodologies.johnny_decimal.categories import CategoryDefinition

        cat = CategoryDefinition(
            area=11,
            category=1,
            name="PDFs",
            description="d",
            patterns=["*.pdf", "*_invoice*"],
        )
        assert cat.matches_pattern("doc.pdf") is True
        assert cat.matches_pattern("jan_invoice_2025.txt") is True
        assert cat.matches_pattern("photo.jpg") is False

    def test_empty_name_raises(self) -> None:
        """Verify an empty name raises ValueError."""
        from file_organizer.methodologies.johnny_decimal.categories import CategoryDefinition

        with pytest.raises(ValueError):
            CategoryDefinition(area=11, category=1, name="", description="d")


# ---------------------------------------------------------------------------
# NumberingResult
# ---------------------------------------------------------------------------


class TestNumberingResult:
    """Tests for NumberingResult dataclass."""

    def test_basic_result(self, tmp_path: Path) -> None:
        """Verify NumberingResult stores confidence and reasons correctly."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberingResult,
        )

        n = JohnnyDecimalNumber(area=11, category=1, item_id=5)
        result = NumberingResult(
            file_path=tmp_path / "doc.pdf",
            number=n,
            confidence=0.85,
            reasons=["keyword match", "content match"],
        )
        assert result.confidence == 0.85
        assert len(result.reasons) == 2

    def test_is_confident(self, tmp_path: Path) -> None:
        """Verify is_confident is True above threshold and False below it."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberingResult,
        )

        n = JohnnyDecimalNumber(area=11, category=1)
        high = NumberingResult(
            file_path=tmp_path / "f.txt",
            number=n,
            confidence=0.9,
            reasons=["r"],
        )
        low = NumberingResult(
            file_path=tmp_path / "g.txt",
            number=n,
            confidence=0.5,
            reasons=["r"],
        )
        assert high.is_confident is True
        assert low.is_confident is False

    def test_requires_review(self, tmp_path: Path) -> None:
        """Verify requires_review is True for low-confidence results."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberingResult,
        )

        n = JohnnyDecimalNumber(area=11, category=1)
        result = NumberingResult(
            file_path=tmp_path / "f.txt",
            number=n,
            confidence=0.4,
            reasons=["r"],
        )
        assert result.requires_review is True

    def test_to_dict(self, tmp_path: Path) -> None:
        """Verify to_dict returns a dict containing confidence."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberingResult,
        )

        n = JohnnyDecimalNumber(area=11, category=1)
        result = NumberingResult(
            file_path=tmp_path / "f.txt",
            number=n,
            confidence=0.75,
            reasons=["reason"],
        )
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "confidence" in d
        assert d["confidence"] == 0.75

    def test_invalid_confidence_raises(self, tmp_path: Path) -> None:
        """Verify confidence > 1.0 raises ValueError."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberingResult,
        )

        n = JohnnyDecimalNumber(area=11, category=1)
        with pytest.raises(ValueError):
            NumberingResult(
                file_path=tmp_path / "f.txt",
                number=n,
                confidence=1.5,
                reasons=["r"],
            )


# ---------------------------------------------------------------------------
# NumberingScheme
# ---------------------------------------------------------------------------


class TestNumberingScheme:
    """Tests for NumberingScheme dataclass."""

    def test_add_and_get_area(self) -> None:
        """Verify adding an area allows retrieval by area number."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            AreaDefinition,
            NumberingScheme,
        )

        scheme = NumberingScheme(name="test", description="d")
        area = AreaDefinition(
            area_range_start=10, area_range_end=19, name="Finance", description="d"
        )
        scheme.add_area(area)
        retrieved = scheme.get_area(10)
        assert retrieved is not None
        assert retrieved.name == "Finance"

    def test_add_and_get_category(self) -> None:
        """Verify adding a category allows retrieval by area and category number."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            CategoryDefinition,
            NumberingScheme,
        )

        scheme = NumberingScheme(name="test", description="d")
        cat = CategoryDefinition(area=11, category=1, name="Invoices", description="d")
        scheme.add_category(cat)
        retrieved = scheme.get_category(11, 1)
        assert retrieved is not None
        assert retrieved.name == "Invoices"

    def test_reserve_number(self) -> None:
        """Verify a reserved number is reported as reserved by is_number_reserved."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
            NumberingScheme,
        )

        scheme = NumberingScheme(name="test", description="d")
        n = JohnnyDecimalNumber(area=10)
        scheme.reserve_number(n)
        assert scheme.is_number_reserved(n) is True

    def test_get_available_areas(self) -> None:
        """Verify get_available_areas returns all added areas in sorted order."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            AreaDefinition,
            NumberingScheme,
        )

        scheme = NumberingScheme(name="test", description="d")
        for start in [10, 20, 30]:
            scheme.add_area(
                AreaDefinition(
                    area_range_start=start,
                    area_range_end=start + 9,
                    name=f"Area{start}",
                    description="d",
                )
            )
        areas = scheme.get_available_areas()
        assert len(areas) >= 3
        assert areas == sorted(areas)

    def test_get_default_scheme(self) -> None:
        """Verify get_default_scheme returns a non-empty scheme with at least one area."""
        from file_organizer.methodologies.johnny_decimal.categories import get_default_scheme

        scheme = get_default_scheme()
        assert scheme.name != ""
        areas = scheme.get_available_areas()
        assert len(areas) >= 1


# ---------------------------------------------------------------------------
# JohnnyDecimalGenerator
# ---------------------------------------------------------------------------


class TestJohnnyDecimalGenerator:
    """Tests for JohnnyDecimalGenerator."""

    def _make_scheme(self) -> object:
        from file_organizer.methodologies.johnny_decimal.categories import (
            AreaDefinition,
            NumberingScheme,
        )

        scheme = NumberingScheme(name="test", description="d")
        for start in [10, 20, 30]:
            scheme.add_area(
                AreaDefinition(
                    area_range_start=start,
                    area_range_end=start + 9,
                    name=f"Area{start}",
                    description="d",
                )
            )
        return scheme

    def test_generate_area_number(self) -> None:
        """Verify generate_area_number returns an AREA-level number."""
        from file_organizer.methodologies.johnny_decimal.numbering import (
            JohnnyDecimalGenerator,
        )

        scheme = self._make_scheme()
        gen = JohnnyDecimalGenerator(scheme)
        n = gen.generate_area_number(name="NewArea")
        assert n.level.value == "area"

    def test_is_number_available(self) -> None:
        """Verify an unregistered number is available."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )
        from file_organizer.methodologies.johnny_decimal.numbering import (
            JohnnyDecimalGenerator,
        )

        scheme = self._make_scheme()
        gen = JohnnyDecimalGenerator(scheme)
        n = JohnnyDecimalNumber(area=10)
        assert gen.is_number_available(n) is True

    def test_register_existing_number(self, tmp_path: Path) -> None:
        """Verify registering a number makes it unavailable and raises on duplicate."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )
        from file_organizer.methodologies.johnny_decimal.numbering import (
            JohnnyDecimalGenerator,
            NumberConflictError,
        )

        scheme = self._make_scheme()
        gen = JohnnyDecimalGenerator(scheme)
        n = JohnnyDecimalNumber(area=10)
        gen.register_existing_number(n, tmp_path / "file.txt")
        assert gen.is_number_available(n) is False
        with pytest.raises(NumberConflictError):
            gen.register_existing_number(n, tmp_path / "other.txt")

    def test_validate_number_valid(self) -> None:
        """Verify validate_number returns (True, []) for a valid area number in scheme."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )
        from file_organizer.methodologies.johnny_decimal.numbering import (
            JohnnyDecimalGenerator,
        )

        scheme = self._make_scheme()
        gen = JohnnyDecimalGenerator(scheme)
        n = JohnnyDecimalNumber(area=10)
        is_valid, errors = gen.validate_number(n)
        assert is_valid is True
        assert errors == []

    def test_clear_registrations(self, tmp_path: Path) -> None:
        """Verify clear_registrations makes previously registered numbers available again."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )
        from file_organizer.methodologies.johnny_decimal.numbering import (
            JohnnyDecimalGenerator,
        )

        scheme = self._make_scheme()
        gen = JohnnyDecimalGenerator(scheme)
        n = JohnnyDecimalNumber(area=10)
        gen.register_existing_number(n, tmp_path / "file.txt")
        gen.clear_registrations()
        assert gen.is_number_available(n) is True

    def test_get_usage_statistics(self, tmp_path: Path) -> None:
        """Verify get_usage_statistics reports total_numbers after registration."""
        from file_organizer.methodologies.johnny_decimal.categories import (
            JohnnyDecimalNumber,
        )
        from file_organizer.methodologies.johnny_decimal.numbering import (
            JohnnyDecimalGenerator,
        )

        scheme = self._make_scheme()
        gen = JohnnyDecimalGenerator(scheme)
        n = JohnnyDecimalNumber(area=10)
        gen.register_existing_number(n, tmp_path / "file.txt")
        stats = gen.get_usage_statistics()
        assert isinstance(stats, dict)
        assert stats["total_numbers"] == 1

    def test_suggest_number_for_content(self) -> None:
        """Verify suggest_number_for_content returns a confidence in [0,1] and a list."""
        from file_organizer.methodologies.johnny_decimal.numbering import (
            JohnnyDecimalGenerator,
        )

        scheme = self._make_scheme()
        gen = JohnnyDecimalGenerator(scheme)
        _number, confidence, reasons = gen.suggest_number_for_content(
            "invoice payment receipt", filename="invoice.pdf"
        )
        assert 0.0 <= confidence <= 1.0
        assert isinstance(reasons, list)


# ---------------------------------------------------------------------------
# JohnnyDecimalConfig & ConfigBuilder
# ---------------------------------------------------------------------------


class TestJohnnyDecimalConfig:
    """Tests for JohnnyDecimalConfig and ConfigBuilder."""

    def test_config_builder_basic(self) -> None:
        """Verify ConfigBuilder sets the scheme name correctly."""
        from file_organizer.methodologies.johnny_decimal.config import ConfigBuilder

        cfg = (
            ConfigBuilder("my-scheme")
            .add_area(10, "Finance", "Financial documents")
            .add_area(20, "Projects", "Project files")
            .build()
        )
        assert cfg.scheme.name == "my-scheme"

    def test_config_builder_with_category(self) -> None:
        """Verify add_category stores and retrieves the category by area and number."""
        from file_organizer.methodologies.johnny_decimal.config import ConfigBuilder

        cfg = (
            ConfigBuilder("scheme")
            .add_area(10, "Finance", "d")
            .add_category(10, 1, "Invoices", "Invoice files")
            .build()
        )
        cat = cfg.scheme.get_category(10, 1)
        assert cat is not None
        assert cat.name == "Invoices"

    def test_config_builder_migration_config(self) -> None:
        """Verify with_migration_config stores preserve_names and max_depth."""
        from file_organizer.methodologies.johnny_decimal.config import ConfigBuilder

        cfg = (
            ConfigBuilder("scheme")
            .with_migration_config(preserve_names=False, create_backups=False, max_depth=5)
            .build()
        )
        assert cfg.migration.preserve_original_names is False
        assert cfg.migration.max_depth == 5

    def test_config_builder_para_integration(self) -> None:
        """Verify with_para_integration enables PARA and sets projects_area."""
        from file_organizer.methodologies.johnny_decimal.config import ConfigBuilder

        cfg = ConfigBuilder("scheme").with_para_integration(enabled=True, projects_area=10).build()
        assert cfg.compatibility.para_integration.enabled is True
        assert cfg.compatibility.para_integration.projects_area == 10

    def test_create_default_config(self) -> None:
        """Verify create_default_config returns a JohnnyDecimalConfig instance."""
        from file_organizer.methodologies.johnny_decimal.config import (
            JohnnyDecimalConfig,
            create_default_config,
        )

        cfg = create_default_config()
        assert isinstance(cfg, JohnnyDecimalConfig)

    def test_create_para_compatible_config(self) -> None:
        """Verify create_para_compatible_config enables PARA integration."""
        from file_organizer.methodologies.johnny_decimal.config import (
            create_para_compatible_config,
        )

        cfg = create_para_compatible_config()
        assert cfg.compatibility.para_integration.enabled is True

    def test_config_to_dict_roundtrip(self) -> None:
        """Verify to_dict/from_dict round-trips to an equivalent config."""
        from file_organizer.methodologies.johnny_decimal.config import (
            JohnnyDecimalConfig,
            create_default_config,
        )

        cfg = create_default_config()
        data = cfg.to_dict()
        assert isinstance(data, dict)
        restored = JohnnyDecimalConfig.from_dict(data)
        assert isinstance(restored, JohnnyDecimalConfig)

    def test_config_save_and_load(self, tmp_path: Path) -> None:
        """Verify save_to_file writes a file and load_from_file restores a config."""
        from file_organizer.methodologies.johnny_decimal.config import (
            JohnnyDecimalConfig,
            create_default_config,
        )

        cfg = create_default_config()
        cfg_path = tmp_path / "jd_config.json"
        cfg.save_to_file(cfg_path)
        assert cfg_path.exists()
        loaded = JohnnyDecimalConfig.load_from_file(cfg_path)
        assert isinstance(loaded, JohnnyDecimalConfig)

    def test_migration_config_defaults(self) -> None:
        """Verify MigrationConfig defaults enable backups and skip hidden files."""
        from file_organizer.methodologies.johnny_decimal.config import MigrationConfig

        mc = MigrationConfig()
        assert mc.preserve_original_names is True
        assert mc.create_backups is True
        assert mc.skip_hidden is True

    def test_para_integration_config_defaults(self) -> None:
        """Verify PARAIntegrationConfig defaults to disabled with projects_area=10."""
        from file_organizer.methodologies.johnny_decimal.config import PARAIntegrationConfig

        pic = PARAIntegrationConfig()
        assert pic.enabled is False
        assert pic.projects_area == 10

    def test_compatibility_config_defaults(self) -> None:
        """Verify CompatibilityConfig defaults allow mixed structures and pre-migration validation."""
        from file_organizer.methodologies.johnny_decimal.config import CompatibilityConfig

        cc = CompatibilityConfig()
        assert cc.allow_mixed_structure is True
        assert cc.validate_before_migration is True


# ---------------------------------------------------------------------------
# PARAJohnnyDecimalBridge
# ---------------------------------------------------------------------------


class TestPARAJohnnyDecimalBridge:
    """Tests for PARAJohnnyDecimalBridge."""

    def _make_bridge(self) -> object:
        from file_organizer.methodologies.johnny_decimal.compatibility import (
            PARAJohnnyDecimalBridge,
        )
        from file_organizer.methodologies.johnny_decimal.config import PARAIntegrationConfig

        config = PARAIntegrationConfig(
            enabled=True, projects_area=10, areas_area=20, resources_area=30, archive_area=40
        )
        return PARAJohnnyDecimalBridge(config)

    def test_para_to_jd_area(self) -> None:
        """Verify PROJECTS category maps to area 10 as configured."""
        from file_organizer.methodologies.johnny_decimal.compatibility import PARACategory

        bridge = self._make_bridge()
        area = bridge.para_to_jd_area(PARACategory.PROJECTS)
        # _make_bridge() sets projects_area=10; index defaults to 0
        assert area == 10

    def test_jd_area_to_para(self) -> None:
        """Verify area 10 maps back to PROJECTS category."""
        from file_organizer.methodologies.johnny_decimal.compatibility import PARACategory

        bridge = self._make_bridge()
        category = bridge.jd_area_to_para(10)
        assert category == PARACategory.PROJECTS

    def test_is_para_area(self) -> None:
        """Verify is_para_area returns True for configured areas and False for others."""
        bridge = self._make_bridge()
        assert bridge.is_para_area(10) is True
        assert bridge.is_para_area(99) is False

    def test_get_para_path_suggestion(self) -> None:
        """Verify get_para_path_suggestion returns a non-empty string."""
        from file_organizer.methodologies.johnny_decimal.compatibility import PARACategory

        bridge = self._make_bridge()
        suggestion = bridge.get_para_path_suggestion(PARACategory.PROJECTS, "my-project")
        assert isinstance(suggestion, str)
        assert len(suggestion) > 0

    def test_create_para_structure(self, tmp_path: Path) -> None:
        """Verify create_para_structure creates dirs with JD-prefixed PARA names."""
        from file_organizer.methodologies.johnny_decimal.compatibility import (
            PARACategory,
            PARAJohnnyDecimalBridge,
        )
        from file_organizer.methodologies.johnny_decimal.config import PARAIntegrationConfig

        config = PARAIntegrationConfig(enabled=True)
        bridge = PARAJohnnyDecimalBridge(config)
        result = bridge.create_para_structure(tmp_path)
        assert isinstance(result, dict)
        # Default area mapping: projects=10, areas=20, resources=30, archive=40
        # Directory names are f"{area:02d} {category.value.title()}"
        assert result[PARACategory.PROJECTS].name == "10 Projects"
        assert result[PARACategory.AREAS].name == "20 Areas"
        assert result[PARACategory.RESOURCES].name == "30 Resources"
        assert result[PARACategory.ARCHIVE].name == "40 Archive"
        for cat in PARACategory:
            assert result[cat].is_dir()


# ---------------------------------------------------------------------------
# CompatibilityAnalyzer
# ---------------------------------------------------------------------------


class TestCompatibilityAnalyzer:
    """Tests for CompatibilityAnalyzer."""

    def test_detect_para_structure_empty_dir(self, tmp_path: Path) -> None:
        """Verify detect_para_structure returns a dict keyed by PARACategory."""
        from file_organizer.methodologies.johnny_decimal.compatibility import (
            CompatibilityAnalyzer,
            PARACategory,
        )
        from file_organizer.methodologies.johnny_decimal.config import create_para_compatible_config

        cfg = create_para_compatible_config()
        analyzer = CompatibilityAnalyzer(cfg)
        result = analyzer.detect_para_structure(tmp_path)
        assert all(isinstance(k, PARACategory) for k in result)

    def test_is_mixed_structure_empty(self, tmp_path: Path) -> None:
        """Verify is_mixed_structure returns False for an empty directory."""
        from file_organizer.methodologies.johnny_decimal.compatibility import (
            CompatibilityAnalyzer,
        )
        from file_organizer.methodologies.johnny_decimal.config import create_default_config

        cfg = create_default_config()
        analyzer = CompatibilityAnalyzer(cfg)
        result = analyzer.is_mixed_structure(tmp_path)
        assert result is False

    def test_suggest_migration_strategy(self, tmp_path: Path) -> None:
        """Verify suggest_migration_strategy returns a dict with recommendations list."""
        from file_organizer.methodologies.johnny_decimal.compatibility import (
            CompatibilityAnalyzer,
        )
        from file_organizer.methodologies.johnny_decimal.config import create_default_config

        cfg = create_default_config()
        analyzer = CompatibilityAnalyzer(cfg)
        strategy = analyzer.suggest_migration_strategy(tmp_path)
        assert isinstance(strategy, dict)
        assert "recommendations" in strategy
        assert isinstance(strategy["recommendations"], list)


# ---------------------------------------------------------------------------
# AdapterRegistry & PARAAdapter
# ---------------------------------------------------------------------------


class TestAdapters:
    """Tests for adapter classes."""

    def test_para_adapter_can_adapt(self) -> None:
        """Verify PARAAdapter.can_adapt returns True for an item with category 'projects'."""
        from file_organizer.methodologies.johnny_decimal.adapters import (
            OrganizationItem,
            PARAAdapter,
        )
        from file_organizer.methodologies.johnny_decimal.config import create_para_compatible_config

        cfg = create_para_compatible_config()
        adapter = PARAAdapter(cfg)
        item = OrganizationItem(
            name="project-doc.pdf",
            path=Path("docs/project-doc.pdf"),
            category="projects",
            metadata={},
        )
        assert adapter.can_adapt(item) is True

    def test_para_adapter_adapt_to_jd(self) -> None:
        """Verify PARAAdapter.adapt_to_jd returns a JohnnyDecimalNumber."""
        from file_organizer.methodologies.johnny_decimal.adapters import (
            OrganizationItem,
            PARAAdapter,
        )
        from file_organizer.methodologies.johnny_decimal.categories import JohnnyDecimalNumber
        from file_organizer.methodologies.johnny_decimal.config import create_para_compatible_config

        cfg = create_para_compatible_config()
        adapter = PARAAdapter(cfg)
        item = OrganizationItem(
            name="doc.pdf",
            path=Path("Projects/doc.pdf"),
            category="projects",
            metadata={},
        )
        result = adapter.adapt_to_jd(item)
        assert isinstance(result, JohnnyDecimalNumber)

    def test_filesystem_adapter_can_adapt_always(self) -> None:
        """Verify FileSystemAdapter.can_adapt returns True for any item."""
        from file_organizer.methodologies.johnny_decimal.adapters import (
            FileSystemAdapter,
            OrganizationItem,
        )
        from file_organizer.methodologies.johnny_decimal.config import create_default_config

        cfg = create_default_config()
        adapter = FileSystemAdapter(cfg)
        item = OrganizationItem(
            name="any-file.txt",
            path=Path("any-file.txt"),
            category="misc",
            metadata={},
        )
        assert adapter.can_adapt(item) is True

    def test_filesystem_adapter_adapt_to_jd(self) -> None:
        """Verify FileSystemAdapter.adapt_to_jd returns a JohnnyDecimalNumber."""
        from file_organizer.methodologies.johnny_decimal.adapters import (
            FileSystemAdapter,
            OrganizationItem,
        )
        from file_organizer.methodologies.johnny_decimal.categories import JohnnyDecimalNumber
        from file_organizer.methodologies.johnny_decimal.config import create_default_config

        cfg = create_default_config()
        adapter = FileSystemAdapter(cfg)
        item = OrganizationItem(
            name="document.txt",
            path=Path("document.txt"),
            category="general",
            metadata={},
        )
        result = adapter.adapt_to_jd(item)
        assert isinstance(result, JohnnyDecimalNumber)

    def test_create_default_registry(self) -> None:
        """Verify create_default_registry returns an AdapterRegistry instance."""
        from file_organizer.methodologies.johnny_decimal.adapters import (
            AdapterRegistry,
            create_default_registry,
        )
        from file_organizer.methodologies.johnny_decimal.config import create_default_config

        cfg = create_default_config()
        registry = create_default_registry(cfg)
        assert isinstance(registry, AdapterRegistry)

    def test_registry_adapt_to_jd(self) -> None:
        """Verify registry.adapt_to_jd returns None or a JohnnyDecimalNumber."""
        from file_organizer.methodologies.johnny_decimal.adapters import (
            OrganizationItem,
            create_default_registry,
        )
        from file_organizer.methodologies.johnny_decimal.categories import JohnnyDecimalNumber
        from file_organizer.methodologies.johnny_decimal.config import create_default_config

        cfg = create_default_config()
        registry = create_default_registry(cfg)
        item = OrganizationItem(
            name="file.txt",
            path=Path("file.txt"),
            category="general",
            metadata={},
        )
        result = registry.adapt_to_jd(item)
        assert result is None or isinstance(result, JohnnyDecimalNumber)


# ---------------------------------------------------------------------------
# ValidationIssue and ValidationResult
# ---------------------------------------------------------------------------


class TestValidationDataClasses:
    """Tests for validation-related data classes."""

    def test_validation_issue(self) -> None:
        """Verify ValidationIssue stores severity, rule_index, and message."""
        from file_organizer.methodologies.johnny_decimal.validator import ValidationIssue

        issue = ValidationIssue(
            severity="error",
            rule_index=0,
            message="Duplicate number detected",
            suggestion="Use a different number",
        )
        assert issue.severity == "error"
        assert issue.rule_index == 0
        assert "Duplicate" in issue.message

    def test_validation_result_add_issue(self) -> None:
        """Verify add_issue separates errors and warnings into respective lists."""
        from file_organizer.methodologies.johnny_decimal.validator import (
            ValidationIssue,
            ValidationResult,
        )

        result = ValidationResult(is_valid=True)
        error = ValidationIssue(severity="error", rule_index=0, message="err")
        warning = ValidationIssue(severity="warning", rule_index=1, message="warn")
        result.add_issue(error)
        result.add_issue(warning)
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert len(result.issues) == 2

    def test_validation_result_empty(self) -> None:
        """Verify a freshly constructed ValidationResult has no issues."""
        from file_organizer.methodologies.johnny_decimal.validator import ValidationResult

        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert len(result.issues) == 0
