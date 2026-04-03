"""Tests for Johnny Decimal validator uncovered branches.

Targets: ValidationResult.add_issue info branch, _check_source_paths,
_check_number_conflicts, _check_target_name_conflicts existing target,
_check_number_validity ranges, _check_filesystem_compatibility long names
and spaces, _check_nested_conflicts, generate_report all sections.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.methodologies.johnny_decimal.categories import (
    JohnnyDecimalNumber,
    get_default_scheme,
)
from file_organizer.methodologies.johnny_decimal.numbering import JohnnyDecimalGenerator
from file_organizer.methodologies.johnny_decimal.system import JohnnyDecimalSystem
from file_organizer.methodologies.johnny_decimal.transformer import (
    TransformationPlan,
    TransformationRule,
)
from file_organizer.methodologies.johnny_decimal.validator import (
    MigrationValidator,
    ValidationIssue,
    ValidationResult,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def validator() -> MigrationValidator:
    scheme = get_default_scheme()
    gen = JohnnyDecimalGenerator(scheme)
    return MigrationValidator(gen)


class TestValidationResult:
    """Cover add_issue branches — lines 48."""

    def test_add_info_issue(self) -> None:
        result = ValidationResult(is_valid=True)
        issue = ValidationIssue(severity="info", rule_index=0, message="info msg")
        result.add_issue(issue)
        assert len(result.info) == 1
        assert result.is_valid is True  # info doesn't invalidate

    def test_add_error_invalidates(self) -> None:
        result = ValidationResult(is_valid=True)
        issue = ValidationIssue(severity="error", rule_index=0, message="error msg")
        result.add_issue(issue)
        assert result.is_valid is False

    def test_add_warning(self) -> None:
        result = ValidationResult(is_valid=True)
        issue = ValidationIssue(severity="warning", rule_index=0, message="warn msg")
        result.add_issue(issue)
        assert len(result.warnings) == 1
        assert result.is_valid is True


class TestCheckSourcePaths:
    """Cover _check_source_paths — lines 97, 107."""

    def test_nonexistent_source(self, validator: MigrationValidator) -> None:
        """Source path doesn't exist => error (line 97)."""
        rule = TransformationRule(
            source_path=Path("/nonexistent/folder"),
            target_name="10 Folder",
            jd_number=JohnnyDecimalNumber(area=10),
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=Path("/"), rules=[rule], estimated_changes=1)
        result = validator.validate_plan(plan)
        assert len(result.errors) >= 1

    def test_file_not_dir_source(self, validator: MigrationValidator, tmp_path: Path) -> None:
        """Source is file not dir => error (line 107)."""
        f = tmp_path / "file.txt"
        f.write_text("content")
        rule = TransformationRule(
            source_path=f,
            target_name="10 File",
            jd_number=JohnnyDecimalNumber(area=10),
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)
        result = validator.validate_plan(plan)
        has_not_dir = any("not a directory" in e.message for e in result.errors)
        assert has_not_dir


class TestCheckNumberConflicts:
    """Cover _check_number_conflicts — line 138."""

    def test_duplicate_number_in_plan(self, validator: MigrationValidator, tmp_path: Path) -> None:
        """Same JD number used twice => error (line 124)."""
        d1 = tmp_path / "d1"
        d1.mkdir()
        d2 = tmp_path / "d2"
        d2.mkdir()
        jd_num = JohnnyDecimalNumber(area=10)
        rule1 = TransformationRule(
            source_path=d1, target_name="10 D1", jd_number=jd_num, action="rename", confidence=0.8
        )
        rule2 = TransformationRule(
            source_path=d2, target_name="10 D2", jd_number=jd_num, action="rename", confidence=0.8
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule1, rule2], estimated_changes=2)
        result = validator.validate_plan(plan)
        dup_errors = [e for e in result.errors if "Duplicate JD number" in e.message]
        assert len(dup_errors) >= 1


