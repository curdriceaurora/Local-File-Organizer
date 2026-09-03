"""Unit tests for scripts/coverage/split_coverage_by_context.py (issue #1767).

Builds a tiny fixture package + test tree + hand-crafted `.coverage` database
(two synthetic test "contexts" covering different lines) and drives the
script end-to-end via subprocess, the same way test_integration_floors.py
drives check-integration-floors.py.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import coverage
import pytest

SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "coverage" / "split_coverage_by_context.py"
)

_spec = importlib.util.spec_from_file_location("split_coverage_by_context", SCRIPT)
assert _spec is not None and _spec.loader is not None
split_coverage_by_context = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(split_coverage_by_context)


@pytest.mark.unit
class TestPureHelpers:
    def test_build_context_pattern_matches_phase_suffixes(self) -> None:
        pattern = split_coverage_by_context.build_context_pattern(
            ["tests/test_a.py::test_x", "tests/test_b.py::test_y[param]"]
        )
        import re

        regex = re.compile(pattern)
        assert regex.search("tests/test_a.py::test_x|run")
        assert regex.search("tests/test_a.py::test_x|setup")
        assert regex.search("tests/test_b.py::test_y[param]|run")
        # A different nodeid must not match, even one that starts the same.
        assert not regex.search("tests/test_a.py::test_x_other|run")

    def test_compute_combined_percent_averages_lines_and_branches(self) -> None:
        combined = split_coverage_by_context.compute_combined_percent(
            {
                "num_statements": 10,
                "num_branches": 10,
                "covered_lines": 8,
                "covered_branches": 2,
            }
        )
        assert combined == pytest.approx(50.0)

    def test_compute_combined_percent_none_when_nothing_measured(self) -> None:
        assert split_coverage_by_context.compute_combined_percent({}) is None


def _write_fixture_project(tmp_path: Path) -> Path:
    """A tiny package + test tree with one unit test and one integration test."""
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'markers = ["unit: unit", "integration: integration", "smoke: smoke"]\n'
        "\n"
        "[tool.coverage.run]\n"
        'source = ["src"]\n'
        "branch = true\n"
    )
    src_dir = tmp_path / "src" / "mypkg"
    src_dir.mkdir(parents=True)
    (src_dir / "__init__.py").write_text("")
    module_path = src_dir / "module.py"
    module_path.write_text("def a():\n    return 1\n\n\ndef b():\n    return 2\n")

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_sample.py").write_text(
        "import pytest\n"
        "\n"
        "\n"
        "@pytest.mark.unit\n"
        "def test_a():\n"
        "    assert True\n"
        "\n"
        "\n"
        "@pytest.mark.integration\n"
        "def test_b():\n"
        "    assert True\n"
    )
    return module_path


def _write_synthetic_coverage_db(tmp_path: Path, module_path: Path) -> None:
    """Two contexts covering different subsets of module.py's statement lines.

    module.py is "def a():\\n    return 1\\n\\n\\ndef b():\\n    return 2\\n" --
    lines 1, 2, 5, 6 are the four statements (def a / return 1 / def b / return 2).
    "test_a" covers only a() (lines 1-2, 50%); "test_b" covers a()'s def line
    plus all of b() (lines 1, 5, 6, 75%).
    """
    data = coverage.CoverageData(basename=str(tmp_path / ".coverage"))
    data.set_context("tests/test_sample.py::test_a|run")
    data.add_lines({str(module_path): [1, 2]})
    data.set_context("tests/test_sample.py::test_b|run")
    data.add_lines({str(module_path): [1, 5, 6]})
    data.write()


@pytest.mark.unit
class TestSplitScriptEndToEnd:
    def test_filters_to_only_the_matching_markers_view(self, tmp_path: Path) -> None:
        module_path = _write_fixture_project(tmp_path)
        _write_synthetic_coverage_db(tmp_path, module_path)

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--data-file",
                ".coverage",
                "--markers",
                "unit",
                "--out",
                "out-unit.json",
                "--tests-dir",
                "tests",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        import json

        report = json.loads((tmp_path / "out-unit.json").read_text())
        # coverage's json report keys files by path relative to the project
        # root (per [tool.coverage.run] source = ["src"]), not the absolute
        # path we wrote synthetic data against.
        summary = report["files"]["src/mypkg/module.py"]["summary"]
        # "unit" only ran test_a, which covered lines 1-2 of the 4 statements.
        assert summary["covered_lines"] == 2
        assert summary["num_statements"] == 4

    def test_integration_view_sees_different_coverage_than_unit_view(self, tmp_path: Path) -> None:
        module_path = _write_fixture_project(tmp_path)
        _write_synthetic_coverage_db(tmp_path, module_path)

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--data-file",
                ".coverage",
                "--markers",
                "integration",
                "--out",
                "out-integration.json",
                "--tests-dir",
                "tests",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

        import json

        report = json.loads((tmp_path / "out-integration.json").read_text())
        # coverage's json report keys files by path relative to the project
        # root (per [tool.coverage.run] source = ["src"]), not the absolute
        # path we wrote synthetic data against.
        summary = report["files"]["src/mypkg/module.py"]["summary"]
        # "integration" only ran test_b, which covered all 3 of its lines (1, 4, 5).
        assert summary["covered_lines"] == 3
        assert summary["num_statements"] == 4

    def test_min_combined_fails_below_threshold(self, tmp_path: Path) -> None:
        module_path = _write_fixture_project(tmp_path)
        _write_synthetic_coverage_db(tmp_path, module_path)

        # unit view is 2/4 = 50% combined (no branches in this fixture) — below 60.
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--data-file",
                ".coverage",
                "--markers",
                "unit",
                "--out",
                "out-unit.json",
                "--tests-dir",
                "tests",
                "--pyproject",
                "pyproject.toml",
                "--min-combined",
                "60",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "FAILED" in result.stderr

    def test_min_combined_passes_at_or_above_threshold(self, tmp_path: Path) -> None:
        module_path = _write_fixture_project(tmp_path)
        _write_synthetic_coverage_db(tmp_path, module_path)

        # integration view is 3/4 = 75% combined — above 60.
        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--data-file",
                ".coverage",
                "--markers",
                "integration",
                "--out",
                "out-integration.json",
                "--tests-dir",
                "tests",
                "--pyproject",
                "pyproject.toml",
                "--min-combined",
                "60",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr

    def test_fails_when_no_tests_match_markers(self, tmp_path: Path) -> None:
        module_path = _write_fixture_project(tmp_path)
        _write_synthetic_coverage_db(tmp_path, module_path)

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--data-file",
                ".coverage",
                "--markers",
                "smoke",
                "--out",
                "out-smoke.json",
                "--tests-dir",
                "tests",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "no tests collected" in result.stderr

    def test_fails_when_data_file_missing(self, tmp_path: Path) -> None:
        _write_fixture_project(tmp_path)

        result = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--data-file",
                ".coverage",
                "--markers",
                "unit",
                "--out",
                "out.json",
                "--tests-dir",
                "tests",
                "--pyproject",
                "pyproject.toml",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stderr
