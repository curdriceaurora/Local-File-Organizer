#!/usr/bin/env python3
"""CI-rail: Flag raw write operations on files (WP-6.1).

Enforces using atomic_write / SafeDir primitives for all file writing
operations except in designated primitive/utility modules.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa

# Paths that are allowed to perform raw write operations (the primitives themselves)
ALLOWED_PATHS = {
    "src/file_organizer/utils/atomic_write.py",
    "src/file_organizer/utils/atomic_io.py",
    "src/file_organizer/utils/safedir.py",
    "src/file_organizer/core/path_guard.py",
}


class AtomicWriteVisitor(ast.NodeVisitor):
    """AST visitor to find raw file write operations."""

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        # 1. Check for built-in open() with write/append/exclusive modes
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            is_write = False
            # Check positional args (second arg is usually the mode)
            if len(node.args) >= 2:
                mode_arg = node.args[1]
                if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
                    if any(char in mode_arg.value for char in "wax+"):
                        is_write = True
            # Check keyword args (mode=...)
            for kw in node.keywords:
                if (
                    kw.arg == "mode"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    if any(char in kw.value.value for char in "wax+"):
                        is_write = True

            if is_write:
                self.add_violation(node, "raw open() with write/append/exclusive mode")

        # 2. Check for Path.open() with write/append/exclusive modes
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "open":
            is_write = False
            # Check positional args (first arg is usually the mode for Path.open())
            if len(node.args) >= 1:
                mode_arg = node.args[0]
                if isinstance(mode_arg, ast.Constant) and isinstance(mode_arg.value, str):
                    if any(char in mode_arg.value for char in "wax+"):
                        is_write = True
            # Check keyword args (mode=...)
            for kw in node.keywords:
                if (
                    kw.arg == "mode"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    if any(char in kw.value.value for char in "wax+"):
                        is_write = True

            if is_write:
                self.add_violation(node, "raw Path.open() with write/append/exclusive mode")

        # 3. Check for Path.write_text() or Path.write_bytes()
        elif isinstance(node.func, ast.Attribute) and node.func.attr in {
            "write_text",
            "write_bytes",
        }:
            self.add_violation(node, f"raw Path.{node.func.attr}() call")

        self.generic_visit(node)

    def add_violation(self, node: ast.AST, message: str) -> None:
        lineno = node.lineno
        line_idx = lineno - 1
        if 0 <= line_idx < len(self.lines):
            line_content = self.lines[line_idx]
            # Only allow targeted suppression for this rail.
            if has_targeted_noqa(line_content, "atomic-write"):
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

    visitor = AtomicWriteVisitor(filepath, lines)
    visitor.visit(tree)
    return visitor.violations


def main() -> int:
    """Scan all source files under src/file_organizer/."""
    package_root = Path("src/file_organizer")
    if not package_root.exists():
        print("Error: src/file_organizer directory not found. Run from the repository root.")
        return 1

    all_violations = []
    # Recursively find all python files
    for path in package_root.rglob("*.py"):
        # Check if the path is in the allowed list
        rel_path = path.as_posix()
        if any(rel_path.endswith(allowed) for allowed in ALLOWED_PATHS):
            continue

        violations = check_file(path)
        for lineno, msg, line in violations:
            all_violations.append((rel_path, lineno, msg, line))

    if all_violations:
        print("❌ [atomic-write] Violations found (raw write operations):", file=sys.stderr)
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: Use atomic_write() to write files, or add '# noqa: atomic-write' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [atomic-write] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