class TestCheckTargetNameConflicts:
    """Cover _check_target_name_conflicts — lines 179, 195."""

    def test_existing_target_path_warning(
        self, validator: MigrationValidator, tmp_path: Path
    ) -> None:
        """Target path exists and differs from source => warning (line 179)."""
        src = tmp_path / "Finance"
        src.mkdir()
        existing = tmp_path / "10 Finance"
        existing.mkdir()

        rule = TransformationRule(
            source_path=src,
            target_name="10 Finance",
            jd_number=JohnnyDecimalNumber(area=10),
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)
        result = validator.validate_plan(plan)
        target_warns = [w for w in result.warnings if "already exists" in w.message]
        assert len(target_warns) >= 1


class TestCheckNumberValidity:
    """Cover _check_number_validity — lines 195, 207, 219."""

    def test_area_out_of_range(self, validator: MigrationValidator, tmp_path: Path) -> None:
        d = tmp_path / "d"
        d.mkdir()
        rule = TransformationRule(
            source_path=d,
            target_name="05 Bad",
            jd_number=JohnnyDecimalNumber(area=5),
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)
        result = validator.validate_plan(plan)
        area_errors = [e for e in result.errors if "Area number out of range" in e.message]
        assert len(area_errors) >= 1

    def test_category_out_of_range(self, validator: MigrationValidator, tmp_path: Path) -> None:
        d = tmp_path / "d"
        d.mkdir()
        rule = TransformationRule(
            source_path=d,
            target_name="10.00 Bad",
            jd_number=JohnnyDecimalNumber(area=10, category=0),
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)
        result = validator.validate_plan(plan)
        cat_errors = [e for e in result.errors if "Category number out of range" in e.message]
        assert len(cat_errors) >= 1

    def test_id_out_of_range(self, validator: MigrationValidator, tmp_path: Path) -> None:
        d = tmp_path / "d"
        d.mkdir()
        rule = TransformationRule(
            source_path=d,
            target_name="10.01.0000 Bad",
            jd_number=JohnnyDecimalNumber(area=10, category=1, item_id=0),
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)
        result = validator.validate_plan(plan)
        id_errors = [e for e in result.errors if "ID number out of range" in e.message]
        assert len(id_errors) >= 1


class TestCheckFilesystemCompatibility:
    """Cover _check_filesystem_compatibility — lines 241, 252, 263."""

    def test_invalid_char_in_name(self, validator: MigrationValidator, tmp_path: Path) -> None:
        d = tmp_path / "d"
        d.mkdir()
        rule = TransformationRule(
            source_path=d,
            target_name="10 Finance/Budget",
            jd_number=JohnnyDecimalNumber(area=10),
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)
        result = validator.validate_plan(plan)
        char_errors = [e for e in result.errors if "invalid character" in e.message]
        assert len(char_errors) >= 1

    def test_very_long_name_warning(self, validator: MigrationValidator, tmp_path: Path) -> None:
        d = tmp_path / "d"
        d.mkdir()
        long_name = "10 " + "A" * 250
        rule = TransformationRule(
            source_path=d,
            target_name=long_name,
            jd_number=JohnnyDecimalNumber(area=10),
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)
        result = validator.validate_plan(plan)
        long_warns = [w for w in result.warnings if "very long" in w.message]
        assert len(long_warns) >= 1

    def test_leading_trailing_spaces_warning(
        self, validator: MigrationValidator, tmp_path: Path
    ) -> None:
        d = tmp_path / "d"
        d.mkdir()
        rule = TransformationRule(
            source_path=d,
            target_name=" 10 Finance ",
            jd_number=JohnnyDecimalNumber(area=10),
            action="rename",
            confidence=0.8,
        )
        plan = TransformationPlan(root_path=tmp_path, rules=[rule], estimated_changes=1)
        result = validator.validate_plan(plan)
        space_warns = [w for w in result.warnings if "leading/trailing spaces" in w.message]
        assert len(space_warns) >= 1


