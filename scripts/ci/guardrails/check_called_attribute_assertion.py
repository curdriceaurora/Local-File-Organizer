#!/usr/bin/env python3
"""CI-rail: Flag weak `assert x.called` / bare `assert x.call_count` (WP-6.2).

Both prove a mock was invoked at all, not that it was invoked correctly.
Prefer `mock.assert_called_with(...)`, `mock.assert_called_once_with(...)`,
or `assert mock.call_count == N`.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa

_WEAK_ATTRS = {"called", "call_count"}


def _is_weak_attribute_expr(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr in _WEAK_ATTRS


class _Visitor(ast.NodeVisitor):
    def __init__(self, lines: list[str]) -> None:
        self.lines = lines
        self.violations: list[tuple[int, str]] = []

    def visit_Assert(self, node: ast.Assert) -> None:
        test = node.test
        # `assert x.called` / `assert x.call_count` — bare attribute access,
        # no comparison. ast.Compare (e.g. `== 2`) is a different node type
        # and is intentionally not flagged.
        if _is_weak_attribute_expr(test):
            line_idx = node.lineno - 1
            if 0 <= line_idx < len(self.lines) and has_targeted_noqa(
                self.lines[line_idx], "called-attribute-assertion"
            ):
                self.generic_visit(node)
                return
            self.violations.append(
                (
                    node.lineno,
                    f"assert on bare '.{test.attr}' only proves the mock was called, "
                    "not that it was called correctly — use assert_called_with(...) "
                    "or compare call_count to an exact value",
                )
            )
        self.generic_visit(node)


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
        print("❌ [called-attribute-assertion] Violations found:", file=sys.stderr)
        for file_path, lineno, msg in all_violations:
            print(f"  {file_path}:{lineno}: {msg}", file=sys.stderr)
        print(
            "\nFix: use assert_called_with(...) or compare call_count to a value, "
            "or add '# noqa: called-attribute-assertion' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [called-attribute-assertion] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
