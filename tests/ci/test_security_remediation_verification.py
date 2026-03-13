from __future__ import annotations

import json
import re
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


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _security_finding_count(report: dict[str, object]) -> int:
    findings = report["findings"]  # type: ignore[index]
    return sum(1 for finding in findings if finding["rule_class"] == "security")  # type: ignore[index]


def _suppression_count(report: dict[str, object]) -> int:
    findings = report.get("findings", [])
    return sum(1 for finding in findings if finding.get("suppressed") is True)  # type: ignore[union-attr]


def _extract_metadata(text: str) -> dict[str, object]:
    match = re.search(
        r"<!-- REVIEW_REGRESSION_SECURITY_REMEDIATION_METADATA_START -->\s*```json\s*(.*?)\s*```"
        r"\s*<!-- REVIEW_REGRESSION_SECURITY_REMEDIATION_METADATA_END -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, "Security remediation metadata marker block is missing"
    return json.loads(match.group(1))


def test_security_artifact_is_security_only_and_zero_findings() -> None:
    assert SECURITY_PATH.is_file(), f"Missing security remediation audit artifact: {SECURITY_PATH}"
    artifact = _load_json(SECURITY_PATH)

    assert artifact["format_version"] == 1
    assert artifact["finding_count"] == 0
    assert artifact["findings"] == []
    assert _security_finding_count(artifact) == 0
    assert all(detector["rule_class"] == "security" for detector in artifact["detectors"])  # type: ignore[index]


def test_security_remediation_metadata_reconciles_with_artifacts() -> None:
    assert REPORT_PATH.is_file(), f"Missing security remediation report: {REPORT_PATH}"
    baseline = _load_json(BASELINE_PATH)
    security = _load_json(SECURITY_PATH)
    metadata = _extract_metadata(REPORT_PATH.read_text(encoding="utf-8"))

    baseline_security_count = _security_finding_count(baseline)
    post_security_count = _security_finding_count(security)
    expected_new_suppressions = max(0, _suppression_count(security) - _suppression_count(baseline))

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
