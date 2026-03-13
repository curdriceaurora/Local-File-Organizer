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
            "src/file_organizer/api/direct_path_allowed_roots_missing_codeql.py",
            15,
            "unguarded-direct-path",
        ),
        (
            "src/file_organizer/api/direct_path_positive.py",
            16,
            "unguarded-direct-path",
        ),
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

    assert [
        (finding.path, finding.line, finding.rule_id, finding.message) for finding in findings
    ] == [
        (
            "src/file_organizer/api/validation_bypass_positional_positive.py",
            26,
            "raw-field-after-validation",
            "Route validates request.destination with resolve_path() but later passes raw request.destination to move_files().",
        ),
        (
            "src/file_organizer/api/validation_bypass_positional_positive.py",
            26,
            "raw-field-after-validation",
            "Route validates request.source with resolve_path() but later passes raw request.source to move_files().",
        ),
        (
            "src/file_organizer/api/validation_bypass_positive.py",
            35,
            "raw-request-after-validation",
            "Route validates request path fields with resolve_path() but later passes the raw request object to add_task().",
        ),
        (
            "src/file_organizer/api/validation_bypass_positive.py",
            36,
            "raw-field-after-validation",
            "Route validates request.input_dir with resolve_path() but later passes raw request.input_dir to organize().",
        ),
        (
            "src/file_organizer/api/validation_bypass_positive.py",
            36,
            "raw-field-after-validation",
            "Route validates request.output_dir with resolve_path() but later passes raw request.output_dir to organize().",
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
