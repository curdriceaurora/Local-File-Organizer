#!/usr/bin/env python3
"""T10 pre-commit hook: verify every _is_*/_has_*/_find_* predicate in
review_regressions/ detector modules has a paired negative test case.

Exit 0 if all predicates are covered; exit 1 and print a clear message
listing the missing cases otherwise.

Usage (called by pre-commit with staged file paths as argv):
    python .claude/scripts/check_predicate_negative_coverage.py [paths...]

The hook is triggered on changes to detector modules OR their test files.
When detector files are staged it checks those modules; when test files are
staged it checks the corresponding detector modules.  Either way it only
re-checks modules touched in this commit.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

FO_ROOT = Path(__file__).resolve().parents[2]
DETECTORS_DIR = FO_ROOT / "src" / "file_organizer" / "review_regressions"
UNIT_TESTS_DIR = FO_ROOT / "tests" / "unit" / "review_regressions"

# Maps detector module stem → test module stem
_MODULE_TO_TEST: dict[str, str] = {
    "correctness": "test_correctness_detectors",
    "security": "test_security_detectors",
    "memory_lifecycle": "test_memory_lifecycle_detectors",
    "test_quality": "test_test_quality_detectors",
    "api_compat": "test_api_compat_detectors",
}
_TEST_TO_MODULE: dict[str, str] = {v: k for k, v in _MODULE_TO_TEST.items()}


def collect_predicates(module_path: Path) -> list[str]:
    """Return names of all _is_*/_has_*/_find_* functions in module_path."""
    try:
        source = module_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(module_path))
    except (OSError, SyntaxError):
        return []
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith(("_is_", "_has_", "_find_"))
    ]


def has_negative_test(test_path: Path, predicate_name: str) -> bool:
    """Return True if test_path contains 'assert not <predicate_name>('."""
    try:
        text = test_path.read_text(encoding="utf-8")
    except OSError:
        return False
    return f"assert not {predicate_name}(" in text


def _affected_module_stems(staged_paths: list[Path]) -> set[str]:
    """Derive which detector module stems are affected by the staged paths."""
    stems: set[str] = set()
    for path in staged_paths:
        rel = path.relative_to(FO_ROOT) if path.is_absolute() else path
        rel_str = str(rel)
        # Detector file staged directly
        if rel_str.startswith("src/file_organizer/review_regressions/"):
            stem = path.stem
            if stem in _MODULE_TO_TEST:
                stems.add(stem)
        # Test file staged — look up the corresponding detector
        elif rel_str.startswith("tests/unit/review_regressions/test_"):
            test_stem = path.stem
            if test_stem in _TEST_TO_MODULE:
                stems.add(_TEST_TO_MODULE[test_stem])
    return stems


def check(module_stems: set[str] | None = None) -> list[str]:
    """Return list of 'module.py: predicate' strings that are missing negative tests.

    If module_stems is None, check all known modules (full scan).
    """
    to_check = module_stems if module_stems is not None else set(_MODULE_TO_TEST)
    missing: list[str] = []
    for stem in sorted(to_check):
        if stem not in _MODULE_TO_TEST:
            continue
        module_path = DETECTORS_DIR / f"{stem}.py"
        test_path = UNIT_TESTS_DIR / f"{_MODULE_TO_TEST[stem]}.py"
        if not module_path.exists():
            continue
        for pred in collect_predicates(module_path):
            if not test_path.exists() or not has_negative_test(test_path, pred):
                missing.append(f"{stem}.py: {pred}")
    return missing


def main(argv: list[str]) -> int:
    """Entry point for pre-commit hook."""
    staged = [Path(p) for p in argv] if argv else []
    module_stems = _affected_module_stems(staged) if staged else None

    if module_stems is not None and not module_stems:
        # Staged files matched the hook glob but none map to a known module
        return 0

    missing = check(module_stems)
    if not missing:
        return 0

    print(
        "T10: These predicates are missing negative test cases\n"
        "(add `assert not <predicate_name>(...)` to the paired test file):\n"
        + "\n".join(f"  {m}" for m in missing),
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
