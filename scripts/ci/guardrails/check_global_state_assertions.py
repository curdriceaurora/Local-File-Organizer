#!/usr/bin/env python3
"""CI-rail: Flag test assertions over process-global channels (#1721).

Every flake fixed in #1720 was the same mistake wearing a different hat: a
test reached for something process-global when it meant something specific.
Unrelated code touches the same global, and the test then fails by import
order, Python version, or worker placement — never on a developer machine.

The three shapes seen, all from real failures:

1. ``monkeypatch.setattr(sys, "platform", "win32")`` mutates the REAL sys
   module. ``ext.sys`` IS ``sys``; there is no module-local copy. Anything
   first-imported inside that window sees the lie — ``pydub.utils`` calls
   ``shutil.which("ffmpeg")`` at import, whose win32 branch dereferences
   ``_winapi``, ``None`` off Windows. Patch the module under test's own
   ``sys`` reference instead.

2. ``patch("logging.Logger.error")`` patches the Logger CLASS, so the mock
   records error() from every logger in the process. One unrelated library
   log turns ``assert_called_once`` into "Called 2 times". Patch the
   module's own logger object instead.

3. ``assert result.stdout.strip() == "1,3"`` compares a whole captured
   stream. A library printing on import (PyMuPDF's ``fitz`` notice) lands in
   the same stream. Print a marked line and assert on that.

Suppress with ``# noqa: global-state-assertion`` on the offending line when
the global really is the subject under test.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

try:
    from scripts.ci.guardrails.suppressions import has_targeted_noqa
except ModuleNotFoundError:  # pragma: no cover - direct script execution path
    from suppressions import has_targeted_noqa  # type: ignore[no-redef]

RAIL_NAME = "global-state-assertion"

#: Attribute of the real ``sys`` module whose mutation has bitten us. Kept
#: narrow on purpose: ``sys.argv`` and ``sys.modules`` are mutated routinely
#: and legitimately, and flagging those would drown the signal.
_GUARDED_SYS_ATTRS = frozenset({"platform"})

#: Streams that belong to the whole process, not to the code under test.
_CAPTURED_STREAM_ATTRS = frozenset({"stdout", "stderr", "out", "err"})


def _targets_sys_module(node: ast.expr) -> bool:
    """True if *node* names the real ``sys`` module — bare or ``pkg.mod.sys``."""
    if isinstance(node, ast.Name):
        return node.id == "sys"
    if isinstance(node, ast.Attribute):
        return node.attr == "sys"
    return False


def _check_sys_mutation(node: ast.Call) -> str | None:
    """Rule 1: ``setattr(<...>.sys, "platform", ...)`` on the real sys module."""
    func = node.func
    is_setattr = (isinstance(func, ast.Name) and func.id == "setattr") or (
        isinstance(func, ast.Attribute) and func.attr == "setattr"
    )
    if not is_setattr or len(node.args) < 2:
        return None
    if not _targets_sys_module(node.args[0]):
        return None
    attr = node.args[1]
    if not (isinstance(attr, ast.Constant) and attr.value in _GUARDED_SYS_ATTRS):
        return None
    return (
        f"mutates the real sys module's '{attr.value}' process-wide — anything "
        f"first-imported during this window sees it. Patch the module under "
        f"test's own 'sys' reference instead "
        f"(monkeypatch.setattr(mod, 'sys', SimpleNamespace(platform=...)))"
    )


def _check_logger_class_patch(node: ast.Call) -> str | None:
    """Rule 2: patching ``logging.Logger`` itself rather than a logger."""
    func = node.func
    is_patch = (isinstance(func, ast.Name) and func.id == "patch") or (
        isinstance(func, ast.Attribute) and func.attr == "patch"
    )
    if is_patch and node.args:
        first = node.args[0]
        if (
            isinstance(first, ast.Constant)
            and isinstance(first.value, str)
            and first.value.startswith("logging.Logger.")
        ):
            method = first.value.rsplit(".", 1)[-1]
            return (
                f"patches the Logger class, so it records '{method}' from every "
                f"logger in the process. Patch the module's own logger instead "
                f"(patch.object(mod.logger, '{method}'))"
            )
    # patch.object(logging.Logger, "error")
    if isinstance(func, ast.Attribute) and func.attr == "object" and len(node.args) >= 2:
        target = node.args[0]
        if isinstance(target, ast.Attribute) and target.attr == "Logger":
            attr = node.args[1]
            method = attr.value if isinstance(attr, ast.Constant) else "<attr>"
            return (
                f"patches the Logger class, so it records '{method}' from every "
                f"logger in the process. Patch the module's own logger instead"
            )
    return None


def _is_captured_stream(node: ast.expr) -> bool:
    """True for ``x.stdout``, ``x.stdout.strip()``, ``capsys.readouterr().out``."""
    if isinstance(node, ast.Call):  # .strip() and friends
        return _is_captured_stream(node.func)
    if isinstance(node, ast.Attribute):
        if node.attr in _CAPTURED_STREAM_ATTRS:
            return True
        # unwrap .strip / .lower / ... applied to a stream
        return node.attr in {"strip", "lower", "rstrip", "lstrip"} and _is_captured_stream(
            node.value
        )
    return False


def _check_whole_stream_equality(node: ast.Compare) -> str | None:
    """Rule 3: exact equality against an entire captured stream."""
    if not node.ops or not isinstance(node.ops[0], ast.Eq):
        return None
    right = node.comparators[0]
    if not (isinstance(right, ast.Constant) and isinstance(right.value, str)):
        return None
    if not _is_captured_stream(node.left):
        return None
    return (
        "compares an entire captured stream for equality — a library printing "
        "on import lands in the same stream. Assert on a marked line, a parsed "
        "field, or membership instead"
    )


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
    for node in ast.walk(tree):
        message = None
        if isinstance(node, ast.Call):
            message = _check_sys_mutation(node) or _check_logger_class_patch(node)
        elif isinstance(node, ast.Compare):
            message = _check_whole_stream_equality(node)
        if message is None:
            continue
        line = lines[node.lineno - 1] if node.lineno <= len(lines) else ""
        if has_targeted_noqa(line, RAIL_NAME):
            continue
        violations.append((node.lineno, message))
    return sorted(set(violations))


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
            f"\nFix: scope the patch to the module under test, or assert on your "
            f"own marked output. Add '# noqa: {RAIL_NAME}' if the global really "
            f"is the subject under test.",
            file=sys.stderr,
        )
        return 1

    print(f"✅ [{RAIL_NAME}] No violations found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
