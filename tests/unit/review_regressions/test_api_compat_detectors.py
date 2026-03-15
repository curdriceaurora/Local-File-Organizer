from __future__ import annotations

from pathlib import Path

from file_organizer.review_regressions.api_compat import (
    API_COMPAT_DETECTORS,
    PublicApiCompatibilityDetector,
    PublicCallableContract,
)


def _fixture_root() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "fixtures" / "review_regressions" / "api_compat"
    ).resolve()


def test_api_compat_detector_flags_legacy_positional_prefix_changes() -> None:
    detector = PublicApiCompatibilityDetector(
        contracts=(
            PublicCallableContract(
                path=Path("src/file_organizer/public/constructor_prefix_positive.py"),
                qualname="PipelineOrchestrator.__init__",
                legacy_positional_params=("config", "stages", "prefetch_depth"),
            ),
        )
    )

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.line, finding.rule_id) for finding in findings] == [
        (
            "src/file_organizer/public/constructor_prefix_positive.py",
            2,
            "legacy-positional-prefix-changed",
        ),
    ]


def test_api_compat_detector_flags_new_optional_positional_params() -> None:
    detector = PublicApiCompatibilityDetector(
        contracts=(
            PublicCallableContract(
                path=Path("src/file_organizer/public/optional_positional_positive.py"),
                qualname="FileOrganizer.__init__",
                legacy_positional_params=("dry_run", "prefetch_depth"),
            ),
        )
    )

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.line, finding.rule_id) for finding in findings] == [
        (
            "src/file_organizer/public/optional_positional_positive.py",
            6,
            "new-optional-param-must-be-keyword-only",
        ),
    ]


def test_api_compat_detector_allows_keyword_only_optional_extension() -> None:
    detector = PublicApiCompatibilityDetector(
        contracts=(
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

    findings = detector.find_violations(_fixture_root())

    assert findings == []


def test_api_compat_detector_pack_exports_detector() -> None:
    assert [detector.detector_id for detector in API_COMPAT_DETECTORS] == [
        "api-compat.public-callable-signature-contracts",
    ]


def test_api_compat_detector_flags_missing_allowlisted_targets() -> None:
    detector = PublicApiCompatibilityDetector(
        contracts=(
            PublicCallableContract(
                path=Path("src/file_organizer/public/does_not_exist.py"),
                qualname="PipelineOrchestrator.__init__",
                legacy_positional_params=("config",),
            ),
            PublicCallableContract(
                path=Path("src/file_organizer/public/process_batch_safe.py"),
                qualname="PipelineOrchestrator.missing_method",
                legacy_positional_params=("files",),
            ),
        )
    )

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.rule_id) for finding in findings] == [
        (
            "src/file_organizer/public/does_not_exist.py",
            "allowlisted-callable-missing",
        ),
        (
            "src/file_organizer/public/process_batch_safe.py",
            "allowlisted-callable-missing",
        ),
    ]
