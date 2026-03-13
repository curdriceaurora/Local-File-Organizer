"""Correctness detector pack for legacy review-regression audits."""

from __future__ import annotations

import ast
from collections.abc import Iterable
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
_PRIMITIVE_TYPES = {"bool", "float", "int", "str"}


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


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _stage_context_aliases(tree: ast.AST) -> set[str]:
    aliases = {"StageContext"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "file_organizer.interfaces.pipeline":
            for alias in node.names:
                if alias.name == "StageContext":
                    aliases.add(alias.asname or alias.name)
    return aliases


def _is_name_annotation(node: ast.AST, names: set[str]) -> bool:
    return isinstance(node, ast.Name) and node.id in names


def _is_stage_context_annotation(node: ast.AST | None, aliases: set[str]) -> bool:
    if node is None:
        return False
    if _is_name_annotation(node, aliases):
        return True
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value in aliases
    return False


def _is_stage_context_constructor(node: ast.AST, aliases: set[str]) -> bool:
    return isinstance(node, ast.Call) and _is_name_annotation(node.func, aliases)


def _stage_context_names(tree: ast.AST, aliases: set[str]) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
                if _is_stage_context_annotation(arg.annotation, aliases):
                    names.add(arg.arg)
            if node.args.vararg and _is_stage_context_annotation(
                node.args.vararg.annotation, aliases
            ):
                names.add(node.args.vararg.arg)
            if node.args.kwarg and _is_stage_context_annotation(
                node.args.kwarg.annotation, aliases
            ):
                names.add(node.args.kwarg.arg)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if _is_stage_context_annotation(node.annotation, aliases) or (
                node.value is not None and _is_stage_context_constructor(node.value, aliases)
            ):
                names.add(node.target.id)
        elif isinstance(node, ast.Assign) and _is_stage_context_constructor(node.value, aliases):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _stage_field_name(node: ast.Call) -> str | None:
    if len(node.args) < 2:
        return None
    field = node.args[1]
    if isinstance(field, ast.Constant) and isinstance(field.value, str):
        return field.value
    return None


def _setattr_target_name(node: ast.Call) -> str | None:
    if not node.args:
        return None
    target = node.args[0]
    if isinstance(target, ast.Name):
        return target.id
    return None


def _is_active_models_target(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "_active_models"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "self"
    )


def _annotation_contains_primitive(node: ast.AST | None) -> bool:
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id in _PRIMITIVE_TYPES
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value in _PRIMITIVE_TYPES
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _annotation_contains_primitive(node.left) or _annotation_contains_primitive(
            node.right
        )
    if isinstance(node, ast.Subscript):
        return _annotation_contains_primitive(node.slice)
    if isinstance(node, ast.Tuple):
        return any(_annotation_contains_primitive(elt) for elt in node.elts)
    return False


def _is_primitive_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool))


def _iter_scope_nodes(scope: ast.AST) -> Iterable[ast.AST]:
    if isinstance(scope, ast.Module):
        stack = list(reversed(scope.body))
    elif isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        stack = list(reversed(scope.body))
    else:
        return []

    nodes: list[ast.AST] = []
    while stack:
        node = stack.pop()
        nodes.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        children = list(ast.iter_child_nodes(node))
        stack.extend(reversed(children))
    return nodes


def _primitive_like_names(scope: ast.AST) -> set[str]:
    primitive_names: set[str] = set()

    if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
        for arg in (*scope.args.posonlyargs, *scope.args.args, *scope.args.kwonlyargs):
            if _annotation_contains_primitive(arg.annotation):
                primitive_names.add(arg.arg)
        if scope.args.vararg and _annotation_contains_primitive(scope.args.vararg.annotation):
            primitive_names.add(scope.args.vararg.arg)
        if scope.args.kwarg and _annotation_contains_primitive(scope.args.kwarg.annotation):
            primitive_names.add(scope.args.kwarg.arg)

    changed = True
    while changed:
        changed = False
        for node in _iter_scope_nodes(scope):
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if _annotation_contains_primitive(node.annotation) or (
                    node.value is not None
                    and _is_primitive_model_assignment(node.value, primitive_names)
                ):
                    changed |= node.target.id not in primitive_names
                    primitive_names.add(node.target.id)
            elif isinstance(node, ast.Assign) and _is_primitive_model_assignment(
                node.value, primitive_names
            ):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        changed |= target.id not in primitive_names
                        primitive_names.add(target.id)
    return primitive_names


def _enclosing_scope(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> ast.AST:
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)):
            return current
    raise ValueError("AST node has no enclosing scope")


def _enclosing_class_name(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str | None:
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if isinstance(current, ast.ClassDef):
            return current.name
    return None


def _is_primitive_model_assignment(value: ast.AST, primitive_names: set[str]) -> bool:
    if isinstance(value, ast.Constant):
        return isinstance(value.value, (str, int, float, bool))
    return isinstance(value, ast.Name) and value.id in primitive_names


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
            stage_context_names = _stage_context_names(tree, _stage_context_aliases(tree))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not _call_matches_object_setattr(node):
                    continue
                field_name = _stage_field_name(node)
                if field_name not in _VALIDATED_STAGE_FIELDS:
                    continue
                if _setattr_target_name(node) not in stage_context_names:
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
            parents = _parent_map(tree)
            primitive_names_by_scope: dict[ast.AST, set[str]] = {}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                    continue
                target = node.targets[0]
                if not _is_active_models_target(target):
                    continue
                if _enclosing_class_name(node, parents) != "ModelManager":
                    continue
                scope = _enclosing_scope(node, parents)
                primitive_names = primitive_names_by_scope.setdefault(
                    scope, _primitive_like_names(scope)
                )
                if not _is_primitive_model_assignment(node.value, primitive_names):
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
