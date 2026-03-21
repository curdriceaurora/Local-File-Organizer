from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.review_regressions.framework import run_audit
from file_organizer.review_regressions.memory_lifecycle import MEMORY_LIFECYCLE_DETECTORS

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = FO_ROOT / "tests" / "fixtures" / "review_regressions" / "memory_lifecycle"

EXPECTED_MEMORY_LIFECYCLE_DETECTOR_IDS = {
    "memory-lifecycle.absolute-rss-in-batch-feedback",
    "memory-lifecycle.eager-buffer-pool-allocation",
    "memory-lifecycle.legacy-acquire-release-without-consume",
    "memory-lifecycle.pooled-buffer-ownership-via-length",
}


def test_memory_lifecycle_repo_enforcement_reports_zero_findings() -> None:
    report = run_audit(FO_ROOT, MEMORY_LIFECYCLE_DETECTORS)
    detector_ids = {detector.detector_id for detector in report.detectors}

    assert detector_ids == EXPECTED_MEMORY_LIFECYCLE_DETECTOR_IDS
    assert not report.findings, (
        "Memory-lifecycle guardrail found violations in repository source:\n"
        + "\n".join(
            f"{finding.path}:{finding.line or '-'} {finding.rule_id} {finding.message}"
            for finding in report.findings
        )
    )


def test_seeded_memory_lifecycle_fixtures_trigger_all_rules() -> None:
    report = run_audit(FIXTURE_ROOT, MEMORY_LIFECYCLE_DETECTORS)

    assert report.findings
    found_rule_ids = {finding.rule_id for finding in report.findings}
    assert found_rule_ids == {
        "absolute-rss-in-batch-feedback",
        "eager-buffer-pool-allocation",
        "legacy-acquire-release-without-consume",
        "pooled-buffer-ownership-via-length",
    }
    assert all(finding.rule_class == "memory-lifecycle" for finding in report.findings)
