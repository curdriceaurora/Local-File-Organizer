#!/usr/bin/env python3
"""CI-rail: Flag raw open(), Path.open(), and shutil copy/move functions (WP-6.1).

Enforces using SafeDir / SafeDir-validated paths for all file operations
except in designated primitive/utility modules.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa

# Paths that are allowed to perform raw file operations (the primitives themselves)
ALLOWED_PATHS = {
    "src/file_organizer/utils/safedir.py",
    "src/file_organizer/utils/atomic_io.py",
    "src/file_organizer/utils/atomic_write.py",
    "src/file_organizer/core/path_guard.py",
}

# Third-party and stdlib library namespaces whose `.open()` methods are NOT raw
# filesystem path operations on caller-supplied paths (e.g. Image.open() is a
# PIL/Pillow decode call, os.open() returns a low-level file descriptor, etc.).
# These are excluded from the Path.open() check to avoid detector overreach.
_OPEN_EXEMPT_NAMESPACES: frozenset[str] = frozenset(
    {
        "os",  # os.open() → low-level fd, not a Python file object
        "Image",  # PIL/Pillow image decode
        "fitz",  # PyMuPDF document open
        "tarfile",  # stdlib tar archive open
        "tokenize",  # stdlib tokenize.open() — encoding-aware source reader
        "aiofiles",  # async file I/O library
        "zipfile",  # stdlib ZipFile.open()
        "cv2",  # OpenCV image read
        "PIL",  # PIL package-level alias
        "wave",  # stdlib wave.open()
    }
)


def _open_receiver_name(node: ast.Attribute) -> str | None:
    """Return the simple name of the receiver of a `.open()` attribute call.

    For ``Image.open(...)`` the receiver is ``Image`` (a Name node).
    For ``self.Image.open(...)`` the receiver is the inner Attribute whose
    attr is ``Image``; we return that attr name.
    Returns ``None`` when the receiver shape is too complex to inspect.
    """
    receiver = node.value
    if isinstance(receiver, ast.Name):
        return receiver.id
    if isinstance(receiver, ast.Attribute):
        # Handles chained access like ``self.Image.open(...)``
        return receiver.attr
    return None


class SafeDirVisitor(ast.NodeVisitor):
    """AST visitor to find raw file operations."""

    def __init__(self, filepath: Path, lines: list[str]) -> None:
        self.filepath = filepath
        self.lines = lines
        self.violations: list[tuple[int, str, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        # 1. Check for raw built-in open()
        if isinstance(node.func, ast.Name) and node.func.id == "open":
            self.add_violation(node, "raw open() call")

        # 2. Check for Path.open() — but exclude known library namespaces whose
        #    `.open()` is not a raw filesystem call on a caller-supplied path.
        elif isinstance(node.func, ast.Attribute) and node.func.attr == "open":
            receiver_name = _open_receiver_name(node.func)
            if receiver_name not in _OPEN_EXEMPT_NAMESPACES:
                self.add_violation(node, "raw Path.open() call")

        # 3. Check for shutil copy/move/etc.
        elif (
            isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "shutil"
        ):
            if node.func.attr in {
                "copy",
                "copy2",
                "move",
                "copyfile",
                "copytree",
                "copymode",
                "copystat",
            }:
                self.add_violation(node, f"raw shutil.{node.func.attr}() call")

        self.generic_visit(node)

    def add_violation(self, node: ast.AST, message: str) -> None:
        lineno = node.lineno
        line_idx = lineno - 1
        if 0 <= line_idx < len(self.lines):
            line_content = self.lines[line_idx]
            if has_targeted_noqa(line_content, "safedir-required"):
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

    visitor = SafeDirVisitor(filepath, lines)
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
        print("❌ [safedir-required] Violations found (raw file operations):", file=sys.stderr)
        for file_path, lineno, msg, line in all_violations:
            print(f"  {file_path}:{lineno}: {msg} -> `{line}`", file=sys.stderr)
        print(
            "\nFix: Use SafeDir to perform file operations, or add '# noqa: safedir-required' if exempt.",
            file=sys.stderr,
        )
        return 1

    print("✅ [safedir-required] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
