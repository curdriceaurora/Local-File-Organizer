#!/usr/bin/env python3
"""CI-rail: Ensure pytest.raises on generic/built-in exceptions specifies 'match' (WP-6.2).

Guards against tests swallowing unexpected exceptions by enforcing that common
exceptions (ValueError, Exception, RuntimeError, etc.) are matched against a regex.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Exceptions that are too generic to raise without a match pattern
GENERIC_EXCEPTIONS = {
    "Exception",
    "BaseException",
    "ValueError",
    "RuntimeError",
    "TypeError",
    "OSError",
    "ImportError",
    "AttributeError",
    "KeyError",
    "IndexError",
    "FileNotFoundError",
    "PermissionError",
}


class PytestRaisesHygieneVisitor(ast.NodeVisitor):
    """AST visitor to check pytest.raises hygiene in tests."""

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            context_expr = item.context_expr
            if isinstance(context_expr, ast.Call):
                # Check for pytest.raises(...)
                is_pytest_raises = False
                if isinstance(context_expr.func, ast.Attribute):
                    if (
                        isinstance(context_expr.func.value, ast.Name)
                        and context_expr.func.value.id == "pytest"
                        and context_expr.func.attr == "raises"
                    ):
                        is_pytest_raises = True
                elif isinstance(context_expr.func, ast.Name) and context_expr.func.id == "raises":
                    is_pytest_raises = True

                if is_pytest_raises:
                    # Check the exception class argument (usually first positional arg)
                    if context_expr.args:
                        exc_arg = context_expr.args[0]
                        exc_name = ""
                        if isinstance(exc_arg, ast.Name):
                            exc_name = exc_arg.id
                        elif isinstance(exc_arg, ast.Attribute):
                            exc_name = exc_arg.attr

                        if exc_name in GENERIC_EXCEPTIONS:
                            # Verify if 'match' keyword argument is provided
                            has_match = any(kw.arg == "match" for kw in context_expr.keywords)
                            if not has_match:
                                self.add_violation(
                                    context_expr,
                                    f"pytest.raises({exc_name}) missing 'match' parameter",
                                )
        self.generic_visit(node)

    def add_violation(self, node: ast.AST, message: str) -> None:
        lineno = node.lineno
        line_idx = lineno - 1
        if 0 <= line_idx < len(self.lines):
            line_content = self.lines[line_idx]
            # Support noqa override
            if "noqa: pytest-raises-hygiene" in line_content or "noqa" in line_content:
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

    visitor = PytestRaisesHygieneVisitor(filepath, lines)
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
        print(
            "❌ [pytest-raises-hygiene] Violations found (generic pytest.raises without match):",
            file=sys.stderr,
        )
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: Add a 'match' parameter to pytest.raises(), or add '# noqa: pytest-raises-hygiene' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [pytest-raises-hygiene] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
