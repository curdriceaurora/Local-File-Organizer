from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
CLOSEOUT_REPORT_REL = "docs/plans/review-regressions/2026-03-15-issue-813-pr5-and-822-closeout.md"
CLOSEOUT_REPORT_PATH = FO_ROOT / CLOSEOUT_REPORT_REL


def _extract_metadata(text: str) -> dict[str, object]:
    match = re.search(
        r"<!-- REVIEW_REGRESSION_813_822_CLOSEOUT_METADATA_START -->\s*```json\s*(.*?)\s*```"
        r"\s*<!-- REVIEW_REGRESSION_813_822_CLOSEOUT_METADATA_END -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, "#813/#822 closeout metadata block is missing or malformed"
    metadata = json.loads(match.group(1))
    assert isinstance(metadata, dict), "Closeout metadata must decode to a JSON object"
    return metadata


def _assert_test_reference_exists(nodeid: str) -> None:
    path_str, _, test_name = nodeid.partition("::")
    assert test_name, f"Malformed test reference (missing ::test_name): {nodeid!r}"

    path = FO_ROOT / path_str
    assert path.is_file(), f"Closeout references missing test file: {path}"

    source = path.read_text(encoding="utf-8")
    assert f"def {test_name}(" in source, (
        f"Closeout references missing test function {test_name!r} in {path}"
    )


def test_issue_813_822_closeout_metadata_recomputes_and_meets_target() -> None:
    assert CLOSEOUT_REPORT_PATH.is_file(), f"Missing closeout report: {CLOSEOUT_REPORT_PATH}"
    metadata = _extract_metadata(CLOSEOUT_REPORT_PATH.read_text(encoding="utf-8"))

    baseline_total = metadata["baseline_total_findings"]
    covered_ids = metadata["covered_finding_ids"]
    uncovered_ids = metadata["uncovered_finding_ids"]
    coverage_target_minimum = metadata["coverage_target_minimum"]

    assert isinstance(baseline_total, int) and baseline_total == 19
    assert isinstance(coverage_target_minimum, int) and coverage_target_minimum == 12
    assert isinstance(covered_ids, list)
    assert isinstance(uncovered_ids, list)

    covered_set = {int(item) for item in covered_ids}
    uncovered_set = {int(item) for item in uncovered_ids}

    assert covered_set.isdisjoint(uncovered_set)
    assert covered_set | uncovered_set == set(range(1, baseline_total + 1))

    covered_count = len(covered_set)
    uncovered_count = len(uncovered_set)
    recomputed_percent = round((covered_count / baseline_total) * 100, 1)

    coverage_recomputed = metadata["coverage_recomputed"]
    assert isinstance(coverage_recomputed, dict)
    assert coverage_recomputed["covered"] == covered_count
    assert coverage_recomputed["uncovered"] == uncovered_count
    assert coverage_recomputed["coverage_percent"] == recomputed_percent

    assert covered_count >= coverage_target_minimum


def test_issue_813_822_closeout_finding_map_references_live_tests() -> None:
    assert CLOSEOUT_REPORT_PATH.is_file(), f"Missing closeout report: {CLOSEOUT_REPORT_PATH}"
    metadata = _extract_metadata(CLOSEOUT_REPORT_PATH.read_text(encoding="utf-8"))

    finding_map = metadata["finding_map"]
    assert isinstance(finding_map, list)
    assert len(finding_map) == 19

    seen_ids: set[int] = set()
    for entry in finding_map:
        assert isinstance(entry, dict)
        finding_id = int(entry["id"])
        covered = bool(entry["covered"])
        tests = entry["enforcing_tests"]

        assert finding_id not in seen_ids, f"Duplicate finding id in closeout map: {finding_id}"
        seen_ids.add(finding_id)

        assert isinstance(tests, list)
        if covered:
            assert tests, f"Covered finding {finding_id} must map to at least one enforcing test"
            for nodeid in tests:
                assert isinstance(nodeid, str)
                _assert_test_reference_exists(nodeid)
        else:
            assert tests == [], f"Uncovered finding {finding_id} should not claim enforcing tests"

    assert seen_ids == set(range(1, 20))
