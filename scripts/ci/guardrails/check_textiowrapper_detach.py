#!/usr/bin/env python3
"""CI-rail: Flag io.TextIOWrapper instances that are never detach()-ed (WP-6.1).

A TextIOWrapper that wraps a caller-owned buffer/fd must call .detach()
before the wrapper goes out of scope, or its __del__ closes the
underlying buffer/fd out from under the caller.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _walk_excluding_nested_functions(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """Like ast.walk(func), but does not descend into nested function defs.

    Prevents a nested function's own TextIOWrapper/detach() usage from being
    attributed to (and tracked against) the *outer* function, and from being
    visited twice (once here, once when the nested def is visited directly
    by the NodeVisitor).
    """
    seen: list[ast.AST] = []
    stack: list[ast.AST] = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        seen.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        stack.extend(ast.iter_child_nodes(node))
    return seen


def _is_textiowrapper_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name) and node.func.id == "TextIOWrapper":
        return True
    if (
        isinstance(node.func, ast.Attribute)
        and node.func.attr == "TextIOWrapper"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "io"
    ):
        return True
    return False


class _Visitor(ast.NodeVisitor):
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.violations: list[tuple[int, str]] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        # NOTE: wrapped/detached are keyed by variable name, not by individual
        # assignment. If a function reassigns the same name to two separate
        # TextIOWrapper instances, only the most recently seen assignment's
        # line is tracked and a single detach() call on that name satisfies
        # both — a real (if rare) gap. Out of scope for this rail; use an
        # explicit suppression or a follow-up if it ever bites in practice.
        wrapped: dict[str, int] = {}
        detached: set[str] = set()

        for child in _walk_excluding_nested_functions(node):
            if (
                isinstance(child, ast.Assign)
                and len(child.targets) == 1
                and isinstance(child.targets[0], ast.Name)
                and isinstance(child.value, ast.Call)
                and _is_textiowrapper_call(child.value)
            ):
                wrapped[child.targets[0].id] = child.lineno
            elif (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "detach"
                and isinstance(child.func.value, ast.Name)
            ):
                detached.add(child.func.value.id)

        for name, lineno in wrapped.items():
            if name not in detached:
                line_idx = lineno - 1
                if 0 <= line_idx < len(self.lines) and "noqa" in self.lines[line_idx]:
                    continue
                self.violations.append(
                    (
                        lineno,
                        f"TextIOWrapper assigned to '{name}' is never .detach()-ed — "
                        "its __del__ will close the wrapped buffer/fd",
                    )
                )


def check_file(filepath: Path) -> list[tuple[int, str]]:
    """Parse and check a single Python file."""
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
    """Scan all source files under src/file_organizer/."""
    package_root = Path("src/file_organizer")
    if not package_root.exists():
        print("Error: src/file_organizer directory not found. Run from the repository root.")
        return 1

    all_violations = []
    for path in package_root.rglob("*.py"):
        for lineno, msg in check_file(path):
            all_violations.append((path.as_posix(), lineno, msg))

    if all_violations:
        print("❌ [textiowrapper-detach] Violations found:", file=sys.stderr)
        for file_path, lineno, msg in all_violations:
            print(f"  {file_path}:{lineno}: {msg}", file=sys.stderr)
        print(
            "\nFix: call .detach() before the wrapper goes out of scope, or add "
            "'# noqa: textiowrapper-detach' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [textiowrapper-detach] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
