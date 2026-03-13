"""Security detector pack for legacy review-regression audits."""

from __future__ import annotations

import ast
import tokenize
from dataclasses import dataclass
from pathlib import Path

from file_organizer.review_regressions.framework import (
    ReviewRegressionDetector,
    Violation,
    fingerprint_ast_node,
    iter_python_files,
)

_GUARDED_SOURCE_ROOTS = (
    Path("src/file_organizer/api"),
    Path("src/file_organizer/web"),
)
_ROUTE_DECORATORS = {"delete", "get", "head", "options", "patch", "post", "put"}
_SAFE_PATH_ATTRS = {"name", "stem", "suffix"}
_PATH_LIKE_KEYWORDS = {
    "destination",
    "file_path",
    "input_dir",
    "input_path",
    "output_dir",
    "output_path",
    "path",
    "root",
    "scan_dir",
    "source",
    "target",
}
_VALIDATION_BYPASS_SINKS = {"add_task", "organize"}


@dataclass(frozen=True, slots=True)
class _ValidatedField:
    request_name: str
    field_name: str
    alias_name: str | None
    line: int


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _iter_guarded_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for guarded_root in _GUARDED_SOURCE_ROOTS:
        candidate = root / guarded_root
        if candidate.exists():
            files.extend(iter_python_files(candidate))
    return sorted(files, key=lambda path: path.as_posix())


def _read_python_source(path: Path) -> str:
    with tokenize.open(path) as handle:
        return handle.read()


def _is_path_call(node: ast.AST) -> bool:
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Path"


def _is_resolve_path_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "resolve_path"
    )


def _is_allowed_paths_expr(node: ast.AST) -> bool:
    return (isinstance(node, ast.Name) and node.id == "allowed_paths") or (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "settings"
        and node.attr == "allowed_paths"
    )


def _window_has_codeql_suppression(lines: list[str], lineno: int) -> bool:
    start = max(0, lineno - 3)
    end = min(len(lines), lineno)
    window = "\n".join(lines[start:end])
    return "codeql[py/path-injection]" in window


def _window_has_prevalidated_marker(lines: list[str], lineno: int) -> bool:
    start = max(0, lineno - 3)
    end = min(len(lines), lineno)
    window = "\n".join(lines[start:end]).lower()
    return "pre-validated at api boundary" in window


def _is_basename_extraction(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    if not (isinstance(parent, ast.Attribute) and parent.attr in _SAFE_PATH_ATTRS):
        return False

    grandparent = parents.get(parent)
    if isinstance(grandparent, ast.Attribute) and grandparent.attr == "strip":
        return isinstance(parents.get(grandparent), ast.Call)

    return True


def _is_allowed_config_root_path(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    if len(node.args) != 1 or not isinstance(node.args[0], ast.Name):
        return False
    target_name = node.args[0].id

    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if isinstance(current, (ast.ListComp, ast.SetComp, ast.GeneratorExp)):
            for generator in current.generators:
                if (
                    isinstance(generator.target, ast.Name)
                    and generator.target.id == target_name
                    and _is_allowed_paths_expr(generator.iter)
                ):
                    return True
    return False


def _is_allowed_file_info_wrapper(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    return (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Name)
        and parent.func.id == "file_info_from_path"
    )


def _is_allowed_direct_path_call(
    node: ast.Call,
    *,
    parents: dict[ast.AST, ast.AST],
    lines: list[str],
) -> bool:
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if (
            isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef))
            and current.name == "resolve_path"
        ):
            return True
    if node.args and isinstance(node.args[0], ast.Name) and node.args[0].id == "__file__":
        return True
    if _window_has_codeql_suppression(lines, node.lineno):
        return True
    if _window_has_prevalidated_marker(lines, node.lineno):
        return True
    if _is_basename_extraction(node, parents):
        return True
    if _is_allowed_config_root_path(node, parents) and _window_has_codeql_suppression(
        lines, node.lineno
    ):
        return True
    if _is_allowed_file_info_wrapper(node, parents):
        return True
    return False


def _call_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _is_route_handler(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr in _ROUTE_DECORATORS
        ):
            return True
    return False


