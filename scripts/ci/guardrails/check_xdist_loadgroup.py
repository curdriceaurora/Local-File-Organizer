#!/usr/bin/env python3
"""CI-rail: Remind to mark shared-state tests with xdist_group (WP-6.2).

Heuristic only: flags test functions that call
tmp_path_factory.getbasetemp() (the shared-across-workers temp root,
unlike the per-test tmp_path fixture) without an xdist_group marker on
the function or its enclosing class. Such tests are candidates for
cross-worker races under pytest-xdist's default load-balancing.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa


def _calls_getbasetemp(node: ast.AST, wrapper_names: frozenset[str] = frozenset()) -> bool:
    """Return True if `node` calls `.getbasetemp()` directly or via a known wrapper name."""
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        if isinstance(child.func, ast.Attribute) and child.func.attr == "getbasetemp":
            return True
        if isinstance(child.func, ast.Name) and child.func.id in wrapper_names:
            return True
        if isinstance(child.func, ast.Attribute) and child.func.attr in wrapper_names:
            return True
    return False


def _collect_wrapper_names(tree: ast.AST) -> frozenset[str]:
    """Find same-file functions/methods that call getbasetemp() directly,
    then expand to functions that call those wrappers, fixed-point style,
    so chained helpers are also caught."""
    defs: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defs[node.name] = node

    wrapper_names: set[str] = set()
    changed = True
    while changed:
        changed = False
        for name, node in defs.items():
            if name in wrapper_names:
                continue
            if _calls_getbasetemp(node, frozenset(wrapper_names)):
                wrapper_names.add(name)
                changed = True
    return frozenset(wrapper_names)


def _has_xdist_group_marker(
    decorators: list[ast.expr],
    mark_aliases: frozenset[str] = frozenset(),
    xdist_group_aliases: frozenset[str] = frozenset(),
) -> bool:
    """Return True if any decorator expr is an `xdist_group` marker, recognizing
    `pytest.mark.xdist_group`, aliased `mark` imports, and aliased `xdist_group` imports."""
    for dec in decorators:
        call = dec if isinstance(dec, ast.Call) else None
        func = call.func if call is not None else dec
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "xdist_group"
            and (
                (isinstance(func.value, ast.Attribute) and func.value.attr == "mark")
                or (isinstance(func.value, ast.Name) and func.value.id in mark_aliases)
            )
        ):
            return True
        if isinstance(func, ast.Name) and func.id in xdist_group_aliases:
            return True
    return False


def _collect_mark_aliases(tree: ast.AST) -> tuple[frozenset[str], frozenset[str]]:
    """Track `from pytest import mark` and `from pytest.mark import xdist_group`
    aliases so decorator/pytestmark detection isn't fooled by import style."""
    mark_aliases: set[str] = set()
    xdist_group_aliases: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module == "pytest":
            for alias in node.names:
                if alias.name == "mark":
                    mark_aliases.add(alias.asname or alias.name)
        elif node.module == "pytest.mark":
            for alias in node.names:
                if alias.name == "xdist_group":
                    xdist_group_aliases.add(alias.asname or alias.name)
    return frozenset(mark_aliases), frozenset(xdist_group_aliases)


def _pytestmark_exprs(body: list[ast.stmt]) -> list[ast.expr]:
    """Return marker expressions assigned via a `pytestmark = [...]` (or bare)
    statement in a module or class body."""
    exprs: list[ast.expr] = []
    for stmt in body:
        if not isinstance(stmt, ast.Assign):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "pytestmark" for target in stmt.targets
        ):
            continue
        value = stmt.value
        if isinstance(value, (ast.List, ast.Tuple)):
            exprs.extend(value.elts)
        else:
            exprs.append(value)
    return exprs


