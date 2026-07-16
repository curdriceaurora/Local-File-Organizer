"""CI-tagged smoke tests: every CLI command wired to ``resolve_cli_path``
rejects a non-existent directory with exit code 2 (``typer.BadParameter``).

The detailed helper semantics live in ``test_path_validation.py``. This file
exists so PR-CI's diff-coverage gate sees the call sites in
``src/cli/{daemon,organize,main,rules,utilities,benchmark,suggest,dedupe_v2,autotag_v2}.py``
as exercised under the ``-m ci`` marker (the integration tests that drive
these commands end-to-end run in the main-push suite, not in PR-CI).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.daemon import daemon_app
from file_organizer.cli.main import app

pytestmark = [pytest.mark.ci, pytest.mark.unit]

runner = CliRunner()


@pytest.fixture(autouse=True)
def _bypass_setup_wizard() -> Iterator[None]:
    """Skip the organize/preview setup-wizard check; the wiring test only
    needs to reach ``resolve_cli_path``."""
    with patch("file_organizer.cli.organize._check_setup_completed", return_value=True):
        yield


def _bogus(tmp_path: Path) -> str:
    return str(tmp_path / "does_not_exist")


def _flat_output(output: str) -> str:
    """Collapse rich/typer line-wrapping (width-dependent newlines) for substring asserts."""
    return " ".join(output.split()).lower()


# (app, argv-template) — each template uses ``{p}`` for the bogus path.
# Commands that take two paths get two bogus substitutions; one rejected path
# is enough to trigger the ``resolve_cli_path`` branch.
_COMMANDS: list[tuple[str, list[str]]] = [
    ("app", ["organize", "{p}", "{p2}"]),
    ("app", ["preview", "{p}"]),
    ("app", ["benchmark", "run", "{p}"]),
    ("app", ["suggest", "files", "{p}"]),
    ("app", ["suggest", "apply", "{p}"]),
    ("app", ["suggest", "patterns", "{p}"]),
    ("app", ["search", "{p}", "query"]),
    ("app", ["analyze", "{p}"]),
    ("app", ["analytics", "{p}"]),
    ("app", ["autotag", "suggest", "{p}"]),
    ("app", ["autotag", "apply", "{p}", "dummy-tag"]),
    ("app", ["autotag", "batch", "{p}"]),
    ("app", ["dedupe", "scan", "{p}"]),
    ("app", ["dedupe", "resolve", "{p}"]),
    ("app", ["dedupe", "report", "{p}"]),
    ("app", ["rules", "preview", "{p}"]),
    ("app", ["rules", "import", "{p}"]),
    ("daemon", ["process", "{p}", "{p2}"]),
    ("daemon", ["start", "--watch-dir", "{p}", "--output-dir", "{p2}"]),
    ("daemon", ["watch", "{p}"]),
]


@pytest.mark.parametrize(("app_key", "argv_template"), _COMMANDS)
def test_cli_command_rejects_missing_path(
    app_key: str, argv_template: list[str], tmp_path: Path
) -> None:
    target = daemon_app if app_key == "daemon" else app
    bogus = _bogus(tmp_path)
    argv = [a.replace("{p}", bogus).replace("{p2}", bogus + "_other") for a in argv_template]
    result = runner.invoke(target, argv)
    # typer.BadParameter → exit code 2 (POSIX usage-error convention).
    assert result.exit_code == 2, (
        f"expected exit 2 for {argv}; got {result.exit_code}\noutput: {result.output}"
    )
    assert "does not exist" in _flat_output(result.output)


def test_benchmark_compare_directory_rejected(tmp_path: Path) -> None:
    """``--compare`` points at a JSON baseline file; directories must be
    rejected at the CLI boundary (exit 2) rather than later at read_text()
    with IsADirectoryError (exit 1). Covers the ``_validate_compare_path``
    helper's is_file branch.
    """
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    compare_dir = tmp_path / "a_dir"
    compare_dir.mkdir()
    result = runner.invoke(app, ["benchmark", "run", str(input_dir), "--compare", str(compare_dir)])
    assert result.exit_code == 2
    assert "not a regular file" in _flat_output(result.output)


def test_analyze_directory_rejected_with_regular_file_message(tmp_path: Path) -> None:
    """After ``resolve_cli_path`` accepts the directory (must_be_dir=False),
    the explicit ``is_file()`` guard in analyze prints "not a regular file"
    and exits 1 (distinct from exit 2's CLI-boundary usage errors).
    """
    d = tmp_path / "target"
    d.mkdir()
    result = runner.invoke(app, ["analyze", str(d)])
    assert result.exit_code == 1
    assert "not a regular file" in _flat_output(result.output)
