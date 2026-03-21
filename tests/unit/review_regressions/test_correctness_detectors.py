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


def _write_module(root: Path, rel_path: str, source: str) -> Path:
    target = root / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return target


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
    root = _fixture_root()
    safe_path = "src/file_organizer/pipeline/stage_context_bypass_safe.py"

    assert (root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [finding for finding in detector.find_violations(root) if finding.path == safe_path]

    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


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
    root = _fixture_root()
    safe_path = "src/file_organizer/models/model_manager_safe.py"

    assert (root / safe_path).exists(), f"Missing fixture: {safe_path}"

    findings = [finding for finding in detector.find_violations(root) if finding.path == safe_path]

    assert not findings, f"Unexpected findings for {safe_path}: {findings}"


def test_correctness_detector_pack_exports_first_wave_correctness_detectors() -> None:
    assert [detector.detector_id for detector in CORRECTNESS_DETECTORS] == [
        "correctness.stage-context-validation-bypass",
        "correctness.active-model-primitive-store",
    ]


def test_stage_context_detector_does_not_leak_names_across_function_scopes(
    tmp_path: Path,
) -> None:
    """StageContext names should only apply within their lexical scope."""
    detector = StageContextValidationBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/pipeline/scope_leak.py",
        (
            "from file_organizer.interfaces.pipeline import StageContext\n"
            "def producer() -> None:\n"
            "    ctx: StageContext\n"
            "def unrelated() -> None:\n"
            "    object.__setattr__(ctx, 'category', 'x')\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert findings == []


def test_stage_context_detector_requires_explicit_canonical_provenance(
    tmp_path: Path,
) -> None:
    """A local class named StageContext must not be treated as canonical provenance."""
    detector = StageContextValidationBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/pipeline/local_stage_context.py",
        (
            "class StageContext:\n"
            "    pass\n"
            "def f() -> None:\n"
            "    ctx = StageContext()\n"
            "    object.__setattr__(ctx, 'category', 'x')\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert findings == []


def test_stage_context_detector_ignores_function_local_import_alias(
    tmp_path: Path,
) -> None:
    """A function-local import alias must not pollute module-wide alias detection.

    If function A imports ``StageContext as SC`` locally and function B uses an
    unrelated variable also named ``SC``, the detector must NOT flag B's
    ``object.__setattr__(sc, 'category', …)`` call — the ``SC`` name in B has no
    canonical provenance from the pipeline module (T10 negative case).
    """
    detector = StageContextValidationBypassDetector()
    _write_module(
        tmp_path,
        "src/file_organizer/pipeline/local_alias_no_spill.py",
        (
            "def importer() -> None:\n"
            "    from file_organizer.interfaces.pipeline import StageContext as SC\n"
            "    sc: SC\n"
            "def unrelated(sc: object) -> None:\n"
            "    object.__setattr__(sc, 'category', 'x')\n"
        ),
    )

    findings = detector.find_violations(tmp_path)

    assert findings == [], f"Function-local alias leaked into unrelated scope: {findings}"
