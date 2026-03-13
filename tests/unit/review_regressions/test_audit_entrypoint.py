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


def test_load_detectors_wraps_missing_module_with_value_error(monkeypatch) -> None:
    def _raise_missing_module(name: str) -> None:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(audit.importlib, "import_module", _raise_missing_module)

    with pytest.raises(ValueError, match="Invalid detector spec 'missing:detector'"):
        audit.load_detectors(["missing:detector"])


def test_load_detectors_wraps_missing_attribute_with_value_error(monkeypatch) -> None:
    class _Module:
        present = object()

    monkeypatch.setattr(audit.importlib, "import_module", lambda name: _Module)

    with pytest.raises(ValueError, match="Invalid detector spec 'pkg:missing'"):
        audit.load_detectors(["pkg:missing"])
