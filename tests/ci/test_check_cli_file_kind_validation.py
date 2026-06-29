"""Tests for the cli-file-kind-validation CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_cli_file_kind_validation as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_flags_unvalidated_must_be_dir_false(tmp_path: Path) -> None:
    """Verify that must_be_dir=False without kind check triggers a violation."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    # No kind check here — should be flagged
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "resolved" in violations[0][1]
    assert "must_be_dir=False" in violations[0][1]


def test_allows_is_file_check(tmp_path: Path) -> None:
    """Verify that is_file() check satisfies the guardrail."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    if not resolved.is_file():
        raise typer.BadParameter(f"Not a file: {resolved}")
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_allows_is_dir_check(tmp_path: Path) -> None:
    """Verify that is_dir() check satisfies the guardrail."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(dir_path: Path) -> None:
    resolved = resolve_cli_path(dir_path, must_exist=True, must_be_dir=False)
    if not resolved.is_dir():
        raise typer.BadParameter(f"Not a dir: {resolved}")
    process_dir(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_flags_noop_is_file_check_without_rejecting_guard(tmp_path: Path) -> None:
    """Verify no-op kind checks are still flagged when they do not reject."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    resolved.is_file()  # no-op: result ignored, wrong kind not rejected
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "function 'run'" in violations[0][1]
    assert "resolved" in violations[0][1]


def test_allows_validate_regular_file_helper(tmp_path: Path) -> None:
    """Verify that validate_regular_file() call satisfies the guardrail."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path, validate_regular_file

@app.command()
def run(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    validate_regular_file(resolved, param_name="file_path")
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_allows_validate_is_dir_helper(tmp_path: Path) -> None:
    """Verify that validate_is_dir() call satisfies the guardrail."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path, validate_is_dir

@app.command()
def run(dir_path: Path) -> None:
    resolved = resolve_cli_path(dir_path, must_exist=True, must_be_dir=False)
    validate_is_dir(resolved, param_name="directory")
    process_dir(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_allows_exists_and_is_file_pattern(tmp_path: Path) -> None:
    """Verify that exists() + is_file() pattern satisfies the guardrail."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(output: Path) -> None:
    resolved = resolve_cli_path(output, must_exist=False, must_be_dir=False)
    if resolved.exists() and not resolved.is_file():
        raise typer.BadParameter(f"Output is not a file: {resolved}")
    write_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_ignores_non_command_helper(tmp_path: Path) -> None:
    """Verify that helper functions (not CLI commands) are ignored."""
    src = tmp_path / "app.py"
    src.write_text(
        """
def helper(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    # No kind check, but helper function so shouldn't be flagged
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_ignores_doctor_command_with_validation(tmp_path: Path) -> None:
    """Verify that doctor command is treated as CLI command."""
    src = tmp_path / "app.py"
    src.write_text(
        """
def doctor(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    if not resolved.is_file():
        raise typer.BadParameter("Not a file")
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_flags_doctor_command_without_validation(tmp_path: Path) -> None:
    """Verify that doctor command without kind validation is flagged."""
    src = tmp_path / "app.py"
    src.write_text(
        """
def doctor(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    # No kind check — should be flagged even though it's a doctor function
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_allows_noqa_override(tmp_path: Path) -> None:
    """Verify that copilot: wontfix suppression exempts from validation."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)  # copilot: wontfix
    # Suppressed — should not be flagged
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_allows_targeted_noqa_override(tmp_path: Path) -> None:
    """Verify that targeted noqa suppression exempts from validation."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)  # noqa: cli-file-kind-validation
    # Suppressed via targeted noqa — should not be flagged
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    """Verify that bare noqa (without code) does not suppress this violation."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)  # noqa
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_multiple_must_be_dir_false_calls(tmp_path: Path) -> None:
    """Verify checking multiple must_be_dir=False calls in same function."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(file1: Path, file2: Path) -> None:
    f1 = resolve_cli_path(file1, must_exist=True, must_be_dir=False)
    if not f1.is_file():
        raise typer.BadParameter("file1 is not a file")

    f2 = resolve_cli_path(file2, must_exist=True, must_be_dir=False)
    # f2 has no kind check — should be flagged

    process_files(f1, f2)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "f2" in violations[0][1]


def test_kind_check_on_different_variable_does_not_suppress(tmp_path: Path) -> None:
    """Verify that kind check on a different variable does not suppress violation."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    other = Path("something")
    if not other.is_file():  # Check on wrong variable
        raise typer.BadParameter("other is not a file")
    process_file(resolved)  # resolved still not validated
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_kind_check_too_far_away_does_not_suppress(tmp_path: Path) -> None:
    """Verify that kind check too far away (>15 lines) does not suppress violation."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def run(file_path: Path) -> None:
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    # Many lines of code in between...
    a = 1
    b = 2
    c = 3
    d = 4
    e = 5
    f = 6
    g = 7
    h = 8
    i = 9
    j = 10
    k = 11
    l = 12
    m = 13
    n = 14
    o = 15
    p = 16
    # Kind check happens here, too far away (>15 lines)
    if not resolved.is_file():
        raise typer.BadParameter("Not a file")
    process_file(resolved)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1


def test_output_file_validation_pattern(tmp_path: Path) -> None:
    """Verify typical output file validation pattern from rules.py."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def export(output: Path) -> None:
    output = resolve_cli_path(output, must_exist=False, must_be_dir=False)
    if not output.parent.is_dir():
        raise typer.BadParameter(f"Output directory does not exist: {output.parent}")
    if output.exists() and not output.is_file():
        raise typer.BadParameter(f"Output path is not a regular file: {output}")
    write_output(output)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_token_file_validation_pattern(tmp_path: Path) -> None:
    """Verify token/config file validation pattern from api.py."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def login(save_to: Path | None = None) -> None:
    if save_to is not None:
        save_to = resolve_cli_path(save_to, must_exist=False, must_be_dir=False)
        if save_to.exists() and not save_to.is_file():
            raise typer.BadParameter(f"Token output path is not a regular file: {save_to}")
        save_token(save_to)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_journal_file_validation_pattern(tmp_path: Path) -> None:
    """Verify journal file validation pattern from main.py."""
    src = tmp_path / "app.py"
    src.write_text(
        """
from file_organizer.cli.path_validation import resolve_cli_path

@app.command()
def recover(journal: Path | None = None) -> None:
    if journal is not None:
        journal = resolve_cli_path(journal, must_exist=True, must_be_dir=False)
        if not journal.is_file():
            raise typer.BadParameter(f"Journal path is not a regular file: {journal}")
    do_recover(journal)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0
