from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
BASELINE_ARTIFACT_REL = "docs/plans/review-regressions/2026-03-13-first-wave-audit.json"
FINAL_ARTIFACT_REL = "docs/plans/review-regressions/2026-03-13-first-wave-final-audit.json"
CLOSEOUT_REPORT_REL = "docs/plans/review-regressions/2026-03-13-first-wave-epic-closeout.md"
BASELINE_PATH = FO_ROOT / BASELINE_ARTIFACT_REL
FINAL_PATH = FO_ROOT / FINAL_ARTIFACT_REL
CLOSEOUT_REPORT_PATH = FO_ROOT / CLOSEOUT_REPORT_REL
EXPECTED_RULE_CLASSES = {"security", "correctness", "test-quality"}


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _typed_findings(report: Mapping[str, object], *, source: str) -> list[dict[str, object]]:
    """Return findings as typed dict entries and fail with source-aware diagnostics."""
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


def _rule_class_counts(report: Mapping[str, object], *, source: str) -> dict[str, int]:
    """Compute normalized finding counts by first-wave rule class."""
    detectors = _typed_detectors(report, source=source)
    findings = _typed_findings(report, source=source)
    classes = {detector.get("rule_class") for detector in detectors}
    assert classes == EXPECTED_RULE_CLASSES
    counts = Counter(str(finding.get("rule_class") or finding.get("class")) for finding in findings)
    return {rule_class: counts.get(rule_class, 0) for rule_class in sorted(EXPECTED_RULE_CLASSES)}


def _extract_metadata(text: str) -> dict[str, object]:
    match = re.search(
        r"<!-- REVIEW_REGRESSION_FIRST_WAVE_CLOSEOUT_METADATA_START -->\s*```json\s*(.*?)\s*```"
        r"\s*<!-- REVIEW_REGRESSION_FIRST_WAVE_CLOSEOUT_METADATA_END -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, "First-wave closeout metadata marker block is missing or malformed"
    metadata = json.loads(match.group(1))
    assert isinstance(metadata, dict), "First-wave closeout metadata must decode to a JSON object"
    return metadata


def test_final_first_wave_artifact_is_zero_findings_with_full_detector_set() -> None:
    assert FINAL_PATH.is_file(), f"Missing final first-wave audit artifact: {FINAL_PATH}"
    artifact = _load_json(FINAL_PATH)

    assert artifact["format_version"] == 1
    assert artifact["root"] == "."
    assert artifact["finding_count"] == 0
    assert _typed_findings(artifact, source=str(FINAL_PATH)) == []
    assert _rule_class_counts(artifact, source=str(FINAL_PATH)) == {
        "correctness": 0,
        "security": 0,
        "test-quality": 0,
    }


def test_first_wave_closeout_metadata_reconciles_initial_fixed_and_final_counts() -> None:
    assert BASELINE_PATH.is_file(), f"Missing baseline first-wave audit artifact: {BASELINE_PATH}"
    assert FINAL_PATH.is_file(), f"Missing final first-wave audit artifact: {FINAL_PATH}"
    assert CLOSEOUT_REPORT_PATH.is_file(), (
        f"Missing first-wave closeout report: {CLOSEOUT_REPORT_PATH}"
    )

    baseline = _load_json(BASELINE_PATH)
    final = _load_json(FINAL_PATH)
    metadata = _extract_metadata(CLOSEOUT_REPORT_PATH.read_text(encoding="utf-8"))

    initial_counts = _rule_class_counts(baseline, source=str(BASELINE_PATH))
    final_counts = _rule_class_counts(final, source=str(FINAL_PATH))
    fixed_counts = {
        rule_class: initial_counts[rule_class] - final_counts[rule_class]
        for rule_class in sorted(EXPECTED_RULE_CLASSES)
    }

    assert metadata["baseline_artifact"] == BASELINE_ARTIFACT_REL
    assert metadata["final_artifact"] == FINAL_ARTIFACT_REL
    assert metadata["initial_rule_class_counts"] == initial_counts
    assert metadata["final_rule_class_counts"] == final_counts
    assert metadata["fixed_rule_class_counts"] == fixed_counts
    assert metadata["initial_total_findings"] == baseline["finding_count"]
    assert metadata["final_total_findings"] == final["finding_count"]
    assert metadata["fixed_total_findings"] == baseline["finding_count"] - final["finding_count"]
    assert metadata["steady_state_zero_verified"] is True
