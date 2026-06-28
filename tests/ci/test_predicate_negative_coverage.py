"""CI ratchet: T10 predicate negative-case coverage.

Every _is_*/_has_*/_find_* predicate in review_regressions/ detectors
must have at least one ``assert not <predicate_name>(`` call in its
paired unit test file.

Acceptance criteria (issue #930):
- Fails with a clear message listing which predicates are missing negative cases
- All existing predicates pass at merge (backfill done before this merges)

The check logic lives in scripts/ci/guardrails/check_predicate_negative_coverage.py
(shared with the pre-commit hook added in issue #931).  This test is a
backstop that runs the full-scan path on every CI run.
"""

from __future__ import annotations

import pytest

from scripts.ci.guardrails import check_predicate_negative_coverage

pytestmark = pytest.mark.ci


@pytest.mark.ci
def test_all_predicates_have_negative_cases() -> None:
    """Every predicate in review_regressions/ must have a negative test case."""
    missing = check_predicate_negative_coverage.check()
    assert not missing, (
        "T10: These predicates are missing negative test cases\n"
        "(add `assert not <predicate_name>(...)` to the paired test file):\n"
        + "\n".join(f"  {m}" for m in missing)
    )
