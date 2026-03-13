from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_ARTIFACT_REL = "docs/plans/review-regressions/2026-03-13-first-wave-audit.json"
CORRECTNESS_REMEDIATION_ARTIFACT_REL = (
    "docs/plans/review-regressions/2026-03-13-correctness-remediation-audit.json"
)
CORRECTNESS_REMEDIATION_REPORT_REL = (
    "docs/plans/review-regressions/2026-03-13-correctness-remediation-report.md"
)
BASELINE_PATH = FO_ROOT / BASELINE_ARTIFACT_REL
CORRECTNESS_PATH = FO_ROOT / CORRECTNESS_REMEDIATION_ARTIFACT_REL
REPORT_PATH = FO_ROOT / CORRECTNESS_REMEDIATION_REPORT_REL
EXPECTED_CORRECTNESS_DETECTOR_IDS = {
    "correctness.active-model-primitive-store",
    "correctness.stage-context-validation-bypass",
}


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _typed_findings(report: Mapping[str, object], *, source: str) -> list[dict[str, object]]:
    findings = report.get("findings")
    assert isinstance(findings, list), (
        f"{source}: expected 'findings' to be a list, got {type(findings).__name__}"
    )
    for index, finding in enumerate(findings):
        assert isinstance(finding, dict), (
            f"{source}: expected finding[{index}] to be a dict, got {type(finding).__name__}"
        )
    return findings


def _typed_detectors(report: Mapping[str, object], *, source: str) -> list[dict[str, object]]:
    detectors = report.get("detectors")
    assert isinstance(detectors, list), (
        f"{source}: expected 'detectors' to be a list, got {type(detectors).__name__}"
    )
    for index, detector in enumerate(detectors):
        assert isinstance(detector, dict), (
            f"{source}: expected detector[{index}] to be a dict, got {type(detector).__name__}"
        )
    return detectors


def _correctness_finding_count(report: Mapping[str, object], *, source: str) -> int:
    findings = _typed_findings(report, source=source)
    return sum(
        1
        for finding in findings
        if finding.get("rule_class") == "correctness" or finding.get("class") == "correctness"
    )


def _suppression_count(report: Mapping[str, object], *, source: str) -> int:
    findings = _typed_findings(report, source=source)
    return sum(
        1
        for finding in findings
        if finding.get("suppressed") is True
        and (finding.get("rule_class") == "correctness" or finding.get("class") == "correctness")
    )


def _extract_metadata(text: str) -> dict[str, object]:
    match = re.search(
        r"<!-- REVIEW_REGRESSION_CORRECTNESS_REMEDIATION_METADATA_START -->\s*```json\s*(.*?)\s*```"
        r"\s*<!-- REVIEW_REGRESSION_CORRECTNESS_REMEDIATION_METADATA_END -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, (
        "Correctness remediation metadata marker block is missing or malformed. "
        "Expected START/END markers around a ```json ... ``` block."
    )
    metadata = json.loads(match.group(1))
    assert isinstance(metadata, dict), (
        f"Correctness remediation metadata must decode to an object, got {type(metadata).__name__}"
    )
    return metadata


def test_correctness_artifact_is_correctness_only_and_zero_findings() -> None:
    """Verify the #784 correctness re-audit artifact is structurally valid and clean."""
    assert CORRECTNESS_PATH.is_file(), (
        f"Missing correctness remediation audit artifact: {CORRECTNESS_PATH}"
    )
    artifact = _load_json(CORRECTNESS_PATH)
    detectors = _typed_detectors(artifact, source=str(CORRECTNESS_PATH))

    assert artifact["format_version"] == 1
    assert artifact["root"] == "."
    assert detectors, "Correctness audit artifact must declare at least one detector"
    assert artifact["detector_count"] > 0
    assert artifact["detector_count"] == len(detectors)
    assert {
        detector.get("detector_id") for detector in detectors
    } == EXPECTED_CORRECTNESS_DETECTOR_IDS
    assert all(detector.get("rule_class") == "correctness" for detector in detectors)
    assert artifact["finding_count"] == 0
    assert _typed_findings(artifact, source=str(CORRECTNESS_PATH)) == []


def test_correctness_remediation_metadata_reconciles_with_artifacts() -> None:
    """Verify report metadata matches artifacts and enforces non-increasing correctness findings."""
    assert REPORT_PATH.is_file(), f"Missing correctness remediation report: {REPORT_PATH}"
    assert BASELINE_PATH.is_file(), f"Missing baseline audit artifact: {BASELINE_PATH}"
    baseline = _load_json(BASELINE_PATH)
    correctness = _load_json(CORRECTNESS_PATH)
    metadata = _extract_metadata(REPORT_PATH.read_text(encoding="utf-8"))

    baseline_correctness_count = _correctness_finding_count(baseline, source=str(BASELINE_PATH))
    post_correctness_count = _correctness_finding_count(correctness, source=str(CORRECTNESS_PATH))
    expected_new_suppressions = max(
        0,
        _suppression_count(correctness, source=str(CORRECTNESS_PATH))
        - _suppression_count(baseline, source=str(BASELINE_PATH)),
    )

    # These metadata path fields pin the report to the exact audited artifacts.
    assert metadata["baseline_artifact"] == BASELINE_ARTIFACT_REL
    assert metadata["correctness_remediation_artifact"] == CORRECTNESS_REMEDIATION_ARTIFACT_REL

    # These metadata values must be mechanically derived from artifacts, not hand-edited.
    assert metadata["baseline_correctness_finding_count"] == baseline_correctness_count
    assert metadata["post_remediation_correctness_finding_count"] == post_correctness_count
    assert post_correctness_count <= baseline_correctness_count
    assert metadata["monotonic_non_increase_verified"] is True
    assert metadata["new_suppressions_introduced"] == expected_new_suppressions
