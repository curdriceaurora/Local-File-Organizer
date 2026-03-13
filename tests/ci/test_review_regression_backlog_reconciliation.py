from __future__ import annotations

import json
import re
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


def _extract_fingerprint_rows(
    text: str,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in text.splitlines():
        if not re.match(r"^\|\s*`[0-9a-f]{16}`\s*\|", line):
            continue
        cells = [cell.strip() for cell in line.strip().split("|")[1:-1]]
        assert len(cells) == 7, f"Unexpected backlog row shape: {line}"
        fingerprint = cells[0].strip("`")
        gap_category = cells[6].strip("`")
        rows.append((fingerprint, gap_category))
    return rows


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

    rule_class_totals = metadata["rule_class_totals"]
    assert isinstance(rule_class_totals, dict)
    assert sum(rule_class_totals.values()) == artifact["finding_count"]


def test_backlog_rows_cover_every_fingerprint_exactly_once_with_mece_gap_categories() -> None:
    backlog_text = BACKLOG_PATH.read_text(encoding="utf-8")
    artifact = _load_artifact()

    row_entries = _extract_fingerprint_rows(backlog_text)
    backlog_fingerprints = [fingerprint for fingerprint, _ in row_entries]
    artifact_fingerprints = [finding["fingerprint"] for finding in artifact["findings"]]

    assert len(backlog_fingerprints) == len(set(backlog_fingerprints)), (
        "Backlog contains duplicate fingerprint rows"
    )
    assert sorted(backlog_fingerprints) == sorted(artifact_fingerprints), (
        "Backlog fingerprint rows do not reconcile to audit artifact findings"
    )

    gap_counts = {"legacy-only gap": 0, "forward-gap and legacy-gap": 0}
    for _, gap_category in row_entries:
        assert gap_category in _ALLOWED_GAP_CATEGORIES
        gap_counts[gap_category] += 1

    metadata = _extract_metadata(backlog_text)
    assert gap_counts == metadata["classification_totals"]
