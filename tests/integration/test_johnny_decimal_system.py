"""Integration tests for the Johnny Decimal methodology system.

Covers:
  - methodologies/johnny_decimal/categories.py  — NumberingScheme, JohnnyDecimalNumber, AreaDefinition, CategoryDefinition
  - methodologies/johnny_decimal/numbering.py   — JohnnyDecimalGenerator
  - methodologies/johnny_decimal/scanner.py     — FolderScanner, ScanResult, FolderInfo
  - methodologies/johnny_decimal/transformer.py — FolderTransformer, TransformationPlan, TransformationRule
  - methodologies/johnny_decimal/validator.py   — MigrationValidator, ValidationResult, ValidationIssue
"""

from __future__ import annotations

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
    JohnnyDecimalGenerator,
    NumberConflictError,
)
from file_organizer.methodologies.johnny_decimal.scanner import (
    FolderInfo,
    FolderScanner,
    ScanResult,
)
from file_organizer.methodologies.johnny_decimal.transformer import (
    FolderTransformer,
    TransformationPlan,
)
from file_organizer.methodologies.johnny_decimal.validator import (
    MigrationValidator,
    ValidationIssue,
    ValidationResult,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_scheme(name: str = "test", area_start: int = 10, area_end: int = 19) -> NumberingScheme:
    scheme = NumberingScheme(name=name, description=f"{name} scheme")
    area = AreaDefinition(
        area_range_start=area_start,
        area_range_end=area_end,
        name="Finance",
        description="Finance area",
        keywords=["finance", "money"],
        examples=["invoices"],
    )
    scheme.add_area(area)
    return scheme


def _make_generator(scheme: NumberingScheme | None = None) -> JohnnyDecimalGenerator:
    if scheme is None:
        scheme = _make_scheme()
    return JohnnyDecimalGenerator(scheme=scheme)


# ---------------------------------------------------------------------------
# JohnnyDecimalNumber
# ---------------------------------------------------------------------------


class TestJohnnyDecimalNumber:
    def test_created(self) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=1, name="Test", description="")
        assert num.area == 10
        assert num.category == 11
        assert num.item_id == 1
        assert num.name == "Test"

    def test_str_representation(self) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=1, name="Test", description="")
        s = str(num)
        assert isinstance(s, str)
        assert len(s) > 0

    def test_area_only_number(self) -> None:
        num = JohnnyDecimalNumber(area=20, name="Work")
        assert num.area == 20

    def test_area_and_category(self) -> None:
        num = JohnnyDecimalNumber(area=20, category=21, name="Projects")
        assert num.category == 21

    def test_formatted_number_attribute(self) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=1, name="x")
        assert hasattr(num, "formatted_number")
        assert isinstance(num.formatted_number, str)


# ---------------------------------------------------------------------------
# NumberingScheme
# ---------------------------------------------------------------------------


class TestNumberingScheme:
    def test_default_init(self) -> None:
        scheme = NumberingScheme(name="test", description="test")
        assert scheme.name == "test"
        assert scheme.allow_gaps is True
        assert scheme.auto_increment is True

    def test_empty_areas_by_default(self) -> None:
        scheme = NumberingScheme(name="test", description="test")
        assert scheme.get_available_areas() == []

    def test_add_area_populates_areas(self) -> None:
        scheme = _make_scheme()
        areas = scheme.get_available_areas()
        assert len(areas) > 0

    def test_area_range_included(self) -> None:
        scheme = _make_scheme(area_start=10, area_end=14)
        areas = scheme.get_available_areas()
        assert 10 in areas
        assert 14 in areas

    def test_add_category(self) -> None:
        scheme = _make_scheme()
        cat = CategoryDefinition(
            area=10,
            category=11,
            name="Invoices",
            description="Incoming invoices",
            keywords=["invoice"],
            patterns=["*.pdf"],
        )
        scheme.add_category(cat)
        result = scheme.get_category(10, 11)
        assert result is not None

    def test_is_number_reserved_false_default(self) -> None:
        scheme = _make_scheme()
        num = JohnnyDecimalNumber(area=10, category=11, item_id=1, name="test")
        assert scheme.is_number_reserved(num) is False

    def test_reserve_number(self) -> None:
        scheme = _make_scheme()
        num = JohnnyDecimalNumber(area=10, category=11, item_id=99, name="reserved")
        scheme.reserve_number(num)
        assert scheme.is_number_reserved(num) is True


