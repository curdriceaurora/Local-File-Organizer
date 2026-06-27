"""Tests for the WP-6.3 pip-audit accepted-risk gate."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_SCRIPT = Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "pip_audit_gate.py"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pip_audit_gate_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load_module()


def _write_audit_json(path: Path, dependencies: list[dict]) -> None:
    path.write_text(json.dumps({"dependencies": dependencies}), encoding="utf-8")


def _write_accepted_risks(path: Path, risks: list[dict]) -> None:
    import yaml

    path.write_text(yaml.dump({"risks": risks}), encoding="utf-8")


def test_no_findings_passes(tmp_path: Path) -> None:
    audit_json = tmp_path / "audit.json"
    _write_audit_json(audit_json, [])
    risks_yml = tmp_path / "accepted-risks.yml"
    _write_accepted_risks(risks_yml, [])

    assert gate.run_gate(audit_json, risks_yml) == []


def test_unaccepted_finding_is_reported(tmp_path: Path) -> None:
    audit_json = tmp_path / "audit.json"
    _write_audit_json(
        audit_json,
        [{"name": "pillow", "version": "10.4.0", "vulns": [{"id": "PYSEC-2026-165"}]}],
    )
    risks_yml = tmp_path / "accepted-risks.yml"
    _write_accepted_risks(risks_yml, [])

    findings = gate.run_gate(audit_json, risks_yml)
    assert len(findings) == 1
    assert "pillow" in findings[0]
    assert "PYSEC-2026-165" in findings[0]


def test_accepted_finding_is_suppressed(tmp_path: Path) -> None:
    audit_json = tmp_path / "audit.json"
    _write_audit_json(
        audit_json,
        [{"name": "pillow", "version": "10.4.0", "vulns": [{"id": "PYSEC-2026-165"}]}],
    )
    risks_yml = tmp_path / "accepted-risks.yml"
    _write_accepted_risks(
        risks_yml,
        [
            {
                "package": "pillow",
                "vulnerability_id": "PYSEC-2026-165",
                "reason": "test",
                "tracking_issue": "test",
            }
        ],
    )

    assert gate.run_gate(audit_json, risks_yml) == []


def test_partial_acceptance_still_reports_remaining_finding(tmp_path: Path) -> None:
    audit_json = tmp_path / "audit.json"
    _write_audit_json(
        audit_json,
        [
            {
                "name": "pillow",
                "version": "10.4.0",
                "vulns": [{"id": "PYSEC-2026-165"}, {"id": "CVE-2026-25990"}],
            }
        ],
    )
    risks_yml = tmp_path / "accepted-risks.yml"
    _write_accepted_risks(
        risks_yml,
        [
            {
                "package": "pillow",
                "vulnerability_id": "PYSEC-2026-165",
                "reason": "test",
                "tracking_issue": "test",
            }
        ],
    )

    findings = gate.run_gate(audit_json, risks_yml)
    assert len(findings) == 1
    assert "CVE-2026-25990" in findings[0]


def test_missing_accepted_risks_file_treats_as_empty(tmp_path: Path) -> None:
    audit_json = tmp_path / "audit.json"
    _write_audit_json(audit_json, [])
    missing_risks = tmp_path / "does-not-exist.yml"

    assert gate.run_gate(audit_json, missing_risks) == []
