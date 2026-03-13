from __future__ import annotations

from pathlib import Path

from file_organizer.review_regressions.security import (
    SECURITY_DETECTORS,
    GuardedContextDirectPathDetector,
    ValidatedPathBypassDetector,
)


def _fixture_root() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "fixtures" / "review_regressions" / "security"
    ).resolve()


def test_direct_path_detector_flags_unreviewed_path_construction() -> None:
    detector = GuardedContextDirectPathDetector()

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.line, finding.rule_id) for finding in findings] == [
        (
            "src/file_organizer/api/direct_path_positive.py",
            16,
            "unguarded-direct-path",
        )
    ]


def test_direct_path_detector_skips_documented_safe_patterns() -> None:
    detector = GuardedContextDirectPathDetector()

    findings = [
        finding
        for finding in detector.find_violations(_fixture_root())
        if finding.path == "src/file_organizer/api/direct_path_safe.py"
    ]

    assert findings == []


def test_validation_bypass_detector_flags_raw_request_reuse_after_validation() -> None:
    detector = ValidatedPathBypassDetector()

    findings = detector.find_violations(_fixture_root())

    assert [(finding.path, finding.line, finding.rule_id) for finding in findings] == [
        (
            "src/file_organizer/api/validation_bypass_positive.py",
            35,
            "raw-request-after-validation",
        ),
        (
            "src/file_organizer/api/validation_bypass_positive.py",
            36,
            "raw-field-after-validation",
        ),
        (
            "src/file_organizer/api/validation_bypass_positive.py",
            36,
            "raw-field-after-validation",
        ),
    ]


def test_validation_bypass_detector_skips_sanitized_request_flow() -> None:
    detector = ValidatedPathBypassDetector()

    findings = [
        finding
        for finding in detector.find_violations(_fixture_root())
        if finding.path == "src/file_organizer/api/validation_bypass_safe.py"
    ]

    assert findings == []


def test_security_detector_pack_exports_both_first_wave_security_detectors() -> None:
    assert [detector.detector_id for detector in SECURITY_DETECTORS] == [
        "security.guarded-context-direct-path",
        "security.validated-path-bypass",
    ]
