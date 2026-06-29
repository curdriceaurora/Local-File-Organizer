"""Tests for the WP-6.1 cli-path-validation CI rail."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.ci.guardrails import check_cli_path_validation as checker

pytestmark = [pytest.mark.unit, pytest.mark.ci]


def test_flags_unvalidated_cli_path(tmp_path: Path) -> None:
    """Verify that the checker flags unvalidated path parameters in command entrypoints."""
    src = tmp_path / "app.py"
    src.write_text(
        """
@app.command()
def run(directory: Path) -> None:
    pass
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "CLI path parameter 'directory' in function 'run' is not validated" in violations[0][1]


def test_allows_validated_cli_path(tmp_path: Path) -> None:
    """Verify that resolved/validated path parameters do not trigger violations."""
    src = tmp_path / "app.py"
    src.write_text(
        """
@app.command()
def run(directory: Path) -> None:
    directory = resolve_cli_path(directory)
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_ignores_non_command_helper(tmp_path: Path) -> None:
    """Verify helper functions that are not CLI commands are ignored by the checker."""
    src = tmp_path / "app.py"
    src.write_text(
        """
def helper(directory: Path) -> None:
    pass
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_ignores_non_path_type_literal_descriptions(tmp_path: Path) -> None:
    """Verify that type annotations are checked strictly, ignoring descriptions containing 'Path'."""
    src = tmp_path / "app.py"
    src.write_text(
        """
@app.command()
def run(path: Annotated[str, typer.Argument(help="Path to inspect.")] = ".") -> None:
    pass
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_ignores_path_references_in_annotated_metadata(tmp_path: Path) -> None:
    """Verify Annotated metadata references to Path do not count as Path-typed params."""
    src = tmp_path / "app.py"
    src.write_text(
        """
@app.command()
def run(path: Annotated[str, typer.Option(path_type=Path)] = ".") -> None:
    pass
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_ignores_path_in_nested_annotated_metadata(tmp_path: Path) -> None:
    """Verify nested Annotated metadata Path references are ignored."""
    src = tmp_path / "app.py"
    src.write_text(
        """
@app.command()
def run(path: list[Annotated[str, typer.Option(path_type=Path)]]) -> None:
    pass
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_flags_unvalidated_doctor_command(tmp_path: Path) -> None:
    """Verify that 'doctor' functions are treated as CLI command entrypoints even without decorators."""
    src = tmp_path / "app.py"
    src.write_text(
        """
def doctor(path: Path) -> None:
    pass
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 1
    assert "CLI path parameter 'path' in function 'doctor' is not validated" in violations[0][1]


def test_allows_noqa_override(tmp_path: Path) -> None:
    """Verify that inline suppression markers can exempt intentional violations."""
    src = tmp_path / "app.py"
    src.write_text(
        """
@app.command()
def run(directory: Path) -> None:  # copilot: wontfix
    pass
""",
        encoding="utf-8",
    )
    violations = checker.check_file(src)
    assert len(violations) == 0


def test_allows_targeted_noqa_override(tmp_path: Path) -> None:
    src = tmp_path / "app.py"
    src.write_text(
        """
@app.command()
def run(directory: Path) -> None:  # noqa: cli-path-validation
    pass
""",
        encoding="utf-8",
    )
    assert checker.check_file(src) == []


def test_bare_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "app.py"
    src.write_text(
        """
@app.command()
def run(directory: Path) -> None:  # noqa
    pass
""",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1


def test_string_literal_noqa_does_not_suppress_violation(tmp_path: Path) -> None:
    src = tmp_path / "app.py"
    src.write_text(
        """
@app.command()
def run(directory: Path) -> None:
    msg = "noqa: cli-path-validation"
    pass
""",
        encoding="utf-8",
    )
    assert len(checker.check_file(src)) == 1
