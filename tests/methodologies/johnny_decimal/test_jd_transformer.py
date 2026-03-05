"""Tests for Johnny Decimal transformer uncovered branches.

Targets: _create_area_rule exception, duplicate target names warning,
_create_category_rules preserve_original_names=False,
_create_id_rules preserve_original_names=False,
generate_preview warnings/conflicts sections.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.methodologies.johnny_decimal.categories import (
    JohnnyDecimalNumber,
    get_default_scheme,
)
from file_organizer.methodologies.johnny_decimal.numbering import JohnnyDecimalGenerator
from file_organizer.methodologies.johnny_decimal.scanner import FolderInfo
from file_organizer.methodologies.johnny_decimal.transformer import (
    FolderTransformer,
    TransformationPlan,
    TransformationRule,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def scheme():
    return get_default_scheme()


@pytest.fixture
def generator(scheme):
    return JohnnyDecimalGenerator(scheme)


@pytest.fixture
def transformer(scheme, generator):
    return FolderTransformer(scheme, generator)


@pytest.fixture
def transformer_no_preserve(scheme, generator):
    return FolderTransformer(scheme, generator, preserve_original_names=False)


class TestCreateTransformationPlan:
    """Cover create_transformation_plan — lines 98-101, 107."""

    def test_area_rule_exception_becomes_conflict(
        self, transformer: FolderTransformer, tmp_path: Path
    ) -> None:
        """Exception in _create_area_rule adds to conflicts (lines 98-101)."""
        folder = FolderInfo(path=tmp_path / "Finance", name="Finance", depth=0)
        with patch.object(transformer, "_create_area_rule", side_effect=RuntimeError("boom")):
            plan = transformer.create_transformation_plan([folder], tmp_path)
        assert len(plan.conflicts) >= 1
        assert "boom" in plan.conflicts[0]

    def test_duplicate_target_names_warning(
        self, transformer: FolderTransformer, tmp_path: Path
    ) -> None:
        """Duplicate target names produce warning (line 107)."""
        folders = [
            FolderInfo(path=tmp_path / "A", name="A", depth=0),
            FolderInfo(path=tmp_path / "B", name="B", depth=0),
        ]
        # Patch to produce same target name for both
        with patch.object(
            transformer,
            "_create_area_rule",
            side_effect=[
                TransformationRule(
                    source_path=tmp_path / "A",
                    target_name="10 Same",
                    jd_number=JohnnyDecimalNumber(area=10),
                    action="rename",
                    confidence=0.8,
                ),
                TransformationRule(
                    source_path=tmp_path / "B",
                    target_name="10 Same",
                    jd_number=JohnnyDecimalNumber(area=11),
                    action="rename",
                    confidence=0.8,
                ),
            ],
        ):
            plan = transformer.create_transformation_plan(folders, tmp_path)
        assert len(plan.warnings) >= 1
        assert "Duplicate" in plan.warnings[0]

    def test_basic_plan_with_children(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        """Plan includes category rules for children."""
        child = FolderInfo(path=tmp_path / "A" / "sub", name="sub", depth=1)
        folder = FolderInfo(path=tmp_path / "A", name="A", depth=0, children=[child])
        plan = transformer.create_transformation_plan([folder], tmp_path)
        assert len(plan.rules) >= 2  # area + category


class TestCreateAreaRule:
    """Cover _create_area_rule — line 141 (preserve_original_names=False)."""

    def test_preserve_original_names_true(
        self, transformer: FolderTransformer, tmp_path: Path
    ) -> None:
        folder = FolderInfo(path=tmp_path / "Finance", name="Finance", depth=0)
        rule = transformer._create_area_rule(folder, 0)
        assert "Finance" in rule.target_name

    def test_preserve_original_names_false(
        self, transformer_no_preserve: FolderTransformer, tmp_path: Path
    ) -> None:
        """Line 141: target_name is just the number."""
        folder = FolderInfo(path=tmp_path / "Finance", name="Finance", depth=0)
        rule = transformer_no_preserve._create_area_rule(folder, 0)
        assert "Finance" not in rule.target_name
        assert rule.target_name.strip().isdigit()


class TestCreateCategoryRules:
    """Cover _create_category_rules — line 185 (preserve=False)."""

    def test_preserve_names_true(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        child = FolderInfo(path=tmp_path / "Budgets", name="Budgets", depth=1)
        parent = JohnnyDecimalNumber(area=10)
        rules = transformer._create_category_rules([child], parent)
        assert len(rules) == 1
        assert "Budgets" in rules[0].target_name

    def test_preserve_names_false(
        self, transformer_no_preserve: FolderTransformer, tmp_path: Path
    ) -> None:
        """Line 185: target_name is just area.category."""
        child = FolderInfo(path=tmp_path / "Budgets", name="Budgets", depth=1)
        parent = JohnnyDecimalNumber(area=10)
        rules = transformer_no_preserve._create_category_rules([child], parent)
        assert len(rules) == 1
        assert "Budgets" not in rules[0].target_name

    def test_with_grandchildren(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        """Children with their own children generate ID rules."""
        grandchild = FolderInfo(path=tmp_path / "Budgets" / "Q1", name="Q1", depth=2)
        child = FolderInfo(
            path=tmp_path / "Budgets",
            name="Budgets",
            depth=1,
            children=[grandchild],
        )
        parent = JohnnyDecimalNumber(area=10)
        rules = transformer._create_category_rules([child], parent)
        assert len(rules) == 2  # category + ID


class TestCreateIdRules:
    """Cover _create_id_rules — line 239 (preserve=False)."""

    def test_preserve_names_true(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        child = FolderInfo(path=tmp_path / "Q1", name="Q1", depth=2)
        parent = JohnnyDecimalNumber(area=10, category=1)
        rules = transformer._create_id_rules([child], parent)
        assert len(rules) == 1
        assert "Q1" in rules[0].target_name

    def test_preserve_names_false(
        self, transformer_no_preserve: FolderTransformer, tmp_path: Path
    ) -> None:
        """Line 239: target_name is just area.category.id."""
        child = FolderInfo(path=tmp_path / "Q1", name="Q1", depth=2)
        parent = JohnnyDecimalNumber(area=10, category=1)
        rules = transformer_no_preserve._create_id_rules([child], parent)
        assert len(rules) == 1
        assert "Q1" not in rules[0].target_name

    def test_multiple_children(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        children = [
            FolderInfo(path=tmp_path / f"item{i}", name=f"item{i}", depth=2) for i in range(3)
        ]
        parent = JohnnyDecimalNumber(area=10, category=1)
        rules = transformer._create_id_rules(children, parent)
        assert len(rules) == 3
        ids = [r.jd_number.item_id for r in rules]
        assert ids == [1, 2, 3]


class TestGeneratePreview:
    """Cover generate_preview — lines 303-308, 332-335, 338-341."""

    def test_preview_with_warnings(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        """Lines 332-335: Warnings section in preview."""
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
            warnings=["Duplicate target names detected"],
        )
        preview = transformer.generate_preview(plan)
        assert "Warnings" in preview
        assert "Duplicate" in preview

    def test_preview_with_conflicts(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        """Lines 338-341: Conflicts section in preview."""
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
            conflicts=["Failed to transform Docs: error"],
        )
        preview = transformer.generate_preview(plan)
        assert "Conflicts" in preview
        assert "Failed to transform" in preview

    def test_preview_with_rules(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        """Lines 303-308: Rules grouped by area."""
        rules = [
            TransformationRule(
                source_path=tmp_path / "Finance",
                target_name="10 Finance",
                jd_number=JohnnyDecimalNumber(area=10),
                action="rename",
                confidence=0.8,
            ),
            TransformationRule(
                source_path=tmp_path / "Projects",
                target_name="20 Projects",
                jd_number=JohnnyDecimalNumber(area=20),
                action="rename",
                confidence=0.8,
            ),
        ]
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=rules,
            estimated_changes=2,
        )
        preview = transformer.generate_preview(plan)
        assert "Area 10" in preview
        assert "Area 20" in preview
        assert "Finance" in preview
        assert "Projects" in preview

    def test_preview_empty_plan(self, transformer: FolderTransformer, tmp_path: Path) -> None:
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
        )
        preview = transformer.generate_preview(plan)
        assert "Total transformations: 0" in preview

    def test_preview_warnings_and_conflicts_together(
        self, transformer: FolderTransformer, tmp_path: Path
    ) -> None:
        """Both warnings and conflicts appear."""
        plan = TransformationPlan(
            root_path=tmp_path,
            rules=[],
            estimated_changes=0,
            warnings=["warn1"],
            conflicts=["conflict1"],
        )
        preview = transformer.generate_preview(plan)
        assert "Warnings" in preview
        assert "Conflicts" in preview
        assert "warn1" in preview
        assert "conflict1" in preview