def _find_validated_fields(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> dict[tuple[str, str], _ValidatedField]:
    validated: dict[tuple[str, str], _ValidatedField] = {}

    for child in ast.walk(node):
        value: ast.AST | None = None
        alias_name: str | None = None
        if isinstance(child, ast.Assign) and len(child.targets) == 1:
            value = child.value
            if isinstance(child.targets[0], ast.Name):
                alias_name = child.targets[0].id
        elif isinstance(child, ast.AnnAssign):
            value = child.value
            if isinstance(child.target, ast.Name):
                alias_name = child.target.id

        if not isinstance(value, ast.Call) or not _is_resolve_path_call(value):
            continue
        if not value.args:
            continue
        first_arg = value.args[0]
        if (
            isinstance(first_arg, ast.Attribute)
            and isinstance(first_arg.value, ast.Name)
            and isinstance(first_arg.attr, str)
        ):
            key = (first_arg.value.id, first_arg.attr)
            validated[key] = _ValidatedField(
                request_name=first_arg.value.id,
                field_name=first_arg.attr,
                alias_name=alias_name,
                line=child.lineno,
            )

    return validated


def _iter_request_field_refs(expr: ast.AST, *, request_name: str) -> list[ast.Attribute]:
    refs: list[ast.Attribute] = []
    for node in ast.walk(expr):
        if (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id == request_name
        ):
            refs.append(node)
    return refs


def _is_safe_model_copy_call(call: ast.Call) -> bool:
    return isinstance(call.func, ast.Attribute) and call.func.attr == "model_copy"


def _is_sensitive_validation_sink(call: ast.Call) -> bool:
    call_name = _call_name(call)
    if call_name in _VALIDATION_BYPASS_SINKS:
        return True
    return isinstance(call_name, str) and call_name.startswith("_run_")


def _is_request_model_construction(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Name)
        and bool(call.func.id)
        and call.func.id[0].isupper()
        and call.func.id.endswith("Request")
    )


class GuardedContextDirectPathDetector:
    """Detect unreviewed direct ``Path(...)`` usage in API/web modules."""

    detector_id = "security.guarded-context-direct-path"
    rule_class = "security"
    description = (
        "Flags direct Path(...) construction in guarded API/web contexts unless the usage "
        "matches a documented approved safe pattern."
    )

    def find_violations(self, root: Path) -> list[Violation]:
        """Return direct-path findings under the guarded API/web source roots."""
        violations: list[Violation] = []
        for path in _iter_guarded_python_files(root):
            source = _read_python_source(path)
            lines = source.splitlines()
            tree = ast.parse(source, filename=str(path))
            parents = _parent_map(tree)
            for node in ast.walk(tree):
                if not _is_path_call(node):
                    continue
                if _is_allowed_direct_path_call(node, parents=parents, lines=lines):
                    continue
                violations.append(
                    Violation.from_path(
                        detector_id=self.detector_id,
                        rule_class=self.rule_class,
                        rule_id="unguarded-direct-path",
                        root=root,
                        path=path,
                        line=node.lineno,
                        message=(
                            "Direct Path(...) usage in API/web code must go through a documented "
                            "safe pattern or an explicit path-validation boundary."
                        ),
                        fingerprint_basis=fingerprint_ast_node(node),
                    )
                )
        return sorted(violations, key=lambda finding: finding.sort_key())


