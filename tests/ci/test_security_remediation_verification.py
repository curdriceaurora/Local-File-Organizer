from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_PATH = (
    FO_ROOT / "docs" / "plans" / "review-regressions" / "2026-03-13-first-wave-audit.json"
)
SECURITY_PATH = (
    FO_ROOT / "docs" / "plans" / "review-regressions" / "2026-03-13-security-remediation-audit.json"
)
REPORT_PATH = (
    FO_ROOT / "docs" / "plans" / "review-regressions" / "2026-03-13-security-remediation-report.md"
)
EXPECTED_SECURITY_DETECTOR_IDS = {
    "security.guarded-context-direct-path",
    "security.validated-path-bypass",
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


def _security_finding_count(report: Mapping[str, object], *, source: str) -> int:
    findings = _typed_findings(report, source=source)
    return sum(1 for finding in findings if finding.get("rule_class") == "security")


def _suppression_count(report: Mapping[str, object], *, source: str) -> int:
    findings = _typed_findings(report, source=source)
    return sum(
        1
        for finding in findings
        if finding.get("suppressed") is True
        and (finding.get("rule_class") == "security" or finding.get("class") == "security")
    )


def _extract_metadata(text: str) -> dict[str, object]:
    match = re.search(
        r"<!-- REVIEW_REGRESSION_SECURITY_REMEDIATION_METADATA_START -->\s*```json\s*(.*?)\s*```"
        r"\s*<!-- REVIEW_REGRESSION_SECURITY_REMEDIATION_METADATA_END -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, (
        "Security remediation metadata marker block is missing or malformed. "
        "Expected START/END markers around a ```json ... ``` block."
    )
    metadata = json.loads(match.group(1))
    assert isinstance(metadata, dict), (
        f"Security remediation metadata must decode to an object, got {type(metadata).__name__}"
    )
    return metadata


def test_security_artifact_is_security_only_and_zero_findings() -> None:
    """Verify the #783 security re-audit artifact is structurally valid and clean."""
    assert SECURITY_PATH.is_file(), f"Missing security remediation audit artifact: {SECURITY_PATH}"
    artifact = _load_json(SECURITY_PATH)
    detectors = _typed_detectors(artifact, source=str(SECURITY_PATH))

    assert artifact["format_version"] == 1
    assert artifact["root"] == "."
    assert detectors, "Security audit artifact must declare at least one detector"
    assert artifact["detector_count"] > 0
    assert artifact["detector_count"] == len(detectors)
    assert {detector.get("detector_id") for detector in detectors} == EXPECTED_SECURITY_DETECTOR_IDS
    assert all(detector.get("rule_class") == "security" for detector in detectors)
    assert artifact["finding_count"] == 0
    assert _typed_findings(artifact, source=str(SECURITY_PATH)) == []


def test_security_remediation_metadata_reconciles_with_artifacts() -> None:
    """Verify report metadata matches artifacts and enforces non-increasing security findings."""
    assert REPORT_PATH.is_file(), f"Missing security remediation report: {REPORT_PATH}"
    baseline = _load_json(BASELINE_PATH)
    security = _load_json(SECURITY_PATH)
    metadata = _extract_metadata(REPORT_PATH.read_text(encoding="utf-8"))

    baseline_security_count = _security_finding_count(baseline, source=str(BASELINE_PATH))
    post_security_count = _security_finding_count(security, source=str(SECURITY_PATH))
    expected_new_suppressions = max(
        0,
        _suppression_count(security, source=str(SECURITY_PATH))
        - _suppression_count(baseline, source=str(BASELINE_PATH)),
    )

    assert metadata["baseline_artifact"] == (
        "docs/plans/review-regressions/2026-03-13-first-wave-audit.json"
    )
    assert metadata["security_remediation_artifact"] == (
        "docs/plans/review-regressions/2026-03-13-security-remediation-audit.json"
    )
    assert metadata["baseline_security_finding_count"] == baseline_security_count
    assert metadata["post_remediation_security_finding_count"] == post_security_count
    assert post_security_count <= baseline_security_count
    assert metadata["monotonic_non_increase_verified"] is True
    assert metadata["new_suppressions_introduced"] == expected_new_suppressions
