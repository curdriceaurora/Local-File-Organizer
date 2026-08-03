#!/usr/bin/env python3
"""CI-rail: Flag ``@patch``-injected test parameters never referenced (#1682).

The copy-paste decay pattern from epic #1678: a ``@patch`` decorator stack
is copied onto a new test, the primary assertion is updated, and the
injected secondary mocks (``mock_update_file``, ...) are never referenced —
so their call contracts are silently unasserted.

Injection semantics (verified empirically, pinned by the rail's tests):

- ``@patch("target")`` injects a parameter; an explicit replacement —
  positional second arg or ``new=`` — injects nothing.
- ``@patch.object(obj, "attr")`` injects; a positional third arg does not.
- ``new_callable=`` and ``autospec=`` still inject.
- Class-level ``@patch`` decorates every ``test_*`` method and injects
  its mock into each of them.

Decorators apply bottom-up and ``_patch`` appends mocks to the call's
positional args — pytest passes fixtures by keyword, so the mocks fill
the FIRST free positional slots. The injected mocks are therefore the
FIRST k parameters after ``self``/``cls`` (verified empirically);
fixtures follow them.

Suppress a finding with ``# noqa: unused-patch-argument`` on the ``def``
line when the patch is intentionally a side-effect suppressor.

Known limitation: decorators are matched on the literal names ``patch`` and
``patch.object``, so an aliased import used as a decorator
(``from unittest.mock import patch as p`` then ``@p(...)``) is invisible to
this rail. No such usage exists in the suite today — the one aliased import
is a context manager, which injects no parameter and is out of scope
either way — so alias resolution is not worth the machinery yet.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa  # type: ignore[no-redef]

RAIL_NAME = "unused-patch-argument"


def _is_patch_call(node: ast.AST) -> tuple[bool, bool]:
    """Return (is_patch, is_patch_object) for a decorator expression."""
    if not isinstance(node, ast.Call):
        return (False, False)
    func = node.func
    # patch(...) / mock.patch(...) / unittest.mock.patch(...)
    if isinstance(func, ast.Name) and func.id == "patch":
        return (True, False)
    if isinstance(func, ast.Attribute) and func.attr == "patch":
        return (True, False)
    # patch.object(...) / mock.patch.object(...)
    if isinstance(func, ast.Attribute) and func.attr == "object":
        inner = func.value
        if isinstance(inner, ast.Name) and inner.id == "patch":
            return (True, True)
        if isinstance(inner, ast.Attribute) and inner.attr == "patch":
            return (True, True)
    return (False, False)


def _injects_parameter(call: ast.Call, is_patch_object: bool) -> bool:
    """Does this patch decorator inject a mock parameter?

    An explicit replacement (positional ``new`` or ``new=`` keyword)
    suppresses injection; ``new_callable=``/``autospec=`` do not.
    """
    if any(kw.arg == "new" for kw in call.keywords):
        return False
    max_positional = 2 if is_patch_object else 1
    return len(call.args) <= max_positional


def _injecting_decorator_count(decorator_list: list[ast.expr]) -> int:
    count = 0
    for decorator in decorator_list:
        is_patch, is_object = _is_patch_call(decorator)
        if is_patch and _injects_parameter(decorator, is_object):
            count += 1
    return count


def _referenced_names(func: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names *read* in the function body — Load and Del contexts only.

    Store is excluded deliberately. ``mock_foo = MagicMock()`` rebinds the
    injected parameter without ever reading it, so counting that as a
    reference would let a write-only shadow hide an unasserted mock. Reading
    an attribute (``mock_foo.assert_called()``) or passing it anywhere is a
    Load on the Name itself, so ordinary use is unaffected.
    """
    names: set[str] = set()
    for stmt in func.body:
        for node in ast.walk(stmt):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load | ast.Del):
                names.add(node.id)
    return names


def _check_function(
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    class_level_count: int,
    lines: list[str],
) -> list[tuple[int, str]]:
    if not func.name.startswith("test"):
        return []
    injected = _injecting_decorator_count(func.decorator_list) + class_level_count
    if injected == 0:
        return []

    params = [a.arg for a in func.args.posonlyargs + func.args.args]
    if params and params[0] in ("self", "cls"):
        params = params[1:]
    mock_params = params[:injected]

    def_line = lines[func.lineno - 1] if func.lineno <= len(lines) else ""
    if has_targeted_noqa(def_line, RAIL_NAME):
        return []

    referenced = _referenced_names(func)
    violations = []
    for param in mock_params:
        if param not in referenced:
            violations.append(
                (
                    func.lineno,
                    f"'{param}' in '{func.name}' is injected by @patch but never "
                    f"referenced — assert its call contract, or add "
                    f"'# noqa: {RAIL_NAME}' if the patch is an intentional suppressor",
                )
            )
    return violations


def check_file(filepath: Path) -> list[tuple[int, str]]:
    """Return (lineno, message) violations for one test file."""
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

    violations: list[tuple[int, str]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            violations.extend(_check_function(node, 0, lines))
        elif isinstance(node, ast.ClassDef):
            class_count = _injecting_decorator_count(node.decorator_list)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    violations.extend(_check_function(item, class_count, lines))
    return sorted(violations)


def _changed_lines_by_file() -> dict[str, set[int]]:
    """Map file -> line numbers added/modified in the staged diff."""
    import re
    import subprocess

    result = subprocess.run(
        ["git", "diff", "--cached", "-U0", "--no-color", "--", "tests/"],
        capture_output=True,
        text=True,
        check=False,
    )
    changed: dict[str, set[int]] = {}
    current: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:]
            changed.setdefault(current, set())
        elif line.startswith("@@") and current is not None:
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                start = int(match.group(1))
                span = int(match.group(2)) if match.group(2) is not None else 1
                changed[current].update(range(start, start + span))
    return changed


def main() -> int:
    """Scan test files; --changed-only restricts to staged-diff lines."""
    args = [a for a in sys.argv[1:] if a != "--changed-only"]
    changed_only = "--changed-only" in sys.argv[1:]

    if args:
        paths = [Path(a) for a in args if a.endswith(".py")]
    else:
        tests_root = Path("tests")
        if not tests_root.exists():
            print("Error: tests directory not found. Run from the repository root.")
            return 1
        paths = sorted(tests_root.rglob("test_*.py"))

    changed = _changed_lines_by_file() if changed_only else None

    all_violations = []
    for path in paths:
        for lineno, msg in check_file(path):
            if changed is not None and lineno not in changed.get(path.as_posix(), set()):
                continue
            all_violations.append((path.as_posix(), lineno, msg))

    if all_violations:
        print(f"❌ [{RAIL_NAME}] Violations found:", file=sys.stderr)
        for file_path, lineno, msg in all_violations:
            print(f"  {file_path}:{lineno}: {msg}", file=sys.stderr)
        print(
            f"\nFix: assert the mock's call contract, remove the unneeded patch, "
            f"or add '# noqa: {RAIL_NAME}' on the def line if intentional.",
            file=sys.stderr,
        )
        return 1

    print(f"✅ [{RAIL_NAME}] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
