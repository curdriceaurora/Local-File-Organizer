#!/usr/bin/env python3
"""CI-rail: Flag hardcoded absolute file paths in tests (WP-6.2).

Ensures that tests are portable and do not contain hardcoded absolute
system paths like /tmp/foo or C:\\test, enforcing the use of tmp_path instead.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa

# Match absolute paths:
# 1. Unix absolute paths starting with common system roots (to avoid URL paths like /api/v1)
UNIX_ABS_PATH_PAT = re.compile(r"^/(tmp|usr|var|etc|private|Users|home|bin|opt|var|srv)(/|$)")
# 2. Windows absolute paths starting with a drive letter
WIN_ABS_PATH_PAT = re.compile(r"^[a-zA-Z]:\\")


class TestHardcodedPathVisitor(ast.NodeVisitor):
    """AST visitor to find hardcoded absolute paths in tests."""

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            val = node.value.strip()
            # Check for absolute paths
            if UNIX_ABS_PATH_PAT.match(val) or WIN_ABS_PATH_PAT.match(val):
                self.add_violation(node, f"hardcoded absolute path '{val}' found in test")
        self.generic_visit(node)

    def add_violation(self, node: ast.AST, message: str) -> None:
        lineno = node.lineno
        line_idx = lineno - 1
        if 0 <= line_idx < len(self.lines):
            line_content = self.lines[line_idx]
            if has_targeted_noqa(line_content, "test-hardcoded-paths"):
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

    visitor = TestHardcodedPathVisitor(filepath, lines)
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
            "❌ [test-hardcoded-paths] Violations found (hardcoded absolute paths):",
            file=sys.stderr,
        )
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: Use the pytest 'tmp_path' fixture or relative paths, or add '# noqa: test-hardcoded-paths' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [test-hardcoded-paths] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
