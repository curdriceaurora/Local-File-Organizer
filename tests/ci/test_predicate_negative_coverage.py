"""CI ratchet: T10 predicate negative-case coverage.

Every _is_*/_has_*/_find_* predicate in review_regressions/ detectors
must have at least one ``assert not <predicate_name>(`` call in its
paired unit test file.

Acceptance criteria (issue #930):
- Fails with a clear message listing which predicates are missing negative cases
- All existing predicates pass at merge (backfill done before this merges)

The check logic lives in .claude/scripts/check_predicate_negative_coverage.py
(shared with the pre-commit hook added in issue #931).  This test is a
backstop that runs the full-scan path on every CI run.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

_SCRIPT = (
    Path(__file__).resolve().parents[2]
    / ".claude"
    / "scripts"
    / "check_predicate_negative_coverage.py"
)


def _load_checker():
    """Load the shared hook script as a module; fail loudly if missing or malformed."""
    spec = importlib.util.spec_from_file_location("check_predicate_negative_coverage", _SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Cannot load predicate coverage script — file not found or unreadable: {_SCRIPT}"
        )
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except (SyntaxError, Exception) as exc:
        raise RuntimeError(f"Failed to load predicate coverage script {_SCRIPT}: {exc}") from exc
    return mod


@pytest.mark.ci
def test_all_predicates_have_negative_cases() -> None:
    """Every predicate in review_regressions/ must have a negative test case."""
    checker = _load_checker()
    missing = checker.check()
    assert not missing, (
        "T10: These predicates are missing negative test cases\n"
        "(add `assert not <predicate_name>(...)` to the paired test file):\n"
        + "\n".join(f"  {m}" for m in missing)
    )
