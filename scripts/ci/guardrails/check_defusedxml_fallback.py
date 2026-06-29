#!/usr/bin/env python3
"""CI-rail: Ensure defusedxml is used instead of standard library xml (WP-6.1).

Flags any standard library xml imports (e.g., xml.etree, xml.dom) to prevent
XML External Entity (XXE) injection vulnerabilities.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa


class DefusedXmlVisitor(ast.NodeVisitor):
    """AST visitor to find standard xml module imports."""

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "xml" or alias.name.startswith("xml."):
                self.add_violation(node, f"standard library import '{alias.name}' is unsafe")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "xml" or (node.module and node.module.startswith("xml.")):
            self.add_violation(node, f"standard library import from '{node.module}' is unsafe")
        self.generic_visit(node)

    def add_violation(self, node: ast.AST, message: str) -> None:
        lineno = node.lineno
        line_idx = lineno - 1
        if 0 <= line_idx < len(self.lines):
            line_content = self.lines[line_idx]
            if has_targeted_noqa(line_content, "defusedxml-fallback"):
                return
            self.violations.append((lineno, message, line_content.strip()))


def check_file(filepath: Path) -> list[tuple[int, str, str]]:
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

    visitor = DefusedXmlVisitor(filepath, lines)
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    """Scan all source files under src/file_organizer/."""
    package_root = Path("src/file_organizer")
    if not package_root.exists():
        print("Error: src/file_organizer directory not found. Run from the repository root.")
        return 1

    all_violations = []
    # Scan all python files recursively
    for path in package_root.rglob("*.py"):
        violations = check_file(path)
        for lineno, msg, line in violations:
            all_violations.append((path.as_posix(), lineno, msg, line))

    if all_violations:
        print("❌ [defusedxml-fallback] Violations found (unsafe XML imports):", file=sys.stderr)
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: Import from 'defusedxml' instead of standard 'xml', or add '# noqa: defusedxml-fallback' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [defusedxml-fallback] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