class _Visitor(ast.NodeVisitor):
    """Walks a test module, flagging test functions that reach `getbasetemp()`
    (directly or via a wrapper) without an applicable `xdist_group` marker."""

    def __init__(
        self,
        lines: list[str],
        wrapper_names: frozenset[str] = frozenset(),
        mark_aliases: frozenset[str] = frozenset(),
        xdist_group_aliases: frozenset[str] = frozenset(),
        module_has_marker: bool = False,
    ) -> None:
        self.lines = lines
        self.wrapper_names = wrapper_names
        self.mark_aliases = mark_aliases
        self.xdist_group_aliases = xdist_group_aliases
        self.module_has_marker = module_has_marker
        self.violations: list[tuple[int, str]] = []
        self._class_has_marker: list[bool] = []

    def _has_marker(self, exprs: list[ast.expr]) -> bool:
        """Return True if any of `exprs` (decorators or pytestmark entries) is an
        xdist_group marker, given this visitor's collected import aliases."""
        return _has_xdist_group_marker(exprs, self.mark_aliases, self.xdist_group_aliases)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track whether the enclosing class carries an xdist_group marker (via
        decorator or class-level pytestmark) for nested test functions."""
        class_marker = self._has_marker(node.decorator_list) or self._has_marker(
            _pytestmark_exprs(node.body)
        )
        self._class_has_marker.append(class_marker)
        self.generic_visit(node)
        self._class_has_marker.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Check this function for the violation, then recurse into nested defs."""
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef) -> None:
        """Record a violation if `node` is an unmarked test reaching getbasetemp()."""
        if not node.name.startswith("test_"):
            return
        if not _calls_getbasetemp(node, self.wrapper_names):
            return
        func_has_marker = self._has_marker(node.decorator_list)
        class_has_marker = any(self._class_has_marker)
        if func_has_marker or class_has_marker or self.module_has_marker:
            return

        line_idx = node.lineno - 1
        if 0 <= line_idx < len(self.lines) and has_targeted_noqa(
            self.lines[line_idx], "xdist-loadgroup"
        ):
            return

        self.violations.append(
            (
                node.lineno,
                f"test '{node.name}' uses tmp_path_factory.getbasetemp() (shared "
                "across xdist workers) without an @pytest.mark.xdist_group marker "
                "— add one if this test shares mutable state with others",
            )
        )


def check_file(filepath: Path) -> list[tuple[int, str]]:
    """Parse and check a single Python test file."""
    try:
        content = filepath.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"Error reading {filepath}: {exc}", file=sys.stderr)
        return []

    lines = content.splitlines()
    try:
        tree = ast.parse(content, filename=str(filepath))
    except SyntaxError as exc:
        print(f"Syntax error in {filepath}: {exc}", file=sys.stderr)
        return []

    wrapper_names = _collect_wrapper_names(tree)
    mark_aliases, xdist_group_aliases = _collect_mark_aliases(tree)
    module_has_marker = _has_xdist_group_marker(
        _pytestmark_exprs(tree.body), mark_aliases, xdist_group_aliases
    )
    visitor = _Visitor(
        lines,
        wrapper_names,
        mark_aliases,
        xdist_group_aliases,
        module_has_marker,
    )
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    """Scan all test files under tests/."""
    tests_root = Path("tests")
    if not tests_root.exists():
        print("Error: tests directory not found. Run from the repository root.")
        return 1

    all_violations = []
    for path in tests_root.rglob("test_*.py"):
        for lineno, msg in check_file(path):
            all_violations.append((path.as_posix(), lineno, msg))

    if all_violations:
        print("❌ [xdist-loadgroup] Violations found:", file=sys.stderr)
        for file_path, lineno, msg in all_violations:
            print(f"  {file_path}:{lineno}: {msg}", file=sys.stderr)
        print(
            "\nFix: add @pytest.mark.xdist_group(name='...') if this test shares "
            "state with others, or add '# noqa: xdist-loadgroup' if it's safe.",
            file=sys.stderr,
        )
        return 1

    print("✅ [xdist-loadgroup] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
