"""Public API compatibility detector pack for review-regression audits.

This pack enforces allowlisted callable signature invariants:
- Legacy positional parameter prefixes must remain stable.
- Newly added optional parameters must be keyword-only.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from file_organizer.review_regressions.framework import (
    ReviewRegressionDetector,
    Violation,
    fingerprint_ast_node,
    parse_python_ast,
)


@dataclass(frozen=True, slots=True)
class PublicCallableContract:
    """Compatibility contract for one allowlisted public callable."""

    path: Path
    qualname: str
    legacy_positional_params: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ParameterInfo:
    name: str
    kind: str
    has_default: bool
    line: int | None


_POSITIONAL_ONLY = "positional-only"
_POSITIONAL_OR_KEYWORD = "positional-or-keyword"
_KEYWORD_ONLY = "keyword-only"
_VAR_POSITIONAL = "var-positional"
_VAR_KEYWORD = "var-keyword"
_BOUND_METHOD_PARAM_NAMES = {"self", "cls"}

_DEFAULT_PUBLIC_CALLABLE_CONTRACTS: tuple[PublicCallableContract, ...] = (
    PublicCallableContract(
        path=Path("src/file_organizer/core/organizer.py"),
        qualname="FileOrganizer.__init__",
        legacy_positional_params=(
            "text_model_config",
            "vision_model_config",
            "dry_run",
            "use_hardlinks",
            "parallel_workers",
            "no_prefetch",
        ),
    ),
    PublicCallableContract(
        path=Path("src/file_organizer/core/organizer.py"),
        qualname="FileOrganizer.organize",
        legacy_positional_params=("input_path", "output_path", "skip_existing"),
    ),
    PublicCallableContract(
        path=Path("src/file_organizer/pipeline/orchestrator.py"),
        qualname="PipelineOrchestrator.__init__",
        legacy_positional_params=(
            "config",
            "stages",
            "prefetch_depth",
            "prefetch_stages",
            "memory_limiter",
            "batch_sizer",
            "buffer_pool",
            "resource_monitor",
            "memory_pressure_threshold_percent",
        ),
    ),
    PublicCallableContract(
        path=Path("src/file_organizer/pipeline/orchestrator.py"),
        qualname="PipelineOrchestrator.process_batch",
        legacy_positional_params=("files",),
    ),
)


def _iter_defaults_aligned_positional_args(
    args: ast.arguments,
) -> list[tuple[ast.arg, ast.expr | None, str]]:
    positional: list[tuple[ast.arg, ast.expr | None, str]] = []
    positional_only = args.posonlyargs
    positional_or_keyword = args.args
    all_positional = [*positional_only, *positional_or_keyword]
    defaults = [None] * (len(all_positional) - len(args.defaults)) + list(args.defaults)

    for index, argument in enumerate(all_positional):
        kind = _POSITIONAL_ONLY if index < len(positional_only) else _POSITIONAL_OR_KEYWORD
        positional.append((argument, defaults[index], kind))
    return positional


def _parameters_for_callable(
    node: ast.FunctionDef | ast.AsyncFunctionDef, *, is_bound_method: bool
) -> list[_ParameterInfo]:
    params: list[_ParameterInfo] = []
    positional_args = _iter_defaults_aligned_positional_args(node.args)
    dropped_bound = False
    for argument, default, kind in positional_args:
        if is_bound_method and not dropped_bound and argument.arg in _BOUND_METHOD_PARAM_NAMES:
            dropped_bound = True
            continue
        params.append(
            _ParameterInfo(
                name=argument.arg,
                kind=kind,
                has_default=default is not None,
                line=getattr(argument, "lineno", None),
            )
        )

    if node.args.vararg is not None:
        params.append(
            _ParameterInfo(
                name=node.args.vararg.arg,
                kind=_VAR_POSITIONAL,
                has_default=False,
                line=getattr(node.args.vararg, "lineno", None),
            )
        )

    for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
        params.append(
            _ParameterInfo(
                name=argument.arg,
                kind=_KEYWORD_ONLY,
                has_default=default is not None,
                line=getattr(argument, "lineno", None),
            )
        )

    if node.args.kwarg is not None:
        params.append(
            _ParameterInfo(
                name=node.args.kwarg.arg,
                kind=_VAR_KEYWORD,
                has_default=False,
                line=getattr(node.args.kwarg, "lineno", None),
            )
        )

    return params


def _find_allowlisted_callable(
    tree: ast.AST,
    qualname: str,
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef | None, bool]:
    """Resolve an allowlisted callable by qualified name and return (node, is_method)."""
    parts = qualname.split(".")
    if len(parts) == 1:
        return _find_toplevel_callable(tree, parts[0]), False
    return _find_class_method_callable(tree, parts)


def _find_toplevel_callable(
    tree: ast.AST, name: str
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for stmt in getattr(tree, "body", []):
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == name:
            return stmt
    return None


def _find_named_classes(body: list[ast.stmt], class_name: str) -> list[ast.ClassDef]:
    return [stmt for stmt in body if isinstance(stmt, ast.ClassDef) and stmt.name == class_name]


def _find_named_methods(
    body: list[ast.stmt], method_name: str
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        stmt
        for stmt in body
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)) and stmt.name == method_name
    ]


def _find_class_method_callable(
    tree: ast.AST,
    parts: list[str],
) -> tuple[ast.FunctionDef | ast.AsyncFunctionDef | None, bool]:
    classes = _find_named_classes(getattr(tree, "body", []), parts[0])
    for class_name in parts[1:-1]:
        next_classes: list[ast.ClassDef] = []
        for class_node in classes:
            next_classes.extend(_find_named_classes(class_node.body, class_name))
        classes = next_classes
        if not classes:
            return None, True

    method_name = parts[-1]
    for class_node in classes:
        methods = _find_named_methods(class_node.body, method_name)
        if methods:
            return methods[0], True
    return None, True


def _prefix_mismatch(
    actual: tuple[str, ...],
    expected: tuple[str, ...],
) -> bool:
    if len(actual) < len(expected):
        return True
    return actual[: len(expected)] != expected


class PublicApiCompatibilityDetector:
    """Enforce allowlisted public callable signature compatibility contracts."""

    detector_id = "api-compat.public-callable-signature-contracts"
    rule_class = "api-compat"
    description = (
        "Enforces allowlisted public callable signature contracts: keep legacy positional "
        "prefixes stable and require new optional parameters to be keyword-only."
    )

    def __init__(
        self,
        *,
        contracts: tuple[PublicCallableContract, ...] | None = None,
    ) -> None:
        """Initialize detector with the default or provided callable contracts."""
        self._contracts = contracts or _DEFAULT_PUBLIC_CALLABLE_CONTRACTS

    def find_violations(self, root: Path) -> list[Violation]:
        """Return violations for allowlisted callable compatibility contracts under *root*."""
        findings: list[Violation] = []
        parsed_trees: dict[Path, ast.AST] = {}
        for contract in self._contracts:
            source_path = root / contract.path
            if not source_path.is_file():
                findings.append(
                    Violation.from_path(
                        detector_id=self.detector_id,
                        rule_class=self.rule_class,
                        rule_id="allowlisted-callable-missing",
                        root=root,
                        path=contract.path,
                        message=(
                            f"Allowlisted callable target is missing: {contract.path}::{contract.qualname}"
                        ),
                        fingerprint_basis=f"{contract.path}::{contract.qualname}",
                    )
                )
                continue

            tree = parsed_trees.get(source_path)
            if tree is None:
                tree = parse_python_ast(source_path)
                parsed_trees[source_path] = tree

            callable_node, is_bound_method = _find_allowlisted_callable(tree, contract.qualname)
            if callable_node is None:
                findings.append(
                    Violation.from_path(
                        detector_id=self.detector_id,
                        rule_class=self.rule_class,
                        rule_id="allowlisted-callable-missing",
                        root=root,
                        path=source_path,
                        line=1,
                        message=(
                            "Allowlisted callable not found in source AST: "
                            f"{contract.path}::{contract.qualname}"
                        ),
                        fingerprint_basis=f"{contract.path}::{contract.qualname}",
                    )
                )
                continue

            all_params = _parameters_for_callable(callable_node, is_bound_method=is_bound_method)
            positional_infos = [
                param
                for param in all_params
                if param.kind in {_POSITIONAL_ONLY, _POSITIONAL_OR_KEYWORD}
            ]
            positional_params = tuple(param.name for param in positional_infos)

            prefix_changed = _prefix_mismatch(positional_params, contract.legacy_positional_params)
            if prefix_changed:
                findings.append(
                    Violation.from_path(
                        detector_id=self.detector_id,
                        rule_class=self.rule_class,
                        rule_id="legacy-positional-prefix-changed",
                        root=root,
                        path=source_path,
                        line=getattr(callable_node, "lineno", None),
                        message=(
                            f"{contract.qualname} changed legacy positional prefix. "
                            f"Expected {contract.legacy_positional_params!r} but found "
                            f"{positional_params!r}."
                        ),
                        fingerprint_basis=fingerprint_ast_node(callable_node),
                    )
                )
                continue

            for position, param in enumerate(positional_infos):
                if position < len(contract.legacy_positional_params):
                    continue
                if not param.has_default:
                    continue
                findings.append(
                    Violation.from_path(
                        detector_id=self.detector_id,
                        rule_class=self.rule_class,
                        rule_id="new-optional-param-must-be-keyword-only",
                        root=root,
                        path=source_path,
                        line=param.line,
                        message=(
                            f"{contract.qualname} adds optional positional parameter "
                            f"{param.name!r}; new optional params must be keyword-only."
                        ),
                        fingerprint_basis=f"{contract.qualname}:{param.name}:{param.kind}",
                    )
                )

        return sorted(findings, key=lambda finding: finding.sort_key())


API_COMPAT_DETECTORS: tuple[ReviewRegressionDetector, ...] = (PublicApiCompatibilityDetector(),)
