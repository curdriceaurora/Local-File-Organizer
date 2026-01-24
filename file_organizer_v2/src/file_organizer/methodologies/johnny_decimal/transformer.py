"""
Johnny Decimal Folder Transformer

Transforms existing folder structures to Johnny Decimal naming convention.
Handles renaming, restructuring, and maintains file integrity.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .categories import JohnnyDecimalNumber, NumberingScheme, NumberLevel
from .numbering import JohnnyDecimalGenerator
from .scanner import FolderInfo

logger = logging.getLogger(__name__)


@dataclass
class TransformationRule:
    """Rule for transforming a folder to Johnny Decimal format."""

    source_path: Path
    target_name: str
    jd_number: JohnnyDecimalNumber
    action: str  # "rename", "move", "restructure"
    confidence: float
    reasoning: List[str] = field(default_factory=list)


@dataclass
class TransformationPlan:
    """Complete plan for transforming a folder structure."""

    root_path: Path
    rules: List[TransformationRule]
    estimated_changes: int
    conflicts: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class FolderTransformer:
    """
    Transforms existing folder structures to Johnny Decimal format.

    Creates transformation plans that map existing folders to
    appropriate Johnny Decimal numbers while preserving content.
    """

    def __init__(
        self,
        scheme: NumberingScheme,
        generator: JohnnyDecimalGenerator,
        preserve_original_names: bool = True,
    ):
        """
        Initialize the folder transformer.

        Args:
            scheme: Johnny Decimal numbering scheme
            generator: Number generator for assignments
            preserve_original_names: Keep original names after JD number
        """
        self.scheme = scheme
        self.generator = generator
        self.preserve_original_names = preserve_original_names

    def create_transformation_plan(
        self,
        folder_tree: List[FolderInfo],
        root_path: Path,
    ) -> TransformationPlan:
        """
        Create a transformation plan for a folder structure.

        Args:
            folder_tree: Scanned folder tree from FolderScanner
            root_path: Root directory path

        Returns:
            TransformationPlan with all transformation rules
        """
        logger.info(f"Creating transformation plan for {root_path}")

        rules: List[TransformationRule] = []
        conflicts: List[str] = []
        warnings: List[str] = []

        # Transform top-level folders as Areas (10-99)
        for idx, folder in enumerate(folder_tree):
            try:
                rule = self._create_area_rule(folder, idx)
                rules.append(rule)

                # Transform children as Categories
                if folder.children:
                    child_rules = self._create_category_rules(folder.children, rule.jd_number)
                    rules.extend(child_rules)

            except Exception as e:
                conflict = f"Failed to transform {folder.name}: {str(e)}"
                conflicts.append(conflict)
                logger.error(conflict)

        # Check for naming conflicts
        target_names = [r.target_name for r in rules]
        duplicates = [name for name in target_names if target_names.count(name) > 1]
        if duplicates:
            warnings.append(f"Duplicate target names detected: {set(duplicates)}")

        plan = TransformationPlan(
            root_path=root_path,
            rules=rules,
            estimated_changes=len(rules),
            conflicts=conflicts,
            warnings=warnings,
        )

        logger.info(f"Plan created: {len(rules)} transformations, {len(conflicts)} conflicts")

        return plan

    def _create_area_rule(self, folder: FolderInfo, suggested_index: int) -> TransformationRule:
        """
        Create transformation rule for an area-level folder.

        Args:
            folder: Folder information
            suggested_index: Suggested area index (0-9 for areas 10-19, etc.)

        Returns:
            TransformationRule for this folder
        """
        # Determine area number based on folder characteristics
        area_number = self._suggest_area_number(folder, suggested_index)

        # Create JD number
        jd_number = JohnnyDecimalNumber(
            area=area_number, category=None, id_number=None, level=NumberLevel.AREA
        )

        # Create target name
        if self.preserve_original_names:
            target_name = f"{area_number:02d} {folder.name}"
        else:
            target_name = f"{area_number:02d}"

        rule = TransformationRule(
            source_path=folder.path,
            target_name=target_name,
            jd_number=jd_number,
            action="rename",
            confidence=0.8,
            reasoning=[
                f"Assigned to area {area_number}",
                f"Original name: {folder.name}",
            ],
        )

        return rule

    def _create_category_rules(
        self,
        children: List[FolderInfo],
        parent_number: JohnnyDecimalNumber,
    ) -> List[TransformationRule]:
        """
        Create transformation rules for category-level folders.

        Args:
            children: Child folders to transform
            parent_number: Parent area number

        Returns:
            List of transformation rules
        """
        rules = []

        for idx, child in enumerate(children):
            category_number = self._suggest_category_number(
                child, parent_number.area, idx
            )

            jd_number = JohnnyDecimalNumber(
                area=parent_number.area,
                category=category_number,
                id_number=None,
                level=NumberLevel.CATEGORY,
            )

            if self.preserve_original_names:
                target_name = f"{parent_number.area:02d}.{category_number:02d} {child.name}"
            else:
                target_name = f"{parent_number.area:02d}.{category_number:02d}"

            rule = TransformationRule(
                source_path=child.path,
                target_name=target_name,
                jd_number=jd_number,
                action="rename",
                confidence=0.7,
                reasoning=[
                    f"Category {category_number} in area {parent_number.area}",
                    f"Original name: {child.name}",
                ],
            )

            rules.append(rule)

            # Handle deeper nesting (convert to IDs)
            if child.children:
                id_rules = self._create_id_rules(child.children, jd_number)
                rules.extend(id_rules)

        return rules

    def _create_id_rules(
        self,
        children: List[FolderInfo],
        parent_number: JohnnyDecimalNumber,
    ) -> List[TransformationRule]:
        """
        Create transformation rules for ID-level folders.

        Args:
            children: Child folders to transform
            parent_number: Parent category number

        Returns:
            List of transformation rules
        """
        rules = []

        for idx, child in enumerate(children):
            id_number = idx + 1  # IDs start at 001

            jd_number = JohnnyDecimalNumber(
                area=parent_number.area,
                category=parent_number.category,
                id_number=id_number,
                level=NumberLevel.ID,
            )

            if self.preserve_original_names:
                target_name = (
                    f"{parent_number.area:02d}.{parent_number.category:02d}."
                    f"{id_number:03d} {child.name}"
                )
            else:
                target_name = (
                    f"{parent_number.area:02d}.{parent_number.category:02d}."
                    f"{id_number:03d}"
                )

            rule = TransformationRule(
                source_path=child.path,
                target_name=target_name,
                jd_number=jd_number,
                action="rename",
                confidence=0.6,
                reasoning=[
                    f"ID {id_number} in category {parent_number.area}.{parent_number.category}",
                    f"Original name: {child.name}",
                    "Deep nesting converted to ID level",
                ],
            )

            rules.append(rule)

        return rules

    def _suggest_area_number(self, folder: FolderInfo, index: int) -> int:
        """
        Suggest an area number based on folder characteristics.

        Args:
            folder: Folder information
            index: Index in folder list

        Returns:
            Suggested area number (10-99)
        """
        # Check scheme for predefined area mappings
        folder_name_lower = folder.name.lower()

        # Try to match with scheme areas
        if self.scheme.areas:
            for area in self.scheme.areas:
                if area.title.lower() in folder_name_lower or folder_name_lower in area.title.lower():
                    return area.area_number

        # Default: assign sequentially starting from 10
        base_area = 10
        return base_area + index

    def _suggest_category_number(self, folder: FolderInfo, area: int, index: int) -> int:
        """
        Suggest a category number based on folder characteristics.

        Args:
            folder: Folder information
            area: Parent area number
            index: Index in folder list

        Returns:
            Suggested category number (01-99)
        """
        # Check scheme for predefined category mappings
        folder_name_lower = folder.name.lower()

        # Try to match with scheme categories
        if self.scheme.categories:
            for category in self.scheme.categories:
                if (
                    category.area_number == area
                    and (
                        category.title.lower() in folder_name_lower
                        or folder_name_lower in category.title.lower()
                    )
                ):
                    return category.category_number

        # Default: assign sequentially starting from 01
        return index + 1

    def generate_preview(self, plan: TransformationPlan) -> str:
        """
        Generate human-readable preview of transformation plan.

        Args:
            plan: Transformation plan

        Returns:
            Formatted preview string
        """
        lines = [
            "# Johnny Decimal Transformation Plan",
            "",
            f"Root: {plan.root_path}",
            f"Total transformations: {len(plan.rules)}",
            "",
        ]

        if plan.warnings:
            lines.append("## Warnings")
            for warning in plan.warnings:
                lines.append(f"⚠️  {warning}")
            lines.append("")

        if plan.conflicts:
            lines.append("## Conflicts")
            for conflict in plan.conflicts:
                lines.append(f"❌ {conflict}")
            lines.append("")

        lines.append("## Transformations")
        lines.append("")

        # Group by area
        area_rules: Dict[int, List[TransformationRule]] = {}
        for rule in plan.rules:
            area = rule.jd_number.area
            if area not in area_rules:
                area_rules[area] = []
            area_rules[area].append(rule)

        for area, rules in sorted(area_rules.items()):
            lines.append(f"### Area {area:02d}")
            for rule in rules:
                lines.append(f"- {rule.source_path.name} → {rule.target_name}")
            lines.append("")

        return "\n".join(lines)
