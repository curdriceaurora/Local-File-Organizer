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


def _calls_getbasetemp(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "getbasetemp"
        ):
            return True
    return False


def _has_xdist_group_marker(decorators: list[ast.expr]) -> bool:
    for dec in decorators:
        call = dec if isinstance(dec, ast.Call) else None
        func = call.func if call is not None else dec
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "xdist_group"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "mark"
        ):
            return True
    return False


class _Visitor(ast.NodeVisitor):
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.violations: list[tuple[int, str]] = []
        self._class_has_marker: list[bool] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class_has_marker.append(_has_xdist_group_marker(node.decorator_list))
        self.generic_visit(node)
        self._class_has_marker.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef) -> None:
        if not node.name.startswith("test_"):
            return
        if not _calls_getbasetemp(node):
            return
        func_has_marker = _has_xdist_group_marker(node.decorator_list)
        class_has_marker = any(self._class_has_marker)
        if func_has_marker or class_has_marker:
            return

        line_idx = node.lineno - 1
        if 0 <= line_idx < len(self.lines) and "noqa" in self.lines[line_idx]:
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

    visitor = _Visitor(lines)
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