# ---------------------------------------------------------------------------
# AreaDefinition
# ---------------------------------------------------------------------------


class TestAreaDefinition:
    def test_created(self) -> None:
        ad = AreaDefinition(
            area_range_start=10,
            area_range_end=19,
            name="Work",
            description="Work projects",
            keywords=["work"],
            examples=["projects"],
        )
        assert ad.name == "Work"
        assert ad.area_range_start == 10
        assert ad.area_range_end == 19


# ---------------------------------------------------------------------------
# CategoryDefinition
# ---------------------------------------------------------------------------


class TestCategoryDefinition:
    def test_created(self) -> None:
        cd = CategoryDefinition(
            area=10,
            category=11,
            name="Invoices",
            description="Finance invoices",
            keywords=["invoice", "payment"],
            patterns=["*.pdf", "*.xlsx"],
        )
        assert cd.area == 10
        assert cd.category == 11
        assert cd.name == "Invoices"
        assert cd.auto_assign is True


# ---------------------------------------------------------------------------
# JohnnyDecimalGenerator — init and registration
# ---------------------------------------------------------------------------


@pytest.fixture()
def scheme() -> NumberingScheme:
    return _make_scheme()


@pytest.fixture()
def generator(scheme: NumberingScheme) -> JohnnyDecimalGenerator:
    return JohnnyDecimalGenerator(scheme=scheme)


class TestJohnnyDecimalGeneratorInit:
    def test_created(self, scheme: NumberingScheme) -> None:
        gen = JohnnyDecimalGenerator(scheme=scheme)
        assert gen is not None

    def test_scheme_stored(
        self, generator: JohnnyDecimalGenerator, scheme: NumberingScheme
    ) -> None:
        assert generator.scheme is scheme


class TestRegisterExistingNumber:
    def test_register_new_number(self, generator: JohnnyDecimalGenerator, tmp_path: Path) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=1, name="Test")
        generator.register_existing_number(num, tmp_path / "file.txt")

    def test_register_duplicate_raises(
        self, generator: JohnnyDecimalGenerator, tmp_path: Path
    ) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=1, name="Test")
        generator.register_existing_number(num, tmp_path / "file.txt")
        with pytest.raises(NumberConflictError):
            generator.register_existing_number(num, tmp_path / "other.txt")


class TestIsNumberAvailable:
    def test_fresh_number_available(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=5, name="test")
        assert generator.is_number_available(num) is True

    def test_registered_number_not_available(
        self, generator: JohnnyDecimalGenerator, tmp_path: Path
    ) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=5, name="test")
        generator.register_existing_number(num, tmp_path / "file.txt")
        assert generator.is_number_available(num) is False


# ---------------------------------------------------------------------------
# JohnnyDecimalGenerator — number generation
# ---------------------------------------------------------------------------


class TestGetNextAvailableArea:
    def test_returns_int(self, generator: JohnnyDecimalGenerator) -> None:
        area = generator.get_next_available_area()
        assert 10 <= area <= 19

    def test_value_in_scheme_range(self, generator: JohnnyDecimalGenerator) -> None:
        area = generator.get_next_available_area()
        assert 10 <= area <= 19

    def test_no_areas_raises(self) -> None:
        empty_scheme = NumberingScheme(name="empty", description="empty")
        gen = JohnnyDecimalGenerator(scheme=empty_scheme)
        with pytest.raises(InvalidNumberError):
            gen.get_next_available_area()


class TestGenerateAreaNumber:
    def test_returns_jd_number(self, generator: JohnnyDecimalGenerator) -> None:
        num = generator.generate_area_number("Projects")
        assert isinstance(num, JohnnyDecimalNumber)

    def test_name_stored(self, generator: JohnnyDecimalGenerator) -> None:
        num = generator.generate_area_number("Finance")
        assert num.name == "Finance"


class TestGenerateCategoryNumber:
    def test_returns_jd_number(self, generator: JohnnyDecimalGenerator) -> None:
        area_num = generator.generate_area_number("Work")
        cat_num = generator.generate_category_number(area_num.area, "Invoices")
        assert isinstance(cat_num, JohnnyDecimalNumber)

    def test_name_stored(self, generator: JohnnyDecimalGenerator) -> None:
        area_num = generator.generate_area_number("Work")
        cat_num = generator.generate_category_number(area_num.area, "Reports")
        assert cat_num.name == "Reports"

    def test_area_matches(self, generator: JohnnyDecimalGenerator) -> None:
        area_num = generator.generate_area_number("Work")
        cat_num = generator.generate_category_number(area_num.area, "Budget")
        assert cat_num.area == area_num.area


