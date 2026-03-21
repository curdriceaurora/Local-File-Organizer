"""CI ratchet: T10 predicate negative-case coverage.

Every _is_*/_has_*/_find_* predicate in review_regressions/ detectors
must have at least one ``assert not <predicate_name>(`` call in its
paired unit test file.

Acceptance criteria (issue #930):
- Fails with a clear message listing which predicates are missing negative cases
- All existing predicates pass at merge (backfill done before this merges)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

FO_ROOT = Path(__file__).resolve().parents[2]
DETECTORS_DIR = FO_ROOT / "src" / "file_organizer" / "review_regressions"
UNIT_TESTS_DIR = FO_ROOT / "tests" / "unit" / "review_regressions"

pytestmark = pytest.mark.ci

_MODULE_TO_TEST: dict[str, str] = {
    "correctness": "test_correctness_detectors",
    "security": "test_security_detectors",
    "memory_lifecycle": "test_memory_lifecycle_detectors",
    "test_quality": "test_test_quality_detectors",
    "api_compat": "test_api_compat_detectors",
}


def _collect_predicates(module_path: Path) -> list[str]:
    """Return names of all _is_*/_has_*/_find_* functions in module_path."""
    source = module_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(module_path))
    except SyntaxError:
        return []

    predicates: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = node.name
            if name.startswith(("_is_", "_has_", "_find_")):
                predicates.append(name)
    return predicates


def _has_negative_test(test_path: Path, predicate_name: str) -> bool:
    """Return True if test_path contains 'assert not <predicate_name>('."""
    text = test_path.read_text(encoding="utf-8")
    return f"assert not {predicate_name}(" in text


@pytest.mark.ci
def test_all_predicates_have_negative_cases() -> None:
    """Every predicate in review_regressions/ must have a negative test case."""
    missing: list[str] = []
    for module_stem, test_stem in _MODULE_TO_TEST.items():
        module_path = DETECTORS_DIR / f"{module_stem}.py"
        test_path = UNIT_TESTS_DIR / f"{test_stem}.py"
        if not module_path.exists():
            continue
        predicates = _collect_predicates(module_path)
        for pred in predicates:
            if not test_path.exists() or not _has_negative_test(test_path, pred):
                missing.append(f"{module_stem}.py: {pred}")
    assert not missing, (
        "T10: These predicates are missing negative test cases\n"
        "(add `assert not <predicate_name>(...)` to the paired test file):\n"
        + "\n".join(f"  {m}" for m in missing)
    )
