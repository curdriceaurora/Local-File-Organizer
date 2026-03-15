from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.review_regressions.api_compat import (
    API_COMPAT_DETECTORS,
    PublicApiCompatibilityDetector,
    PublicCallableContract,
)
from file_organizer.review_regressions.framework import run_audit

pytestmark = pytest.mark.ci

FO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = FO_ROOT / "tests" / "fixtures" / "review_regressions" / "api_compat"


def _fixture_detector() -> PublicApiCompatibilityDetector:
    return PublicApiCompatibilityDetector(
        contracts=(
            PublicCallableContract(
                path=Path("src/file_organizer/public/constructor_prefix_positive.py"),
                qualname="PipelineOrchestrator.__init__",
                legacy_positional_params=("config", "stages", "prefetch_depth"),
            ),
            PublicCallableContract(
                path=Path("src/file_organizer/public/optional_positional_positive.py"),
                qualname="FileOrganizer.__init__",
                legacy_positional_params=("dry_run", "prefetch_depth"),
            ),
            PublicCallableContract(
                path=Path("src/file_organizer/public/keyword_only_safe.py"),
                qualname="FileOrganizer.__init__",
                legacy_positional_params=("dry_run", "prefetch_depth"),
            ),
            PublicCallableContract(
                path=Path("src/file_organizer/public/process_batch_safe.py"),
                qualname="PipelineOrchestrator.process_batch",
                legacy_positional_params=("files",),
            ),
        )
    )


def test_api_compat_repo_enforcement_reports_zero_findings() -> None:
    report = run_audit(FO_ROOT, API_COMPAT_DETECTORS)
    detector_ids = {detector.detector_id for detector in report.detectors}

    assert detector_ids == {"api-compat.public-callable-signature-contracts"}
    assert not report.findings, (
        "API compatibility guardrail found violations in repository source:\n"
        + "\n".join(
            f"{finding.path}:{finding.line or '-'} {finding.rule_id} {finding.message}"
            for finding in report.findings
        )
    )


def test_seeded_api_compat_fixtures_trigger_expected_rules() -> None:
    report = run_audit(FIXTURE_ROOT, (_fixture_detector(),))
    assert len(report.findings) == 2
    found_rule_ids = {finding.rule_id for finding in report.findings}
    found_paths = {finding.path for finding in report.findings}

    assert found_rule_ids == {
        "legacy-positional-prefix-changed",
        "new-optional-param-must-be-keyword-only",
    }
    assert found_paths == {
        "src/file_organizer/public/constructor_prefix_positive.py",
        "src/file_organizer/public/optional_positional_positive.py",
    }
    assert all(finding.rule_class == "api-compat" for finding in report.findings)