class TestCheckNestedConflicts:
    """Cover _check_nested_conflicts — lines 313."""

    def test_nested_transformation_warning(
        self, validator: MigrationValidator, tmp_path: Path
    ) -> None:
        parent = tmp_path / "Finance"
        parent.mkdir()
        child = parent / "Budgets"
        child.mkdir()

        rules = [
            TransformationRule(
                source_path=parent,
                target_name="10 Finance",
                jd_number=JohnnyDecimalNumber(area=10),
                action="rename",
                confidence=0.8,
            ),
            TransformationRule(
                source_path=child,
                target_name="10.01 Budgets",
                jd_number=JohnnyDecimalNumber(area=10, category=1),
                action="rename",
                confidence=0.7,
            ),
        ]
        plan = TransformationPlan(root_path=tmp_path, rules=rules, estimated_changes=2)
        result = validator.validate_plan(plan)
        nested_warns = [w for w in result.warnings if "Nested transformation" in w.message]
        assert len(nested_warns) >= 1


class TestGenerateReport:
    """Cover generate_report branches — lines 326-331, 342-345."""

    def test_report_valid_plan(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=True)
        report = validator.generate_report(result)
        assert "VALID" in report

    def test_report_invalid_with_errors_and_warnings(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=True)
        result.add_issue(
            ValidationIssue(severity="error", rule_index=0, message="err1", suggestion="fix1")
        )
        result.add_issue(
            ValidationIssue(severity="warning", rule_index=1, message="warn1", suggestion="fix2")
        )
        result.add_issue(ValidationIssue(severity="info", rule_index=2, message="info1"))
        report = validator.generate_report(result)
        assert "ERRORS" in report
        assert "err1" in report
        assert "warn1" in report
        assert "info1" in report


class TestValidatorCoverage:
    """Cover all missing lines in validator.py."""

    @pytest.fixture
    def validator(self) -> MigrationValidator:
        scheme = JohnnyDecimalSystem().scheme
        gen = JohnnyDecimalGenerator(scheme)
        return MigrationValidator(gen)

    # Line 138: number conflicts with existing assignment
    def test_validate_plan_existing_conflict(
        self, validator: MigrationValidator, tmp_path: Path
    ) -> None:
        # Register a number first
        num = JohnnyDecimalNumber(area=10, category=1)
        validator.generator.register_existing_number(num, Path("existing.txt"))

        rule = TransformationRule(
            source_path=tmp_path / "test",
            target_name="10.01 Test",
            jd_number=JohnnyDecimalNumber(area=10, category=1),
            action="rename",
            confidence=0.9,
        )
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[rule],
            estimated_changes=1,
        )
        result = validator.validate_plan(plan)
        assert not result.is_valid
        error_msgs = [e.message for e in result.errors]
        assert any("already in use" in m for m in error_msgs)

    # Branch 331->329: generate_report with no errors (skip errors section)
    def test_generate_report_no_errors(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=True)
        result.add_issue(
            ValidationIssue(
                severity="warning",
                rule_index=0,
                message="Just a warning",
                suggestion="Fix it",
            )
        )
        report = validator.generate_report(result)
        assert "Warnings" in report
        assert "Errors (Must Fix)" not in report

    # Branch 339->337: generate_report with no warnings (skip warnings section)
    def test_generate_report_no_warnings(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=False)
        result.add_issue(
            ValidationIssue(
                severity="error",
                rule_index=0,
                message="An error",
                suggestion="Fix it",
            )
        )
        report = validator.generate_report(result)
        assert "Errors" in report
        assert "Warnings (Should Review)" not in report

    # Also test info section present
    def test_generate_report_with_info(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=True)
        result.add_issue(
            ValidationIssue(
                severity="info",
                rule_index=0,
                message="Info note",
                suggestion=None,
            )
        )
        report = validator.generate_report(result)
        assert "Info" in report

    # Branches 331->329, 339->337: error/warning without suggestion
    def test_generate_report_error_no_suggestion(self, validator: MigrationValidator) -> None:
        result = ValidationResult(is_valid=False)
        result.add_issue(
            ValidationIssue(
                severity="error",
                rule_index=0,
                message="Error without tip",
                suggestion=None,
            )
        )
        result.add_issue(
            ValidationIssue(
                severity="warning",
                rule_index=1,
                message="Warning without tip",
                suggestion=None,
            )
        )
        report = validator.generate_report(result)
        assert "Error without tip" in report
        assert "Warning without tip" in report
        # No suggestion line should appear
        assert "\u0020\u0020\U0001f4a1" not in report  # no lightbulb suggestion line
