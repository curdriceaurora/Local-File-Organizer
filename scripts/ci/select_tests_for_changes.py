#!/usr/bin/env python3
"""Map changed src files to their corresponding test files (WP-6.2).

Convention: src/file_organizer/X/y.py <-> tests/X/test_y.py (the
project's existing 1:1 module-to-test-file naming, e.g.
src/file_organizer/core/organizer.py <-> tests/core/test_organizer.py).
A changed test file maps to itself. Unmapped or non-Python changed
files are silently skipped — this is a best-effort speed-up, not a
completeness guarantee.

Usage:
    git diff --name-only origin/main... | python scripts/ci/select_tests_for_changes.py
    pytest $(git diff --name-only origin/main... | python scripts/ci/select_tests_for_changes.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

_SRC_PREFIX = "src/file_organizer/"
_TESTS_PREFIX = "tests/"


def select_tests(changed_files: list[str], tests_root: Path) -> list[str]:
    """Return sorted, de-duplicated relative test-file paths for *changed_files*."""
    base = tests_root.parent
    selected: set[str] = set()

    for changed in changed_files:
        normalized = changed.replace("\\", "/")
        if not normalized.endswith(".py"):
            continue

        if normalized.startswith(_TESTS_PREFIX):
            candidate = base / normalized
            if candidate.is_file():
                selected.add(str(candidate.relative_to(base)))
            continue

        if not normalized.startswith(_SRC_PREFIX):
            continue

        rel = normalized[len(_SRC_PREFIX) :]
        rel_path = Path(rel)
        test_candidate = tests_root / rel_path.parent / f"test_{rel_path.name}"
        if test_candidate.is_file():
            selected.add(str(test_candidate.relative_to(base)))

    return sorted(selected)


def main() -> int:
    changed_files = [line.strip() for line in sys.stdin if line.strip()]
    tests_root = Path("tests")
    if not tests_root.exists():
        print("Error: tests directory not found. Run from the repository root.", file=sys.stderr)
        return 1

    for path in select_tests(changed_files, tests_root):
        print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