class ValidatedPathBypassDetector:
    """Detect route handlers that validate a request path then reuse the raw request."""

    detector_id = "security.validated-path-bypass"
    rule_class = "security"
    description = (
        "Flags route handlers that call resolve_path() and then pass the raw request object "
        "or raw request path fields to downstream calls."
    )

    def find_violations(self, root: Path) -> list[Violation]:
        """Return request-path bypass findings under guarded route handlers."""
        violations: list[Violation] = []
        for path in _iter_guarded_python_files(root):
            source = _read_python_source(path)
            tree = ast.parse(source, filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) or not _is_route_handler(node):
                    continue
                validated = _find_validated_fields(node)
                if not validated:
                    continue
                violations.extend(self._violations_for_function(root, path, node, validated))
        return sorted(violations, key=lambda finding: finding.sort_key())

    def _violations_for_function(
        self,
        root: Path,
        path: Path,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        validated: dict[tuple[str, str], _ValidatedField],
    ) -> list[Violation]:
        findings: list[Violation] = []
        seen: set[tuple[str, int, str]] = set()
        request_names = {item.request_name for item in validated.values()}
        earliest_validation_line = {
            request_name: min(
                field.line for field in validated.values() if field.request_name == request_name
            )
            for request_name in request_names
        }

        for child in ast.walk(node):
            if (
                not isinstance(child, ast.Call)
                or _is_resolve_path_call(child)
                or _is_safe_model_copy_call(child)
            ):
                continue

            call_name = _call_name(child) or "call"
            sensitive_sink = _is_sensitive_validation_sink(child)

            for request_name in request_names:
                self._append_raw_request_findings(
                    findings=findings,
                    seen=seen,
                    root=root,
                    path=path,
                    child=child,
                    request_name=request_name,
                    call_name=call_name,
                    sensitive_sink=sensitive_sink,
                    earliest_validation_line=earliest_validation_line[request_name],
                )
                self._append_raw_field_findings(
                    findings=findings,
                    seen=seen,
                    root=root,
                    path=path,
                    child=child,
                    request_name=request_name,
                    call_name=call_name,
                    validated=validated,
                )
        return findings

    def _append_raw_request_findings(
        self,
        *,
        findings: list[Violation],
        seen: set[tuple[str, int, str]],
        root: Path,
        path: Path,
        child: ast.Call,
        request_name: str,
        call_name: str,
        sensitive_sink: bool,
        earliest_validation_line: int,
    ) -> None:
        if not sensitive_sink:
            return
        if not any(
            isinstance(arg, ast.Name) and arg.id == request_name
            for arg in [*child.args, *[kw.value for kw in child.keywords]]
        ):
            return
        if child.lineno <= earliest_validation_line:
            return
        key = ("raw-request", child.lineno, request_name)
        if key in seen:
            return
        seen.add(key)
        findings.append(
            Violation.from_path(
                detector_id=self.detector_id,
                rule_class=self.rule_class,
                rule_id="raw-request-after-validation",
                root=root,
                path=path,
                line=child.lineno,
                message=(
                    f"Route validates {request_name} path fields with resolve_path() "
                    f"but later passes the raw {request_name} object to {call_name}()."
                ),
                fingerprint_basis=fingerprint_ast_node(child),
            )
        )

    def _append_raw_field_findings(
        self,
        *,
        findings: list[Violation],
        seen: set[tuple[str, int, str]],
        root: Path,
        path: Path,
        child: ast.Call,
        request_name: str,
        call_name: str,
        validated: dict[tuple[str, str], _ValidatedField],
    ) -> None:
        if _is_request_model_construction(child):
            return
        for arg in child.args:
            self._append_field_findings_from_expr(
                findings=findings,
                seen=seen,
                root=root,
                path=path,
                child=child,
                expr=arg,
                request_name=request_name,
                call_name=call_name,
                validated=validated,
            )

        for keyword in child.keywords:
            if keyword.arg not in _PATH_LIKE_KEYWORDS:
                continue
            self._append_field_findings_from_expr(
                findings=findings,
                seen=seen,
                root=root,
                path=path,
                child=child,
                expr=keyword.value,
                request_name=request_name,
                call_name=call_name,
                validated=validated,
            )

    def _append_field_findings_from_expr(
        self,
        *,
        findings: list[Violation],
        seen: set[tuple[str, int, str]],
        root: Path,
        path: Path,
        child: ast.Call,
        expr: ast.AST,
        request_name: str,
        call_name: str,
        validated: dict[tuple[str, str], _ValidatedField],
    ) -> None:
        for ref in _iter_request_field_refs(expr, request_name=request_name):
            validated_field = validated.get((request_name, ref.attr))
            if validated_field is None or child.lineno <= validated_field.line:
                continue
            key = ("raw-field", ref.lineno, f"{request_name}.{ref.attr}")
            if key in seen:
                continue
            seen.add(key)
            findings.append(
                Violation.from_path(
                    detector_id=self.detector_id,
                    rule_class=self.rule_class,
                    rule_id="raw-field-after-validation",
                    root=root,
                    path=path,
                    line=ref.lineno,
                    message=(
                        f"Route validates {request_name}.{ref.attr} with resolve_path() "
                        f"but later passes raw {request_name}.{ref.attr} to {call_name}()."
                    ),
                    fingerprint_basis=fingerprint_ast_node(expr),
                )
            )


SECURITY_DETECTORS: tuple[ReviewRegressionDetector, ...] = (
    GuardedContextDirectPathDetector(),
    ValidatedPathBypassDetector(),
)