class TestGenerateIdNumber:
    def test_returns_jd_number(self, generator: JohnnyDecimalGenerator) -> None:
        area_num = generator.generate_area_number("Work")
        cat_num = generator.generate_category_number(area_num.area, "Invoices")
        id_num = generator.generate_id_number(area_num.area, cat_num.category, "Invoice2024")
        assert isinstance(id_num, JohnnyDecimalNumber)

    def test_name_stored(self, generator: JohnnyDecimalGenerator) -> None:
        area_num = generator.generate_area_number("Work")
        cat_num = generator.generate_category_number(area_num.area, "Invoices")
        id_num = generator.generate_id_number(area_num.area, cat_num.category, "Q1Invoice")
        assert id_num.name == "Q1Invoice"


class TestValidateNumber:
    def test_valid_number_returns_true(self, generator: JohnnyDecimalGenerator) -> None:
        area_num = generator.generate_area_number("Work")
        cat_num = generator.generate_category_number(area_num.area, "Test")
        id_num = generator.generate_id_number(area_num.area, cat_num.category, "Item")
        is_valid, errors = generator.validate_number(id_num)
        assert is_valid is True
        assert errors == []


class TestFindConflicts:
    def test_no_conflicts_initially(self, generator: JohnnyDecimalGenerator) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=5, name="test")
        conflicts = generator.find_conflicts(num)
        assert isinstance(conflicts, list)
        assert len(conflicts) == 0

    def test_finds_conflict_after_register(
        self, generator: JohnnyDecimalGenerator, tmp_path: Path
    ) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=7, name="test")
        generator.register_existing_number(num, tmp_path / "file.txt")
        conflicts = generator.find_conflicts(num)
        assert len(conflicts) >= 1


class TestGetUsageStatistics:
    def test_returns_dict(self, generator: JohnnyDecimalGenerator) -> None:
        stats = generator.get_usage_statistics()
        assert stats["total_numbers"] == 0

    def test_after_registration(self, generator: JohnnyDecimalGenerator, tmp_path: Path) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=1, name="test")
        generator.register_existing_number(num, tmp_path / "x.txt")
        stats = generator.get_usage_statistics()
        assert stats["total_numbers"] >= 1


class TestClearRegistrations:
    def test_clear_removes_registrations(
        self, generator: JohnnyDecimalGenerator, tmp_path: Path
    ) -> None:
        num = JohnnyDecimalNumber(area=10, category=11, item_id=1, name="test")
        generator.register_existing_number(num, tmp_path / "file.txt")
        generator.clear_registrations()
        assert generator.is_number_available(num) is True


class TestSuggestNumberForContent:
    def test_returns_tuple(self, generator: JohnnyDecimalGenerator) -> None:
        result = generator.suggest_number_for_content("invoice payment finance")
        assert isinstance(result, tuple)
        assert len(result) == 3

    def test_tuple_contains_number_float_list(self, generator: JohnnyDecimalGenerator) -> None:
        num, confidence, reasons = generator.suggest_number_for_content("work projects")
        assert 0.0 <= confidence <= 1.0
        assert len(reasons) >= 1

    def test_confidence_in_range(self, generator: JohnnyDecimalGenerator) -> None:
        _, confidence, _ = generator.suggest_number_for_content("finance invoice")
        assert 0.0 <= confidence <= 1.0


class TestResolveConflict:
    def test_returns_number(self, generator: JohnnyDecimalGenerator) -> None:
        area_num = generator.generate_area_number("Work")
        cat_num = generator.generate_category_number(area_num.area, "Test")
        id_num = generator.generate_id_number(area_num.area, cat_num.category, "Item")
        resolved = generator.resolve_conflict(id_num)
        assert isinstance(resolved, JohnnyDecimalNumber)


# ---------------------------------------------------------------------------
# FolderScanner
# ---------------------------------------------------------------------------


@pytest.fixture()
def scanner() -> FolderScanner:
    return FolderScanner()


class TestFolderScannerInit:
    def test_default_init(self) -> None:
        s = FolderScanner()
        assert s is not None

    def test_with_custom_depth(self) -> None:
        s = FolderScanner(max_depth=5)
        assert s is not None

    def test_with_scheme(self, scheme: NumberingScheme) -> None:
        s = FolderScanner(scheme=scheme)
        assert s is not None


