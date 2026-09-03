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
    """Realistic context attribution across module.py's four statement lines.

    module.py is "def a():\\n    return 1\\n\\n\\ndef b():\\n    return 2\\n" --
    lines 1, 2, 5, 6 are the four statements (def a / return 1 / def b / return 2).

    Lines 1 and 5 (the `def` lines) go to the empty context "" -- matching
    real pytest-cov behavior, where collection-time imports execute a
    module's top-level `def`/`class` statements before any test's own
    setup/call/teardown context is active (see build_context_pattern()'s
    docstring). Only the *bodies* (lines 2 and 6) are attributed to the
    test that actually calls them: test_a calls a() (line 2), test_b calls
    b() (line 6). A synthetic db that instead assigned def-lines directly
    to test contexts (as an earlier version of this fixture did) can't
    catch a regression in the "" handling -- it never exercises that path.
    """
    data = coverage.CoverageData(basename=str(tmp_path / ".coverage"))
    data.set_context("")
    data.add_lines({str(module_path): [1, 5]})
    data.set_context("tests/test_sample.py::test_a|run")
    data.add_lines({str(module_path): [2]})
    data.set_context("tests/test_sample.py::test_b|run")
    data.add_lines({str(module_path): [6]})
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
        # "unit" ran test_a (line 2) plus the shared "" collection-time
        # lines (1, 5) that every view sees -- 3 of the 4 statements.
        assert summary["covered_lines"] == 3
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
        # "integration" ran test_b (line 6) plus the shared "" lines (1, 5) --
        # same count as the unit view (3/4), but a *different* set of lines.
        assert summary["covered_lines"] == 3
        assert summary["num_statements"] == 4

    def test_definition_lines_from_empty_context_appear_in_every_view(self, tmp_path: Path) -> None:
        """The core fix (PR review, issue #1767): collection-time/definition
        lines (the "" context) must be included in EVERY marker view, not
        just whichever test happens to run first -- they're executed once,
        unconditionally, regardless of which tests get selected."""
        module_path = _write_fixture_project(tmp_path)
        _write_synthetic_coverage_db(tmp_path, module_path)

        import json

        for markers, out_name in [
            ("unit", "out-unit.json"),
            ("integration", "out-integration.json"),
        ]:
            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--data-file",
                    ".coverage",
                    "--markers",
                    markers,
                    "--out",
                    out_name,
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
            report = json.loads((tmp_path / out_name).read_text())
            executed = report["files"]["src/mypkg/module.py"]["executed_lines"]
            assert 1 in executed, f"{markers} view is missing the def-a line from the '' context"
            assert 5 in executed, f"{markers} view is missing the def-b line from the '' context"

    def test_min_combined_fails_below_threshold(self, tmp_path: Path) -> None:
        module_path = _write_fixture_project(tmp_path)
        _write_synthetic_coverage_db(tmp_path, module_path)

        # unit view is 3/4 = 75% combined (no branches in this fixture) — below 90.
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
                "90",
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
