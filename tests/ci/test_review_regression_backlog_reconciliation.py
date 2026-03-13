from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import pytest

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_PATH = (
    FO_ROOT / "docs" / "plans" / "review-regressions" / "2026-03-13-first-wave-audit.json"
)
BACKLOG_PATH = (
    FO_ROOT
    / "docs"
    / "plans"
    / "review-regressions"
    / "2026-03-13-first-wave-remediation-backlog.md"
)
_ALLOWED_GAP_CATEGORIES = {"legacy-only gap", "forward-gap and legacy-gap"}
_ALLOWED_SEVERITIES = {"high", "medium", "low"}
_RULE_SEVERITY = {
    "unguarded-direct-path": "high",
    "validated-path-bypass": "high",
    "validated-field-setattr-bypass": "high",
    "primitive-active-model-store": "high",
    "weak-mock-call-count-lower-bound": "medium",
}


def _load_artifact() -> dict[str, object]:
    return json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))


def _extract_metadata(text: str) -> dict[str, object]:
    match = re.search(
        r"<!-- REVIEW_REGRESSION_BACKLOG_METADATA_START -->\s*```json\s*(.*?)\s*```\s*"
        r"<!-- REVIEW_REGRESSION_BACKLOG_METADATA_END -->",
        text,
        flags=re.DOTALL,
    )
    assert match is not None, "Backlog metadata marker block is missing"
    return json.loads(match.group(1))


def _extract_backlog_rows(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in text.splitlines():
        if not re.match(r"^\|\s*`[0-9a-f]{16}`\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().split("|")[1:-1]]
        assert len(cells) == 7, f"Unexpected backlog row shape: {line}"
        rows.append(
            {
                "fingerprint": cells[0].strip("`"),
                "rule_class": cells[1].strip("`"),
                "rule_id": cells[2].strip("`"),
                "location": cells[3].strip("`"),
                "subsystem_module": cells[4].strip("`"),
                "severity": cells[5].strip("`"),
                "gap_category": cells[6].strip("`"),
            }
        )
    return rows


def _expected_severity_for_finding(finding: dict[str, object]) -> str:
    rule_id = str(finding["rule_id"])
    assert rule_id in _RULE_SEVERITY, f"No severity mapping defined for rule_id={rule_id!r}"
    return _RULE_SEVERITY[rule_id]


def test_review_regression_artifact_schema_and_counts() -> None:
    assert ARTIFACT_PATH.is_file(), f"Missing audit artifact: {ARTIFACT_PATH}"
    artifact = _load_artifact()

    assert artifact["format_version"] == 1
    assert isinstance(artifact["detectors"], list)
    assert isinstance(artifact["findings"], list)
    assert artifact["detector_count"] == len(artifact["detectors"])
    assert artifact["finding_count"] == len(artifact["findings"])


def test_backlog_metadata_reconciles_with_artifact() -> None:
    assert BACKLOG_PATH.is_file(), f"Missing backlog document: {BACKLOG_PATH}"
    backlog_text = BACKLOG_PATH.read_text(encoding="utf-8")
    metadata = _extract_metadata(backlog_text)
    artifact = _load_artifact()

    assert metadata["audit_artifact"] == (
        "docs/plans/review-regressions/2026-03-13-first-wave-audit.json"
    )
    assert metadata["audit_finding_total"] == artifact["finding_count"]
    assert metadata["classified_finding_total"] == artifact["finding_count"]

    classification_totals = metadata["classification_totals"]
    assert isinstance(classification_totals, dict)
    assert set(classification_totals) == _ALLOWED_GAP_CATEGORIES
    assert sum(classification_totals.values()) == artifact["finding_count"]

    artifact_rule_classes = sorted({finding["rule_class"] for finding in artifact["findings"]})
    all_rule_classes = sorted(
        {
            detector["rule_class"]  # type: ignore[index]
            for detector in artifact["detectors"]  # type: ignore[index]
        }
    )

    rule_class_totals = metadata["rule_class_totals"]
    assert isinstance(rule_class_totals, dict)
    assert sorted(rule_class_totals) == all_rule_classes
    assert sum(rule_class_totals.values()) == artifact["finding_count"]

    artifact_rule_class_counts = Counter(
        finding["rule_class"]
        for finding in artifact["findings"]  # type: ignore[index]
    )
    expected_rule_class_totals = {
        rule_class: artifact_rule_class_counts.get(rule_class, 0) for rule_class in all_rule_classes
    }
    assert rule_class_totals == expected_rule_class_totals
    assert (
        sorted(rule_class for rule_class, count in rule_class_totals.items() if count > 0)
        == artifact_rule_classes
    )

    severity_totals = metadata["severity_totals"]
    assert isinstance(severity_totals, dict)
    assert set(severity_totals) == _ALLOWED_SEVERITIES
    assert sum(severity_totals.values()) == artifact["finding_count"]
    artifact_severity_counts = Counter(
        _expected_severity_for_finding(finding)
        for finding in artifact["findings"]  # type: ignore[index]
    )
    assert severity_totals == {
        severity: artifact_severity_counts.get(severity, 0)
        for severity in sorted(_ALLOWED_SEVERITIES)
    }


def test_backlog_rows_cover_every_fingerprint_exactly_once_with_mece_gap_categories() -> None:
    backlog_text = BACKLOG_PATH.read_text(encoding="utf-8")
    artifact = _load_artifact()

    row_entries = _extract_backlog_rows(backlog_text)
    backlog_fingerprints = [entry["fingerprint"] for entry in row_entries]
    artifact_fingerprints = [finding["fingerprint"] for finding in artifact["findings"]]

    assert len(backlog_fingerprints) == len(set(backlog_fingerprints)), (
        "Backlog contains duplicate fingerprint rows"
    )
    assert sorted(backlog_fingerprints) == sorted(artifact_fingerprints), (
        "Backlog fingerprint rows do not reconcile to audit artifact findings"
    )

    artifact_by_fingerprint = {finding["fingerprint"]: finding for finding in artifact["findings"]}
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    rule_class_counts: Counter[str] = Counter()
    gap_counts = {"legacy-only gap": 0, "forward-gap and legacy-gap": 0}
    for row in row_entries:
        finding = artifact_by_fingerprint[row["fingerprint"]]
        assert row["rule_class"] == finding["rule_class"]
        assert row["rule_id"] == finding["rule_id"]
        expected_location = (
            f"{finding['path']}:{finding['line']}" if "line" in finding else str(finding["path"])
        )
        assert row["location"] == expected_location
        assert row["subsystem_module"]

        assert row["severity"] in _ALLOWED_SEVERITIES
        assert row["severity"] == _expected_severity_for_finding(finding)
        severity_counts[row["severity"]] += 1

        rule_class_counts[row["rule_class"]] += 1
        gap_category = row["gap_category"]
        assert gap_category in _ALLOWED_GAP_CATEGORIES
        gap_counts[gap_category] += 1

    metadata = _extract_metadata(backlog_text)
    assert dict(rule_class_counts) == {
        rule_class: count
        for rule_class, count in metadata["rule_class_totals"].items()
        if count > 0
    }
    assert severity_counts == metadata["severity_totals"]
    assert gap_counts == metadata["classification_totals"]
