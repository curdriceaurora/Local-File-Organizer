from __future__ import annotations

import re
from pathlib import Path

import pytest

from file_organizer.review_regressions.correctness import CORRECTNESS_DETECTORS
from file_organizer.review_regressions.framework import (
    ReviewRegressionDetector,
    Violation,
    run_audit,
)
from file_organizer.review_regressions.security import SECURITY_DETECTORS
from file_organizer.review_regressions.test_quality import TEST_QUALITY_DETECTORS

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_ROOT = FO_ROOT / "tests" / "fixtures" / "review_regressions"
ALL_FIRST_WAVE_DETECTORS = (
    *CORRECTNESS_DETECTORS,
    *SECURITY_DETECTORS,
    *TEST_QUALITY_DETECTORS,
)
EXPECTED_FIRST_WAVE_DETECTOR_IDS = {
    "correctness.active-model-primitive-store",
    "correctness.stage-context-validation-bypass",
    "security.guarded-context-direct-path",
    "security.validated-path-bypass",
    "test-quality.weak-mock-call-count-lower-bound",
}
FORMATTED_VIOLATION_PATTERN = re.compile(
    r"^rule_id=(?P<rule_id>\S+) path=(?P<path>.+?) line=(?P<line>-|\d+) reason=(?P<reason>.+)$"
)


def _format_violation(violation: Violation) -> str:
    line = violation.line if violation.line is not None else "-"
    return (
        f"rule_id={violation.rule_id} path={violation.path} line={line} reason={violation.message}"
    )


def _assert_no_findings(*, context: str, findings: tuple[Violation, ...]) -> None:
    if not findings:
        return
    details = "\n".join(_format_violation(violation) for violation in findings)
    pytest.fail(f"{context}: expected zero findings, found {len(findings)}\n{details}")


def _assert_formatted_violations_have_required_structure(lines: list[str]) -> None:
    invalid_lines = [line for line in lines if FORMATTED_VIOLATION_PATTERN.fullmatch(line) is None]
    assert not invalid_lines, (
        "Expected every formatted violation to match "
        "'rule_id=<id> path=<path> line=<line|-> reason=<message>' structure.\n"
        + "\n".join(invalid_lines)
    )


def _assert_each_detector_reports_findings(
    *,
    detectors: tuple[ReviewRegressionDetector, ...],
    findings: tuple[Violation, ...],
    rule_class: str,
) -> None:
    expected_detector_ids = {detector.detector_id for detector in detectors}
    reported_detector_ids = {violation.detector_id for violation in findings}
    missing_detector_ids = sorted(expected_detector_ids - reported_detector_ids)
    assert not missing_detector_ids, (
        f"Expected seeded {rule_class} fixtures to exercise every detector; missing findings for: "
        + ", ".join(missing_detector_ids)
    )


def test_first_wave_repo_enforcement_reports_zero_findings() -> None:
    """Main repo must stay at zero findings for all first-wave detectors."""
    report = run_audit(FO_ROOT, ALL_FIRST_WAVE_DETECTORS)
    detector_ids = {detector.detector_id for detector in report.detectors}

    assert detector_ids == EXPECTED_FIRST_WAVE_DETECTOR_IDS
    _assert_no_findings(context="First-wave enforcement", findings=report.findings)


@pytest.mark.parametrize(
    ("rule_class", "fixture_subdir", "detectors"),
    [
        ("security", "security", SECURITY_DETECTORS),
        ("correctness", "correctness", CORRECTNESS_DETECTORS),
        ("test-quality", "test_quality", TEST_QUALITY_DETECTORS),
    ],
)
def test_seeded_fixture_violations_are_detected_for_each_first_wave_class(
    rule_class: str,
    fixture_subdir: str,
    detectors: tuple[ReviewRegressionDetector, ...],
) -> None:
    """Seeded fixture violations prove each first-wave class fails when regressed."""
    report = run_audit(FIXTURES_ROOT / fixture_subdir, detectors)
    assert report.findings, f"Expected seeded {rule_class} fixture violations"
    assert all(violation.rule_class == rule_class for violation in report.findings)
    _assert_each_detector_reports_findings(
        detectors=detectors,
        findings=report.findings,
        rule_class=rule_class,
    )

    formatted = [_format_violation(violation) for violation in report.findings]
    _assert_formatted_violations_have_required_structure(formatted)
