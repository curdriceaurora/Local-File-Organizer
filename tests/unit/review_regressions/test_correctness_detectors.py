from __future__ import annotations

from pathlib import Path

from file_organizer.review_regressions.correctness import (
    CORRECTNESS_DETECTORS,
    ActiveModelPrimitiveStoreDetector,
    StageContextValidationBypassDetector,
)


def _fixture_root() -> Path:
    return (
        Path(__file__).resolve().parents[2] / "fixtures" / "review_regressions" / "correctness"
    ).resolve()


def test_stage_context_detector_flags_validated_field_bypass() -> None:
    detector = StageContextValidationBypassDetector()

    findings = detector.find_violations(_fixture_root())

    assert [
        (finding.path, finding.line, finding.rule_id, finding.message) for finding in findings
    ] == [
        (
            "src/file_organizer/pipeline/stage_context_bypass_positive.py",
            5,
            "validated-field-setattr-bypass",
            "object.__setattr__ writes StageContext.category directly; validated fields must flow through StageContext.__setattr__.",
        ),
        (
            "src/file_organizer/pipeline/stage_context_bypass_positive.py",
            6,
            "validated-field-setattr-bypass",
            "object.__setattr__ writes StageContext.filename directly; validated fields must flow through StageContext.__setattr__.",
        ),
    ]


def test_stage_context_detector_skips_safe_assignment_paths() -> None:
    detector = StageContextValidationBypassDetector()

    findings = [
        finding
        for finding in detector.find_violations(_fixture_root())
        if finding.path == "src/file_organizer/pipeline/stage_context_bypass_safe.py"
    ]

    assert findings == []


def test_active_model_detector_flags_primitive_registry_store() -> None:
    detector = ActiveModelPrimitiveStoreDetector()

    findings = detector.find_violations(_fixture_root())

    assert [
        (finding.path, finding.line, finding.rule_id, finding.message) for finding in findings
    ] == [
        (
            "src/file_organizer/models/model_manager_positive.py",
            8,
            "primitive-active-model-store",
            "_active_models stores selected_model; registry entries must hold live model instances or be removed.",
        ),
        (
            "src/file_organizer/models/model_manager_positive.py",
            12,
            "primitive-active-model-store",
            "_active_models stores fallback_model; registry entries must hold live model instances or be removed.",
        ),
    ]


def test_active_model_detector_skips_live_model_store_and_pop() -> None:
    detector = ActiveModelPrimitiveStoreDetector()

    findings = [
        finding
        for finding in detector.find_violations(_fixture_root())
        if finding.path == "src/file_organizer/models/model_manager_safe.py"
    ]

    assert findings == []


def test_correctness_detector_pack_exports_first_wave_correctness_detectors() -> None:
    assert [detector.detector_id for detector in CORRECTNESS_DETECTORS] == [
        "correctness.stage-context-validation-bypass",
        "correctness.active-model-primitive-store",
    ]
