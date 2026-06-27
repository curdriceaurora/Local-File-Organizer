"""Tests for the WP-6.2 per-file unit coverage floor CI rail."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]

_SCRIPT = (
    Path(__file__).resolve().parents[2] / ".claude" / "scripts" / "check_module_coverage_floor.py"
)


def _load_checker() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_module_coverage_floor_under_test", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checker = _load_checker()


def _write_coverage_json(path: Path, files: dict[str, dict]) -> None:
    path.write_text(json.dumps({"files": files}), encoding="utf-8")


def test_below_floor_is_a_violation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    json_path = tmp_path / "cov.json"
    _write_coverage_json(
        json_path,
        {
            "src/file_organizer/x.py": {
                "summary": {
                    "num_statements": 100,
                    "num_branches": 0,
                    "covered_lines": 50,
                    "covered_branches": 0,
                }
            }
        },
    )
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[tool.coverage.floors.unit]\n"src/file_organizer/x.py" = 80\n', encoding="utf-8"
    )

    with pytest.raises(SystemExit) as exc_info:
        checker.main(["--json", str(json_path), "--pyproject", str(pyproject_path)])
    assert exc_info.value.code == 1
    assert "BELOW FLOOR" in capsys.readouterr().err


def test_meets_floor_passes(tmp_path: Path) -> None:
    json_path = tmp_path / "cov.json"
    _write_coverage_json(
        json_path,
        {
            "src/file_organizer/x.py": {
                "summary": {
                    "num_statements": 100,
                    "num_branches": 0,
                    "covered_lines": 90,
                    "covered_branches": 0,
                }
            }
        },
    )
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[tool.coverage.floors.unit]\n"src/file_organizer/x.py" = 80\n', encoding="utf-8"
    )
    checker.main(["--json", str(json_path), "--pyproject", str(pyproject_path)])


def test_missing_floor_for_covered_file_is_a_violation(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    json_path = tmp_path / "cov.json"
    _write_coverage_json(
        json_path,
        {
            "src/file_organizer/y.py": {
                "summary": {
                    "num_statements": 10,
                    "num_branches": 0,
                    "covered_lines": 10,
                    "covered_branches": 0,
                }
            }
        },
    )
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text("[tool.coverage.floors.unit]\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc_info:
        checker.main(["--json", str(json_path), "--pyproject", str(pyproject_path)])
    assert exc_info.value.code == 1
    assert "MISSING FLOOR" in capsys.readouterr().err


def test_stale_entry_is_a_violation(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    json_path = tmp_path / "cov.json"
    _write_coverage_json(json_path, {})
    pyproject_path = tmp_path / "pyproject.toml"
    pyproject_path.write_text(
        '[tool.coverage.floors.unit]\n"src/file_organizer/gone.py" = 50\n', encoding="utf-8"
    )

    with pytest.raises(SystemExit) as exc_info:
        checker.main(["--json", str(json_path), "--pyproject", str(pyproject_path)])
    assert exc_info.value.code == 1
    assert "STALE ENTRY" in capsys.readouterr().err