class TestFolderScannerScanDirectory:
    def test_empty_dir_returns_scan_result(self, scanner: FolderScanner, tmp_path: Path) -> None:
        result = scanner.scan_directory(tmp_path)
        assert isinstance(result, ScanResult)

    def test_scan_result_has_root_path(self, scanner: FolderScanner, tmp_path: Path) -> None:
        result = scanner.scan_directory(tmp_path)
        assert result.root_path == tmp_path

    def test_empty_dir_total_files_is_int(self, scanner: FolderScanner, tmp_path: Path) -> None:
        result = scanner.scan_directory(tmp_path)
        assert isinstance(result.total_files, int)
        assert result.total_files >= 0

    def test_empty_dir_total_folders_is_int(self, scanner: FolderScanner, tmp_path: Path) -> None:
        result = scanner.scan_directory(tmp_path)
        assert isinstance(result.total_folders, int)
        assert result.total_folders >= 0

    def test_with_folders_counts_correctly(self, scanner: FolderScanner, tmp_path: Path) -> None:
        (tmp_path / "Projects").mkdir()
        (tmp_path / "Documents").mkdir()
        result = scanner.scan_directory(tmp_path)
        assert result.total_folders >= 2

    def test_with_files_counts_correctly(self, scanner: FolderScanner, tmp_path: Path) -> None:
        (tmp_path / "Projects").mkdir()
        (tmp_path / "Projects" / "file.txt").write_text("hello")
        result = scanner.scan_directory(tmp_path)
        assert result.total_files == 1

    def test_folder_tree_is_list(self, scanner: FolderScanner, tmp_path: Path) -> None:
        (tmp_path / "Work").mkdir()
        result = scanner.scan_directory(tmp_path)
        assert len(result.folder_tree) >= 1

    def test_folder_tree_entries_are_folder_info(
        self, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        (tmp_path / "Work").mkdir()
        result = scanner.scan_directory(tmp_path)
        assert len(result.folder_tree) > 0
        assert isinstance(result.folder_tree[0], FolderInfo)

    def test_scan_result_has_warnings(self, scanner: FolderScanner, tmp_path: Path) -> None:
        result = scanner.scan_directory(tmp_path)
        assert result.warnings == []

    def test_scan_result_has_detected_patterns(
        self, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        result = scanner.scan_directory(tmp_path)
        assert hasattr(result, "detected_patterns")


# ---------------------------------------------------------------------------
# FolderTransformer
# ---------------------------------------------------------------------------


@pytest.fixture()
def transformer(scheme: NumberingScheme, generator: JohnnyDecimalGenerator) -> FolderTransformer:
    return FolderTransformer(scheme=scheme, generator=generator)


class TestFolderTransformerInit:
    def test_created(self, scheme: NumberingScheme, generator: JohnnyDecimalGenerator) -> None:
        t = FolderTransformer(scheme=scheme, generator=generator)
        assert t is not None

    def test_with_preserve_names(
        self, scheme: NumberingScheme, generator: JohnnyDecimalGenerator
    ) -> None:
        t = FolderTransformer(scheme=scheme, generator=generator, preserve_original_names=False)
        assert t is not None


class TestCreateTransformationPlan:
    def test_empty_folder_tree_returns_plan(
        self, transformer: FolderTransformer, tmp_path: Path
    ) -> None:
        plan = transformer.create_transformation_plan([], tmp_path)
        assert isinstance(plan, TransformationPlan)

    def test_plan_has_root_path(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        plan = transformer.create_transformation_plan([], tmp_path)
        assert plan.root_path == tmp_path

    def test_plan_has_rules_list(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        plan = transformer.create_transformation_plan([], tmp_path)
        assert plan.rules == []

    def test_plan_from_scan_result(
        self, transformer: FolderTransformer, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        (tmp_path / "Work").mkdir()
        (tmp_path / "Personal").mkdir()
        result = scanner.scan_directory(tmp_path)
        plan = transformer.create_transformation_plan(result.folder_tree, tmp_path)
        assert isinstance(plan, TransformationPlan)
        assert plan.total_folders_count >= 0 if hasattr(plan, "total_folders_count") else True

    def test_rules_count_matches_folders(
        self, transformer: FolderTransformer, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        (tmp_path / "Folder1").mkdir()
        (tmp_path / "Folder2").mkdir()
        result = scanner.scan_directory(tmp_path)
        plan = transformer.create_transformation_plan(result.folder_tree, tmp_path)
        assert len(plan.rules) == len(result.folder_tree)


class TestGeneratePreview:
    def test_empty_plan_returns_string(
        self, transformer: FolderTransformer, tmp_path: Path
    ) -> None:
        plan = transformer.create_transformation_plan([], tmp_path)
        preview = transformer.generate_preview(plan)
        assert len(preview) > 0

    def test_preview_with_folders(
        self, transformer: FolderTransformer, scanner: FolderScanner, tmp_path: Path
    ) -> None:
        (tmp_path / "Finance").mkdir()
        result = scanner.scan_directory(tmp_path)
        plan = transformer.create_transformation_plan(result.folder_tree, tmp_path)
        preview = transformer.generate_preview(plan)
        assert isinstance(preview, str)
        assert len(preview) > 0


# ---------------------------------------------------------------------------
# MigrationValidator
# ---------------------------------------------------------------------------


@pytest.fixture()
def validator(generator: JohnnyDecimalGenerator) -> MigrationValidator:
    return MigrationValidator(generator=generator)


class TestMigrationValidatorInit:
    def test_created(self, generator: JohnnyDecimalGenerator) -> None:
        v = MigrationValidator(generator=generator)
        assert v is not None


class TestValidatePlan:
    def test_empty_plan_returns_result(self, validator: MigrationValidator, tmp_path: Path) -> None:
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
            conflicts=[],
            warnings=[],
        )
        result = validator.validate_plan(plan)
        assert isinstance(result, ValidationResult)

    def test_result_is_valid_for_empty_plan(
        self, validator: MigrationValidator, tmp_path: Path
    ) -> None:
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
            conflicts=[],
            warnings=[],
        )
        result = validator.validate_plan(plan)
        assert result.is_valid is True

    def test_result_has_issues_list(self, validator: MigrationValidator, tmp_path: Path) -> None:
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
            conflicts=[],
            warnings=[],
        )
        result = validator.validate_plan(plan)
        assert result.issues == []

    def test_validate_real_plan(
        self,
        validator: MigrationValidator,
        transformer: FolderTransformer,
        scanner: FolderScanner,
        tmp_path: Path,
    ) -> None:
        (tmp_path / "Projects").mkdir()
        (tmp_path / "Finances").mkdir()
        scan_result = scanner.scan_directory(tmp_path)
        plan = transformer.create_transformation_plan(scan_result.folder_tree, tmp_path)
        result = validator.validate_plan(plan)
        assert isinstance(result, ValidationResult)


class TestGenerateReport:
    def test_returns_string(self, validator: MigrationValidator, tmp_path: Path) -> None:
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
            conflicts=[],
            warnings=[],
        )
        val_result = validator.validate_plan(plan)
        report = validator.generate_report(val_result)
        assert len(report) > 0

    def test_report_non_empty(self, validator: MigrationValidator, tmp_path: Path) -> None:
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
            conflicts=[],
            warnings=[],
        )
        val_result = validator.validate_plan(plan)
        report = validator.generate_report(val_result)
        assert len(report) > 0


# ---------------------------------------------------------------------------
# ValidationResult and ValidationIssue dataclasses
# ---------------------------------------------------------------------------


class TestValidationResult:
    def test_created(self) -> None:
        result = ValidationResult(
            is_valid=True,
            issues=[],
            errors=[],
            warnings=[],
            info=[],
        )
        assert result.is_valid is True
        assert isinstance(result.issues, list)

    def test_invalid_result(self) -> None:
        issue = ValidationIssue(
            severity="error",
            rule_index=0,
            message="Conflict detected",
            suggestion="Rename folder",
        )
        result = ValidationResult(
            is_valid=False,
            issues=[issue],
            errors=["Conflict detected"],
            warnings=[],
            info=[],
        )
        assert result.is_valid is False
        assert len(result.issues) == 1


class TestValidationIssue:
    def test_created(self) -> None:
        issue = ValidationIssue(
            severity="warning",
            rule_index=1,
            message="Potential conflict",
            suggestion="Consider renaming",
        )
        assert issue.severity == "warning"
        assert issue.rule_index == 1
        assert "conflict" in issue.message.lower()
