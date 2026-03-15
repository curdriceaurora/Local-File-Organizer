from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from file_organizer.review_regressions import audit
from file_organizer.review_regressions.framework import Violation


@dataclass
class _Detector:
    detector_id: str = "fixture.detector"
    rule_class: str = "correctness"
    description: str = "fixture detector"
    findings: tuple[Violation, ...] = ()

    def find_violations(self, root: Path) -> tuple[Violation, ...]:
        return self.findings


def test_audit_entrypoint_exits_zero_when_no_findings(monkeypatch, capsys, tmp_path: Path) -> None:
    monkeypatch.setattr(audit, "load_detectors", lambda specs: [_Detector()])

    exit_code = audit.main(["--root", str(tmp_path), "--detector", "fixture:noop"])

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["finding_count"] == 0


def test_audit_entrypoint_exits_nonzero_when_configured_to_fail_on_findings(
    monkeypatch, capsys, tmp_path: Path
) -> None:
    finding = Violation.from_path(
        detector_id="fixture.detector",
        rule_class="correctness",
        rule_id="fixture.rule",
        root=tmp_path,
        path=tmp_path / "demo.py",
        message="demo finding",
        line=7,
    )
    monkeypatch.setattr(
        audit,
        "load_detectors",
        lambda specs: [_Detector(findings=(finding,))],
    )

    exit_code = audit.main(
        ["--root", str(tmp_path), "--detector", "fixture:hit", "--fail-on-findings"]
    )

    assert exit_code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["finding_count"] == 1


def test_load_detectors_accepts_factory_and_iterable(monkeypatch) -> None:
    class _Module:
        @staticmethod
        def one() -> _Detector:
            return _Detector(detector_id="one")

        @staticmethod
        def many() -> list[_Detector]:
            return [_Detector(detector_id="two"), _Detector(detector_id="three")]

    monkeypatch.setattr(audit.importlib, "import_module", lambda name: _Module)

    detectors = audit.load_detectors(["pkg:one", "pkg:many"])

    assert [detector.detector_id for detector in detectors] == ["one", "two", "three"]


def test_load_detectors_does_not_call_detector_instances(monkeypatch) -> None:
    class _CallableDetector(_Detector):
        def __call__(self) -> _Detector:
            raise AssertionError("detector instances should not be invoked")

    detector = _CallableDetector(detector_id="callable-instance")

    class _Module:
        direct = detector

    monkeypatch.setattr(audit.importlib, "import_module", lambda name: _Module)

    detectors = audit.load_detectors(["pkg:direct"])

    assert detectors == [detector]


def test_load_detectors_treats_detector_classes_as_factories(monkeypatch) -> None:
    class _ClassDetector:
        detector_id = "class.detector"
        rule_class = "correctness"
        description = "class-backed detector"

        def find_violations(self, root: Path) -> tuple[Violation, ...]:
            return ()

    class _Module:
        detector = _ClassDetector

    monkeypatch.setattr(audit.importlib, "import_module", lambda name: _Module)

    detectors = audit.load_detectors(["pkg:detector"])

    assert len(detectors) == 1
    assert isinstance(detectors[0], _ClassDetector)


def test_load_detectors_rejects_invalid_detector_surface(monkeypatch) -> None:
    class _InvalidDetector:
        detector_id = "broken"

        def find_violations(self, root: Path) -> tuple[Violation, ...]:
            return ()

    class _Module:
        @staticmethod
        def broken() -> _InvalidDetector:
            return _InvalidDetector()

    monkeypatch.setattr(audit.importlib, "import_module", lambda name: _Module)

    with pytest.raises(
        TypeError, match="detector_id, rule_class, description, and find_violations"
    ):
        audit.load_detectors(["pkg:broken"])


def test_load_detectors_rejects_specs_with_empty_module_or_attribute() -> None:
    for spec in (":detector", "pkg:"):
        with pytest.raises(ValueError, match=f"Invalid detector spec '{spec}'"):
            audit.load_detectors([spec])


def test_load_detectors_wraps_missing_module_with_value_error(monkeypatch) -> None:
    def _raise_missing_module(name: str) -> None:
        error = ModuleNotFoundError(f"No module named '{name}'")
        error.name = name
        raise error

    monkeypatch.setattr(audit.importlib, "import_module", _raise_missing_module)

    with pytest.raises(ValueError, match="Invalid detector spec 'missing:detector'"):
        audit.load_detectors(["missing:detector"])


def test_load_detectors_wraps_missing_parent_package_for_dotted_module(monkeypatch) -> None:
    def _raise_missing_parent(name: str) -> None:
        error = ModuleNotFoundError("No module named 'missing_pkg'")
        error.name = "missing_pkg"
        raise error

    monkeypatch.setattr(audit.importlib, "import_module", _raise_missing_parent)

    with pytest.raises(ValueError, match=r"Invalid detector spec 'missing_pkg.sub:detector'"):
        audit.load_detectors(["missing_pkg.sub:detector"])


def test_load_detectors_preserves_dependency_import_errors(monkeypatch) -> None:
    def _raise_dependency_error(name: str) -> None:
        error = ModuleNotFoundError("No module named 'dependency'")
        error.name = "dependency"
        raise error

    monkeypatch.setattr(audit.importlib, "import_module", _raise_dependency_error)

    with pytest.raises(ModuleNotFoundError, match="dependency"):
        audit.load_detectors(["pkg:detector"])


def test_load_detectors_wraps_missing_attribute_with_value_error(monkeypatch) -> None:
    class _Module:
        present = object()

    monkeypatch.setattr(audit.importlib, "import_module", lambda name: _Module)

    with pytest.raises(ValueError, match="Invalid detector spec 'pkg:missing'"):
        audit.load_detectors(["pkg:missing"])
