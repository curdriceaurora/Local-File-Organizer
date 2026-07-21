"""Test that the setup gate runs for all commands except an allowlist.

Pins the contract: pre-setup, the gate fires and shows the friendly
"First-time setup required" panel for every non-allowlisted command;
allowlisted commands (`setup`, `version`, `doctor`, `update`,
`recover`, `config`, `hardware-info`) bypass the gate so users can run
diagnostics or finish setup without a chicken-and-egg loop.

Step 3 promoted the gate from organize/preview to the global Typer
callback. This test guards against regression — without it, a future
edit to the allowlist could re-introduce the original bug where every
non-organize command crashes pre-setup with a cryptic stack trace.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app


@pytest.fixture
def fresh_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Force a config dir where setup_completed is False.

    Patches `config.manager.DEFAULT_CONFIG_DIR` so the gate's
    `ConfigManager().load()` reads from an empty dir → returns a
    default `AppConfig(setup_completed=False)`.
    """
    monkeypatch.setattr("file_organizer.config.manager.DEFAULT_CONFIG_DIR", tmp_path)
    return tmp_path


@pytest.mark.unit
@pytest.mark.ci
@pytest.mark.uses_setup_gate
@pytest.mark.parametrize(
    "cmd_args",
    [
        ["version"],  # prints version, no config or services needed
        ["config", "list"],  # list profiles; returns "No profiles found" on empty dir
        ["hardware-info"],  # reads local hardware; no config or services needed
    ],
)
def test_allowlisted_commands_bypass_gate(cmd_args: list[str], fresh_config: Path) -> None:
    """Allowlisted commands reach their handler even when setup_completed=False."""
    runner = CliRunner()
    result = runner.invoke(app, cmd_args)
    assert result.exit_code == 0, result.output
    assert "First-time setup required" not in result.output


@pytest.mark.unit
@pytest.mark.ci
@pytest.mark.uses_setup_gate
@pytest.mark.parametrize("cmd", ["start", "quickstart"])
@patch("file_organizer.cli.setup.setup_run")
def test_beginner_commands_bypass_gate(mock_setup_run, cmd: str, fresh_config: Path) -> None:
    """New beginner entry commands should be reachable pre-setup."""
    runner = CliRunner()
    result = runner.invoke(app, [cmd, "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "First-time setup required" not in result.output
    mock_setup_run.assert_called_once()


@pytest.mark.unit
@pytest.mark.ci
@pytest.mark.uses_setup_gate
@pytest.mark.parametrize("cmd", ["doctor", "setup"])
def test_allowlisted_entry_commands_not_gated(cmd: str, fresh_config: Path) -> None:
    """Entry-level allowlisted commands never show the setup gate panel.

    Exit code may be non-zero (doctor service checks may fail; setup
    expects an interactive tty), but the first-run gate panel must be
    absent — that's the contract this test pins.
    """
    runner = CliRunner()
    result = runner.invoke(app, [cmd])
    assert "First-time setup required" not in result.output


@pytest.mark.integration
@pytest.mark.ci
@pytest.mark.uses_setup_gate
def test_organize_blocked_pre_setup(fresh_config: Path, tmp_path: Path) -> None:
    """`fo organize ...` pre-setup hits the gate and shows the panel.

    Uses real input/output dirs to get past path validation and into
    the actual gate path. The gate is in `main_callback` so any
    invocation without `--help` triggers it.
    """
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"

    runner = CliRunner()
    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir)])
    # The gate exits the process; result.output carries the panel.
    assert "First-time setup required" in result.output


@pytest.mark.integration
@pytest.mark.ci
@pytest.mark.uses_setup_gate
@pytest.mark.parametrize("local_json", [False, True], ids=["global", "command-local"])
def test_organize_setup_gate_honors_json_contract(
    local_json: bool, fresh_config: Path, tmp_path: Path
) -> None:
    """Both global and command-local JSON modes emit one setup error object."""
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    args = ["organize", str(input_dir), str(output_dir)]
    if local_json:
        args.append("--json")
    else:
        args.insert(0, "--json")

    result = CliRunner().invoke(app, args)

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload == {
        "command": "organize",
        "error": {
            "code": "setup_required",
            "details": {"action": "fo setup"},
            "message": "First-time setup is required. Run `fo setup` to continue.",
            "retryable": False,
        },
        "outcome": "error",
        "schema_version": 1,
    }


@pytest.mark.integration
@pytest.mark.ci
@pytest.mark.uses_setup_gate
@pytest.mark.parametrize("cmd", ["search", "analyze"])
def test_other_entry_commands_blocked_pre_setup(
    cmd: str, fresh_config: Path, tmp_path: Path
) -> None:
    """Step 3's win: search/analyze are now gated like organize.

    Before Step 3, only organize/preview ran the gate; search and
    analyze would fail pre-setup with cryptic errors. This test pins
    the new behavior — they show the friendly panel instead.
    """
    runner = CliRunner()
    result = runner.invoke(app, [cmd])  # no --help so the gate runs
    # Some commands may also error on missing required args; the
    # panel must appear regardless of the secondary failure.
    assert "First-time setup required" in result.output


@pytest.mark.unit
@pytest.mark.ci
@pytest.mark.uses_setup_gate
@pytest.mark.parametrize("cmd", ["organize", "search", "analyze", "preview"])
def test_help_bypasses_gate_pre_setup(cmd: str, fresh_config: Path) -> None:
    """``fo <cmd> --help`` shows help text even when setup has not been run.

    Regression test for issue #241.  The original implementation relied on
    ``ctx.resilient_parsing`` to bypass the gate for ``--help``, but Click
    only sets ``resilient_parsing=True`` during shell-completion parsing — not
    for ``--help``.  The fix adds a ``LazyTyperGroup.parse_args`` override
    that stashes ``help_requested`` in ``ctx.meta`` before Click's
    ``resolve_command`` consumes the args, and ``main_callback`` checks that
    flag to skip the gate.

    Only ``--help`` is tested: ``-h`` is not a registered help alias in this
    CLI, so it must NOT bypass the gate (a ``-h`` token could be a value to
    another option such as ``--type -h``).

    ``fresh_config`` is used for its fixture side-effect (patching the config
    dir to simulate pre-setup state); its return value is intentionally unused.
    """
    runner = CliRunner()
    result = runner.invoke(app, [cmd, "--help"])
    assert "First-time setup required" not in result.output, (
        f"`fo {cmd} --help` showed the setup gate pre-setup"
    )
    assert result.exit_code == 0, (
        f"`fo {cmd} --help` exited {result.exit_code}: {result.output[:200]}"
    )
