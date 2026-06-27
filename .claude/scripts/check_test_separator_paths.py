#!/usr/bin/env python3
"""CI-rail: Flag hardcoded path separators in Path() construction in tests (WP-6.2).

Ensures cross-platform compatibility by discouraging hardcoded path separators
(like Path("foo/bar")) in favor of the division operator (like Path("foo") / "bar").
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


class TestSeparatorPathVisitor(ast.NodeVisitor):
    """AST visitor to find hardcoded path separators in tests."""

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        # Check for Path("foo/bar") or Path("foo\\bar")
        if isinstance(node.func, ast.Name) and node.func.id == "Path":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    val = arg.value
                    # Flag if it contains path separators (excluding root "/" and URL schemes)
                    if ("/" in val or "\\" in val) and val != "/" and not val.startswith(("http://", "https://")):
                        self.add_violation(
                            node,
                            f"hardcoded path separator in Path('{val}'). Use division operator (/) instead.",
                        )
        self.generic_visit(node)

    def add_violation(self, node: ast.AST, message: str) -> None:
        lineno = node.lineno
        line_idx = lineno - 1
        if 0 <= line_idx < len(self.lines):
            line_content = self.lines[line_idx]
            # Support noqa override
            if "noqa: test-separator-paths" in line_content or "noqa" in line_content:
                return
            self.violations.append((lineno, message, line_content.strip()))


def check_file(filepath: Path) -> list[tuple[int, str, str]]:
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

    visitor = TestSeparatorPathVisitor(filepath, lines)
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    """Scan all test files under tests/."""
    test_dir = Path("tests")
    if not test_dir.exists():
        print("Error: tests directory not found. Run from the repository root.")
        return 1

    all_violations = []
    # Scan all python files in tests recursively
    for path in test_dir.rglob("*.py"):
        violations = check_file(path)
        for lineno, msg, line in violations:
            all_violations.append((path.as_posix(), lineno, msg, line))

    if all_violations:
        print("❌ [test-separator-paths] Violations found (hardcoded path separators):", file=sys.stderr)
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: Construct paths using division (e.g. Path('foo') / 'bar'), or add '# noqa: test-separator-paths' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [test-separator-paths] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
