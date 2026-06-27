# pyre-ignore-all-errors
"""Security detector pack for legacy review-regression audits."""

from __future__ import annotations

import ast
import tokenize
from collections.abc import Iterator
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
_ROUTE_DECORATORS = {"api_route", "delete", "get", "head", "options", "patch", "post", "put"}
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
    """A request field that has been passed through ``resolve_path()``."""

    request_name: str
    field_name: str
    alias_name: str | None
    line: int


@dataclass(frozen=True, slots=True)
class _RawFieldAlias:
    """A local variable bound to a raw (unvalidated) request path field."""

    request_name: str
    field_name: str
    alias_name: str
    line: int
    rebind_lines: tuple[int, ...] = ()
    """Lines (after *line*) where this name is rebound to a non-raw-field value.

    Used by sink-checking code to determine whether the alias still holds a
    raw value at the time of the sink call.  A rebind *before* the sink means
    the alias no longer carries the raw field value, so the sink should not be
    flagged.
    """


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    """Build a child → parent mapping for every node in *tree*."""
    parents: dict[ast.AST, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[child] = parent
    return parents


def _walk_function_body(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Iterator[ast.AST]:
    """Yield every AST node in *node*'s body without descending into nested scopes.

    Unlike ``ast.walk``, nested ``FunctionDef``, ``AsyncFunctionDef``,
    ``ClassDef``, and ``Lambda`` nodes are *yielded* (so they can be inspected
    as call-sites, decorators, etc.) but their children are **not** traversed —
    analysis stays scoped to the immediate function body.
    """
    queue: list[ast.AST] = list(ast.iter_child_nodes(node))
    while queue:
        current = queue.pop()
        yield current
        if not isinstance(
            current,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda),
        ):
            queue.extend(ast.iter_child_nodes(current))


def _iter_guarded_python_files(root: Path) -> list[Path]:
    """Return all Python files under the guarded API/web source roots."""
    files: list[Path] = []
    for guarded_root in _GUARDED_SOURCE_ROOTS:
        candidate = root / guarded_root
        if candidate.exists():
            files.extend(iter_python_files(candidate))
    return sorted(files, key=lambda path: path.as_posix())


def _read_python_source(path: Path) -> str:
    """Read *path* with encoding detection via tokenize."""
    with tokenize.open(path) as handle:
        return handle.read()


def _path_constructor_names(tree: ast.AST) -> set[str]:
    """Return all local names that refer to ``pathlib.Path`` in *tree*.

    Only names introduced by an explicit ``from pathlib import Path [as alias]``
    are returned.  Unconditionally seeding ``"Path"`` would flag files that
    shadow the name without importing it from ``pathlib``.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "pathlib":
            for alias in node.names:
                if alias.name == "Path":
                    names.add(alias.asname or alias.name)
    return names


def _path_module_aliases(tree: ast.AST) -> set[str]:
    """Return all local names bound to the ``pathlib`` module in *tree*."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "pathlib":
                    aliases.add(alias.asname or "pathlib")
    return aliases


def _is_path_call(
    node: ast.AST,
    *,
    constructor_names: set[str],
    module_aliases: set[str],
) -> bool:
    """Return True if *node* is a ``Path(...)`` or ``pathlib.Path(...)`` call."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id in constructor_names
    return (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "Path"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in module_aliases
    )


def _resolve_path_names(tree: ast.AST) -> set[str]:
    """Return all local names bound to ``resolve_path`` in *tree*.

    Handles four binding forms:

    * ``from <pkg>.api.utils import resolve_path [as alias]`` — the canonical
      import form; adds the local name (or alias).
    * ``import <pkg>.api.utils as alias`` — module-alias form; adds the alias so
      that ``alias.resolve_path(...)`` is matched by the attribute branch of
      ``_is_resolve_path_call``.
    * ``from <pkg>.api import utils [as alias]`` — package-level module import;
      adds ``utils`` (or alias) so ``utils.resolve_path(...)`` is recognized.
    * ``def resolve_path(...)`` — locally re-implemented or re-defined; adds
      ``"resolve_path"`` so test fixtures and thin wrappers are covered.

    Unconditionally seeding ``"resolve_path"`` would catch calls to unrelated
    functions that happen to share the name.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.endswith("api.utils"):
                for alias in node.names:
                    if alias.name == "resolve_path":
                        names.add(alias.asname or alias.name)
            elif module.endswith("api") or module.endswith(".api"):
                for alias in node.names:
                    if alias.name == "utils":
                        names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("api.utils"):
                    names.add(alias.asname or alias.name.rpartition(".")[-1])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == "resolve_path":
                names.add("resolve_path")
    return names


def _attr_root_name(node: ast.expr) -> str | None:
    """Return the root ``Name.id`` of an attribute chain, or None for non-Name roots."""
    while isinstance(node, ast.Attribute):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _is_resolve_path_call(node: ast.AST, resolve_path_names: set[str]) -> bool:
    """Return True if *node* is a call to any local alias of ``resolve_path``."""
    if not isinstance(node, ast.Call):
        return False
    if isinstance(node.func, ast.Name):
        return node.func.id in resolve_path_names
    if isinstance(node.func, ast.Attribute) and node.func.attr == "resolve_path":
        root = _attr_root_name(node.func.value)
        return root is not None and root in resolve_path_names
    return False


def _is_allowed_paths_expr(node: ast.AST) -> bool:
    """Return True if *node* is ``allowed_paths`` or ``settings.allowed_paths``."""
    return (isinstance(node, ast.Name) and node.id == "allowed_paths") or (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "settings"
        and node.attr == "allowed_paths"
    )


def _window_has_codeql_suppression(lines: list[str], lineno: int) -> bool:
    """Return True if a CodeQL path-injection suppression comment appears near *lineno*."""
    start = max(0, lineno - 3)
    end = min(len(lines), lineno)
    window = "\n".join(lines[start:end])
    return "codeql[py/path-injection]" in window


def _window_has_prevalidated_marker(lines: list[str], lineno: int) -> bool:
    """Return True if a pre-validated boundary comment appears near *lineno*."""
    start = max(0, lineno - 3)
    end = min(len(lines), lineno)
    window = "\n".join(lines[start:end]).lower()
    return "pre-validated at api boundary" in window


def _is_basename_extraction(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    """Return True if the Path() call is only used to extract a safe attribute (.name, .stem, etc.)."""
    parent = parents.get(node)
    if not (isinstance(parent, ast.Attribute) and parent.attr in _SAFE_PATH_ATTRS):
        return False

    grandparent = parents.get(parent)
    if isinstance(grandparent, ast.Attribute) and grandparent.attr == "strip":
        return isinstance(parents.get(grandparent), ast.Call)

    return True


def _is_allowed_config_root_path(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> bool:
    """Return True if *node* is a Path() call iterating over ``allowed_paths`` in a comprehension."""
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
    """Return True if *node* is wrapped inside a ``file_info_from_path(...)`` call."""
    parent = parents.get(node)
    return (
        isinstance(parent, ast.Call)
        and isinstance(parent.func, ast.Name)
        and parent.func.id == "file_info_from_path"
    )


def _is_in_route_handler(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """Return True if *node* is nested (directly or transitively) inside a route handler.

    Walks all the way up the parent chain rather than stopping at the first
    enclosing function, so nodes inside inner helper functions or lambdas
    defined within a route handler are still detected.
    """
    current: ast.AST | None = node
    while current is not None:
        current = parents.get(current)
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_route_handler(current):
                return True
    return False


def _is_allowed_direct_path_call(
    node: ast.Call,
    *,
    parents: dict[ast.AST, ast.AST],
    lines: list[str],
) -> bool:
    """Return True if the direct Path() call matches a documented safe pattern."""
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
    if _window_has_codeql_suppression(lines, node.lineno) and not _is_in_route_handler(
        node, parents
    ):
        return True
    if _window_has_prevalidated_marker(lines, node.lineno) and not _is_in_route_handler(
        node, parents
    ):
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
    """Return the simple name of the callee in *node*, or None for complex expressions."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _is_route_handler(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True if *node* is decorated with a FastAPI/Starlette route decorator."""
    for decorator in node.decorator_list:
        func = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(func, ast.Attribute) and func.attr in _ROUTE_DECORATORS:
            return True
        if isinstance(func, ast.Name) and func.id in _ROUTE_DECORATORS:
            return True
    return False


def _find_validated_fields(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    resolve_path_names: set[str],
) -> dict[tuple[str, str], _ValidatedField]:
    """Return request fields that are passed through ``resolve_path()`` in *node*.

    Uses ``_walk_function_body`` so that ``resolve_path()`` calls inside nested
    scopes (inner functions, lambdas) are not incorrectly attributed to the outer
    route handler.
    """
    validated: dict[tuple[str, str], _ValidatedField] = {}

    for child in _walk_function_body(node):
        call: ast.Call | None = None
        alias_name: str | None = None
        line = getattr(child, "lineno", None)
        if (
            isinstance(child, ast.Assign)
            and len(child.targets) == 1
            and isinstance(child.value, ast.Call)
        ):
            call = child.value
            if isinstance(child.targets[0], ast.Name):
                alias_name = child.targets[0].id
        elif isinstance(child, ast.AnnAssign) and isinstance(child.value, ast.Call):
            call = child.value
            if isinstance(child.target, ast.Name):
                alias_name = child.target.id
        elif isinstance(child, ast.Call):
            call = child
            line = child.lineno

        if call is None or not _is_resolve_path_call(call, resolve_path_names):
            continue
        if not call.args:
            continue
        first_arg = call.args[0]
        if (
            isinstance(first_arg, ast.Attribute)
            and isinstance(first_arg.value, ast.Name)
            and isinstance(first_arg.attr, str)
        ):
            key = (first_arg.value.id, first_arg.attr)
            candidate = _ValidatedField(
                request_name=first_arg.value.id,
                field_name=first_arg.attr,
                alias_name=alias_name,
                line=line if line is not None else call.lineno,
            )
            existing = validated.get(key)
            if existing is None or candidate.line < existing.line:
                validated[key] = candidate

    return validated


def _find_raw_field_aliases(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    validated: dict[tuple[str, str], _ValidatedField],
) -> dict[str, _RawFieldAlias]:
    """Return local variables assigned from raw (unvalidated) request path fields in *node*.

    Uses ``_walk_function_body`` so that assignments inside nested scopes are
    not incorrectly attributed to the outer route handler.  All raw aliases for
    validated fields are collected regardless of whether the alias appears before
    or after the validation call — a pre-validation raw alias is still a bypass
    when it is passed to a sink that runs after validation.  The sink-time check
    (``child.lineno > vf.line``) in ``_append_field_findings_from_expr`` is
    responsible for filtering sinks that precede validation.

    Each returned alias carries ``rebind_lines``: the sorted tuple of lines at
    which the name is re-assigned after the raw-field assignment.  The sink
    checker uses this to skip the alias when a rebind happened *before* the
    sink, meaning the alias no longer holds the raw value at call time.
    """
    aliases: dict[str, _RawFieldAlias] = {}
    all_assignment_lines: dict[str, list[int]] = {}
    for child in _walk_function_body(node):
        value: ast.AST | None = None
        target: ast.Name | None = None
        if (
            isinstance(child, ast.Assign)
            and len(child.targets) == 1
            and isinstance(child.targets[0], ast.Name)
        ):
            target = child.targets[0]
            value = child.value
        elif (
            isinstance(child, ast.AnnAssign)
            and isinstance(child.target, ast.Name)
            and child.value is not None
        ):
            target = child.target
            value = child.value

        if target is not None:
            all_assignment_lines.setdefault(target.id, []).append(child.lineno)

        if (
            target is None
            or not isinstance(value, ast.Attribute)
            or not isinstance(value.value, ast.Name)
        ):
            continue

        key = (value.value.id, value.attr)
        if validated.get(key) is None:
            continue

        candidate = _RawFieldAlias(
            request_name=value.value.id,
            field_name=value.attr,
            alias_name=target.id,
            line=child.lineno,
        )
        existing = aliases.get(target.id)
        if existing is None or candidate.line > existing.line:
            aliases[target.id] = candidate

    return {
        name: _RawFieldAlias(
            request_name=alias.request_name,
            field_name=alias.field_name,
            alias_name=alias.alias_name,
            line=alias.line,
            rebind_lines=tuple(
                sorted(ln for ln in all_assignment_lines.get(name, []) if ln > alias.line)
            ),
        )
        for name, alias in aliases.items()
    }


def _iter_request_field_refs(expr: ast.AST, *, request_name: str) -> list[ast.Attribute]:
    """Return all ``<request_name>.<field>`` attribute accesses within *expr*."""
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
    """Return True if *call* is a ``.model_copy()`` invocation (safe — always copies validated data)."""
    return isinstance(call.func, ast.Attribute) and call.func.attr == "model_copy"


def _is_sensitive_validation_sink(call: ast.Call) -> bool:
    """Return True if *call* targets a sink that must receive validated path data."""
    call_name = _call_name(call)
    if call_name in _VALIDATION_BYPASS_SINKS:
        return True
    return isinstance(call_name, str) and call_name.startswith("_run_")


def _is_request_model_construction(call: ast.Call) -> bool:
    """Return True if *call* constructs a ``*Request`` Pydantic model (not a path sink)."""
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
            constructor_names = _path_constructor_names(tree)
            module_aliases = _path_module_aliases(tree)
            parents = _parent_map(tree)
            for node in ast.walk(tree):
                if not _is_path_call(
                    node, constructor_names=constructor_names, module_aliases=module_aliases
                ):
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
            resolve_path_names = _resolve_path_names(tree)
            for node in ast.walk(tree):
                if not isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef)
                ) or not _is_route_handler(node):
                    continue
                validated = _find_validated_fields(node, resolve_path_names=resolve_path_names)
                if not validated:
                    continue
                violations.extend(
                    self._violations_for_function(
                        root,
                        path,
                        node,
                        validated,
                        resolve_path_names=resolve_path_names,
                    )
                )
        return sorted(violations, key=lambda finding: finding.sort_key())

    def _violations_for_function(
        self,
        root: Path,
        path: Path,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        validated: dict[tuple[str, str], _ValidatedField],
        resolve_path_names: set[str],
    ) -> list[Violation]:
        """Return all bypass violations found within a single route-handler function."""
        findings: list[Violation] = []
        seen: set[tuple[str, int, str]] = set()
        raw_field_aliases = _find_raw_field_aliases(node, validated=validated)
        request_names = {item.request_name for item in validated.values()}
        earliest_validation_line = {
            request_name: min(
                field.line for field in validated.values() if field.request_name == request_name
            )
            for request_name in request_names
        }

        for child in _walk_function_body(node):
            if (
                not isinstance(child, ast.Call)
                or _is_resolve_path_call(child, resolve_path_names)
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
                    raw_field_aliases=raw_field_aliases,
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
        """Append a violation if the raw request object is passed to a sensitive sink after validation."""
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
        raw_field_aliases: dict[str, _RawFieldAlias],
    ) -> None:
        """Append violations for raw request field references in arguments to *child*."""
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
                raw_field_aliases=raw_field_aliases,
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
                raw_field_aliases=raw_field_aliases,
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
        raw_field_aliases: dict[str, _RawFieldAlias],
    ) -> None:
        """Append violations for a single argument expression that carries a raw request field."""
        if isinstance(expr, ast.Name):
            alias = raw_field_aliases.get(expr.id)
            alias_vf = (
                validated.get((alias.request_name, alias.field_name)) if alias is not None else None
            )
            if (
                alias is not None
                and alias_vf is not None
                and alias.request_name == request_name
                and child.lineno > alias.line
                and child.lineno > alias_vf.line
                and not any(r < child.lineno for r in alias.rebind_lines)
            ):
                key = (
                    "raw-field-alias",
                    child.lineno,
                    f"{alias.request_name}.{alias.field_name}:{alias.alias_name}",
                )
                if key not in seen:
                    seen.add(key)
                    findings.append(
                        Violation.from_path(
                            detector_id=self.detector_id,
                            rule_class=self.rule_class,
                            rule_id="raw-field-after-validation",
                            root=root,
                            path=path,
                            line=expr.lineno,
                            message=(
                                f"Route validates {alias.request_name}.{alias.field_name} with "
                                "resolve_path() but later passes alias "
                                f"{alias.alias_name} sourced from raw "
                                f"{alias.request_name}.{alias.field_name} to {call_name}()."
                            ),
                            fingerprint_basis=fingerprint_ast_node(expr),
                        )
                    )

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
