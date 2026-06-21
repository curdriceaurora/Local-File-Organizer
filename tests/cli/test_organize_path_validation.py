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


@pytest.fixture(autouse=True)
def _bypass_setup_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat first-time setup as complete so these tests exercise path
    validation rather than the setup gate.

    Path validation runs *before* ``_check_setup_completed`` in organize/preview,
    so every case here already fails at validation (exit 2) regardless of setup
    state; patching the gate makes that independence explicit and matches the
    convention in other CLI tests.
    """
    monkeypatch.setattr("file_organizer.cli.organize._check_setup_completed", lambda: True)


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
    out = result.output.lower()
    assert "inside" in out and "input" in out


def test_organize_input_inside_output_is_bad_parameter(tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    in_dir = out_dir / "src"
    in_dir.mkdir(parents=True)
    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir)])
    assert result.exit_code == 2
    out = result.output.lower()
    assert "inside" in out and "output" in out


@pytest.mark.skipif(sys.platform == "win32", reason="symlink loop is POSIX-focused")
def test_organize_symlink_loop_is_bad_parameter(tmp_path: Path) -> None:
    loop = tmp_path / "loop"
    try:
        loop.symlink_to(loop)  # self-referential symlink
    except OSError:
        pytest.skip("symlink creation not supported")
    result = runner.invoke(app, ["organize", str(loop), str(tmp_path / "out")])
    assert result.exit_code == 2
    # The input root is a symlink, so it's refused by the reject_symlink guard
    # before resolution (a loop would also fail resolution if it weren't a link).
    out = result.output.lower()
    assert "symbolic link" in out or "unable to resolve" in out or "does not exist" in out


@pytest.mark.skipif(sys.platform == "win32", reason="symlink roots are POSIX-focused")
def test_organize_symlinked_input_root_is_bad_parameter(tmp_path: Path) -> None:
    """A symlinked input directory is refused (not silently canonicalized to its
    target), preserving the walker's root-symlink rejection (#1270)."""
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlink creation not supported")
    result = runner.invoke(app, ["organize", str(link), str(tmp_path / "out")])
    assert result.exit_code == 2
    assert "symbolic link" in result.output.lower()


@pytest.mark.skipif(sys.platform == "win32", reason="symlink roots are POSIX-focused")
def test_preview_symlinked_input_root_is_bad_parameter(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(real)
    except OSError:
        pytest.skip("symlink creation not supported")
    result = runner.invoke(app, ["preview", str(link)])
    assert result.exit_code == 2
    assert "symbolic link" in result.output.lower()


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
