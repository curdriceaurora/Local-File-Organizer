"""CLI boundary path-validation for organize/preview (#1269).

`organize`/`preview` route their path arguments through
`cli.path_validation.resolve_cli_path` / `validate_pair` before any filesystem
work, so missing/non-directory/symlink-loop paths and incoherent input/output
pairs surface as `typer.BadParameter` (exit code 2) rather than a traceback.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit, pytest.mark.ci]

runner = CliRunner()


def test_organize_missing_input_is_bad_parameter(tmp_path: Path) -> None:
    result = runner.invoke(app, ["organize", str(tmp_path / "nope"), str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "does not exist" in result.output.lower()


def test_organize_non_directory_input_is_bad_parameter(tmp_path: Path) -> None:
    f = tmp_path / "a_file.txt"
    f.write_text("x")
    result = runner.invoke(app, ["organize", str(f), str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "not a directory" in result.output.lower()


def test_organize_identical_input_output_is_bad_parameter(tmp_path: Path) -> None:
    d = tmp_path / "data"
    d.mkdir()
    result = runner.invoke(app, ["organize", str(d), str(d)])
    assert result.exit_code == 2
    assert "same path" in result.output.lower()


def test_organize_output_inside_input_is_bad_parameter(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = in_dir / "sorted"
    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir)])
    assert result.exit_code == 2
    assert "inside the input" in result.output.lower()


def test_organize_input_inside_output_is_bad_parameter(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    in_dir = out_dir / "src"
    in_dir.mkdir(parents=True)
    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir)])
    assert result.exit_code == 2
    assert "inside the output" in result.output.lower()


@pytest.mark.skipif(sys.platform == "win32", reason="symlink loop is POSIX-focused")
def test_organize_symlink_loop_is_bad_parameter(tmp_path: Path) -> None:
    loop = tmp_path / "loop"
    try:
        loop.symlink_to(loop)  # self-referential → resolve() raises
    except OSError:
        pytest.skip("symlink creation not supported")
    result = runner.invoke(app, ["organize", str(loop), str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "unable to resolve" in result.output.lower() or "does not exist" in result.output.lower()


def test_preview_missing_input_is_bad_parameter(tmp_path: Path) -> None:
    result = runner.invoke(app, ["preview", str(tmp_path / "nope")])
    assert result.exit_code == 2
    assert "does not exist" in result.output.lower()


def test_preview_non_directory_input_is_bad_parameter(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x")
    result = runner.invoke(app, ["preview", str(f)])
    assert result.exit_code == 2
    assert "not a directory" in result.output.lower()
