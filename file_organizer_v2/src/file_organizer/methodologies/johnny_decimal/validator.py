"""
Johnny Decimal Migration Validator

Validates transformation plans before execution to prevent errors and data loss.
Checks for conflicts, invalid numbers, and potential issues.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from .numbering import JohnnyDecimalGenerator
from .transformer import TransformationPlan, TransformationRule

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """Represents a validation issue found in a transformation plan."""

    severity: str  # "error", "warning", "info"
    rule_index: int
    message: str
    suggestion: str = ""


@dataclass
class ValidationResult:
    """Result of validating a transformation plan."""

    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    errors: List[ValidationIssue] = field(default_factory=list)
    warnings: List[ValidationIssue] = field(default_factory=list)
    info: List[ValidationIssue] = field(default_factory=list)

    def add_issue(self, issue: ValidationIssue) -> None:
        """Add an issue and categorize it."""
        self.issues.append(issue)
        if issue.severity == "error":
            self.errors.append(issue)
            self.is_valid = False
        elif issue.severity == "warning":
            self.warnings.append(issue)
        else:
            self.info.append(issue)


class MigrationValidator:
    """
    Validates Johnny Decimal transformation plans.

    Checks for number conflicts, invalid paths, naming issues,
    and potential data loss scenarios.
    """

    def __init__(self, generator: JohnnyDecimalGenerator):
        """
        Initialize the validator.

        Args:
            generator: JD number generator with existing numbers registered
        """
        self.generator = generator

    def validate_plan(self, plan: TransformationPlan) -> ValidationResult:
        """
        Validate a transformation plan.

        Args:
            plan: Transformation plan to validate

        Returns:
            ValidationResult with all issues found
        """
        logger.info(f"Validating transformation plan with {len(plan.rules)} rules")

        result = ValidationResult(is_valid=True)

        # Run validation checks
        self._check_source_paths(plan, result)
        self._check_number_conflicts(plan, result)
        self._check_target_name_conflicts(plan, result)
        self._check_number_validity(plan, result)
        self._check_filesystem_compatibility(plan, result)
        self._check_nested_conflicts(plan, result)

        logger.info(
            f"Validation complete: {len(result.errors)} errors, "
            f"{len(result.warnings)} warnings"
        )

        return result

    def _check_source_paths(
        self, plan: TransformationPlan, result: ValidationResult
    ) -> None:
        """Check that all source paths exist and are accessible."""
        for idx, rule in enumerate(plan.rules):
            if not rule.source_path.exists():
                result.add_issue(
                    ValidationIssue(
                        severity="error",
                        rule_index=idx,
                        message=f"Source path does not exist: {rule.source_path}",
                        suggestion="Remove this rule or update the source path",
                    )
                )

            if not rule.source_path.is_dir():
                result.add_issue(
                    ValidationIssue(
                        severity="error",
                        rule_index=idx,
                        message=f"Source path is not a directory: {rule.source_path}",
                        suggestion="Only directories can be transformed",
                    )
                )

    def _check_number_conflicts(
        self, plan: TransformationPlan, result: ValidationResult
    ) -> None:
        """Check for Johnny Decimal number conflicts."""
        used_numbers: Set[str] = set()

        for idx, rule in enumerate(plan.rules):
            number_str = rule.jd_number.formatted_number

            # Check if number already used in plan
            if number_str in used_numbers:
                result.add_issue(
                    ValidationIssue(
                        severity="error",
                        rule_index=idx,
                        message=f"Duplicate JD number in plan: {number_str}",
                        suggestion="Assign a different number to avoid conflict",
                    )
                )
            else:
                used_numbers.add(number_str)

            # Check if number conflicts with existing assignments
            if not self.generator.is_number_available(rule.jd_number):
                result.add_issue(
                    ValidationIssue(
                        severity="error",
                        rule_index=idx,
                        message=f"JD number already in use: {number_str}",
                        suggestion="Choose an available number",
                    )
                )

    def _check_target_name_conflicts(
        self, plan: TransformationPlan, result: ValidationResult
    ) -> None:
        """Check for target name conflicts in same directory."""
        # Group rules by parent directory
        by_parent: dict[Path, List[tuple[int, TransformationRule]]] = {}

        for idx, rule in enumerate(plan.rules):
            parent = rule.source_path.parent
            if parent not in by_parent:
                by_parent[parent] = []
            by_parent[parent].append((idx, rule))

        # Check for name conflicts within each parent
        for parent, rules_list in by_parent.items():
            target_names = [rule.target_name for _, rule in rules_list]
            seen = set()

            for idx, rule in rules_list:
                if rule.target_name in seen:
                    result.add_issue(
                        ValidationIssue(
                            severity="error",
                            rule_index=idx,
                            message=f"Duplicate target name in {parent}: {rule.target_name}",
                            suggestion="Ensure unique names within same directory",
                        )
                    )
                seen.add(rule.target_name)

                # Check if target would conflict with existing folders
                target_path = parent / rule.target_name
                if target_path.exists() and target_path != rule.source_path:
                    result.add_issue(
                        ValidationIssue(
                            severity="warning",
                            rule_index=idx,
                            message=f"Target path already exists: {target_path}",
                            suggestion="May need to merge or rename existing folder",
                    )
                )

    def _check_number_validity(
        self, plan: TransformationPlan, result: ValidationResult
    ) -> None:
        """Check that JD numbers are valid and in proper ranges."""
        for idx, rule in enumerate(plan.rules):
            jd_num = rule.jd_number

            # Check area range (10-99)
            if not (10 <= jd_num.area <= 99):
                result.add_issue(
                    ValidationIssue(
                        severity="error",
                        rule_index=idx,
                        message=f"Area number out of range: {jd_num.area} (must be 10-99)",
                        suggestion="Use area numbers between 10 and 99",
                    )
                )

            # Check category range if present (01-99)
            if jd_num.category is not None:
                if not (1 <= jd_num.category <= 99):
                    result.add_issue(
                        ValidationIssue(
                            severity="error",
                            rule_index=idx,
                            message=f"Category number out of range: {jd_num.category} (must be 01-99)",
                            suggestion="Use category numbers between 01 and 99",
                        )
                    )

            # Check ID range if present (001-999)
            if jd_num.id_number is not None:
                if not (1 <= jd_num.id_number <= 999):
                    result.add_issue(
                        ValidationIssue(
                            severity="error",
                            rule_index=idx,
                            message=f"ID number out of range: {jd_num.id_number} (must be 001-999)",
                            suggestion="Use ID numbers between 001 and 999",
                        )
                    )

    def _check_filesystem_compatibility(
        self, plan: TransformationPlan, result: ValidationResult
    ) -> None:
        """Check that target names are filesystem-compatible."""
        # Characters that may cause issues
        problematic_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']

        for idx, rule in enumerate(plan.rules):
            target_name = rule.target_name

            # Check for problematic characters
            for char in problematic_chars:
                if char in target_name:
                    result.add_issue(
                        ValidationIssue(
                            severity="error",
                            rule_index=idx,
                            message=f"Target name contains invalid character '{char}': {target_name}",
                            suggestion="Remove or replace invalid characters",
                        )
                    )

            # Check for overly long names (filesystem limit typically 255)
            if len(target_name) > 200:
                result.add_issue(
                    ValidationIssue(
                        severity="warning",
                        rule_index=idx,
                        message=f"Target name is very long ({len(target_name)} chars): {target_name}",
                        suggestion="Consider shorter names to avoid filesystem limits",
                    )
                )

            # Check for names starting/ending with spaces
            if target_name.startswith(" ") or target_name.endswith(" "):
                result.add_issue(
                    ValidationIssue(
                        severity="warning",
                        rule_index=idx,
                        message=f"Target name has leading/trailing spaces: '{target_name}'",
                        suggestion="Remove leading/trailing spaces",
                    )
                )

    def _check_nested_conflicts(
        self, plan: TransformationPlan, result: ValidationResult
    ) -> None:
        """Check for issues with nested transformations."""
        # Build path hierarchy
        all_paths = {rule.source_path for rule in plan.rules}

        for idx, rule in enumerate(plan.rules):
            # Check if any path is a parent of this path
            for other_path in all_paths:
                if other_path != rule.source_path:
                    try:
                        rule.source_path.relative_to(other_path)
                        # This path is under other_path
                        result.add_issue(
                            ValidationIssue(
                                severity="warning",
                                rule_index=idx,
                                message=f"Nested transformation: {rule.source_path.name} is under another transformed folder",
                                suggestion="Ensure parent folder is transformed first",
                            )
                        )
                    except ValueError:
                        # Not a subdirectory, continue
                        pass

    def generate_report(self, result: ValidationResult) -> str:
        """
        Generate human-readable validation report.

        Args:
            result: Validation result

        Returns:
            Formatted report string
        """
        lines = [
            "# Transformation Plan Validation Report",
            "",
        ]

        if result.is_valid:
            lines.append("✅ **Plan is VALID** - Ready for execution")
        else:
            lines.append("❌ **Plan has ERRORS** - Cannot execute until resolved")

        lines.extend([
            "",
            f"- Errors: {len(result.errors)}",
            f"- Warnings: {len(result.warnings)}",
            f"- Info: {len(result.info)}",
            "",
        ])

        if result.errors:
            lines.append("## Errors (Must Fix)")
            for issue in result.errors:
                lines.append(f"- **Rule {issue.rule_index}**: {issue.message}")
                if issue.suggestion:
                    lines.append(f"  💡 {issue.suggestion}")
            lines.append("")

        if result.warnings:
            lines.append("## Warnings (Should Review)")
            for issue in result.warnings:
                lines.append(f"- **Rule {issue.rule_index}**: {issue.message}")
                if issue.suggestion:
                    lines.append(f"  💡 {issue.suggestion}")
            lines.append("")

        if result.info:
            lines.append("## Info")
            for issue in result.info:
                lines.append(f"- {issue.message}")
            lines.append("")

        return "\n".join(lines)
