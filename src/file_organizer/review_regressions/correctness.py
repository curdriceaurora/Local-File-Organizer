"""Correctness detector pack for legacy review-regression audits."""

from __future__ import annotations

import ast
from pathlib import Path

from file_organizer.review_regressions.framework import (
    ReviewRegressionDetector,
    Violation,
    fingerprint_ast_node,
    iter_python_files,
    parse_python_ast,
)

_SOURCE_ROOT = Path("src/file_organizer")
_VALIDATED_STAGE_FIELDS = {"category", "filename"}


def _iter_correctness_python_files(root: Path) -> list[Path]:
    source_root = root / _SOURCE_ROOT
    scan_root = source_root if source_root.exists() else root
    return iter_python_files(scan_root)


def _call_matches_object_setattr(node: ast.Call) -> bool:
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "__setattr__"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "object"
    )


def _stage_field_name(node: ast.Call) -> str | None:
    if len(node.args) < 2:
        return None
    field = node.args[1]
    if isinstance(field, ast.Constant) and isinstance(field.value, str):
        return field.value
    return None


def _is_active_models_target(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "_active_models"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
    )


def _is_primitive_model_assignment(value: ast.AST) -> bool:
    if isinstance(value, ast.Constant):
        return isinstance(value.value, (str, int, float, bool))
    return isinstance(value, ast.Name) and value.id.endswith("_id")


class StageContextValidationBypassDetector:
    """Invariant: StageContext.category/filename must validate through __setattr__."""

    detector_id = "correctness.stage-context-validation-bypass"
    rule_class = "correctness"
    description = (
        "Flags object.__setattr__ writes to StageContext validated fields that bypass "
        "the assignment-time path-traversal guard."
    )

    def find_violations(self, root: Path) -> list[Violation]:
        """Return StageContext validated-field writes that bypass __setattr__."""
        findings: list[Violation] = []
        for path in _iter_correctness_python_files(root):
            tree = parse_python_ast(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not _call_matches_object_setattr(node):
                    continue
                field_name = _stage_field_name(node)
                if field_name not in _VALIDATED_STAGE_FIELDS:
                    continue
                findings.append(
                    Violation.from_path(
                        detector_id=self.detector_id,
                        rule_class=self.rule_class,
                        rule_id="validated-field-setattr-bypass",
                        root=root,
                        path=path,
                        line=node.lineno,
                        message=(
                            f"object.__setattr__ writes StageContext.{field_name} directly; "
                            "validated fields must flow through StageContext.__setattr__."
                        ),
                        fingerprint_basis=fingerprint_ast_node(node),
                    )
                )

        return sorted(findings, key=lambda finding: finding.sort_key())


class ActiveModelPrimitiveStoreDetector:
    """Invariant: ModelManager._active_models may hold only live model instances."""

    detector_id = "correctness.active-model-primitive-store"
    rule_class = "correctness"
    description = (
        "Flags primitive-like values written into _active_models, which breaks the "
        "loaded-model registry contract for get_active_model()."
    )

    def find_violations(self, root: Path) -> list[Violation]:
        """Return _active_models writes that store primitive-like values."""
        findings: list[Violation] = []
        for path in _iter_correctness_python_files(root):
            tree = parse_python_ast(path)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                target = node.targets[0]
                if not _is_active_models_target(target):
                    continue
                if not _is_primitive_model_assignment(node.value):
                    continue

                rendered_value = ast.unparse(node.value)
                findings.append(
                    Violation.from_path(
                        detector_id=self.detector_id,
                        rule_class=self.rule_class,
                        rule_id="primitive-active-model-store",
                        root=root,
                        path=path,
                        line=node.lineno,
                        message=(
                            f"_active_models stores {rendered_value}; registry entries must hold "
                            "live model instances or be removed."
                        ),
                        fingerprint_basis=fingerprint_ast_node(node),
                    )
                )

        return sorted(findings, key=lambda finding: finding.sort_key())


CORRECTNESS_DETECTORS: tuple[ReviewRegressionDetector, ...] = (
    StageContextValidationBypassDetector(),
    ActiveModelPrimitiveStoreDetector(),
)
