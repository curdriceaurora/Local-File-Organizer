"""Tests for main Typer CLI app."""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app
from file_organizer.core.types import OrganizationResult

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from *text* for portable string assertions."""
    return _ANSI_RE.sub("", text)


def test_version_command():
    """Test the version command output."""
    with patch("file_organizer.version.__version__", "1.2.3"):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "fo 1.2.3" in result.stdout


@patch("file_organizer.cli.setup.setup_run")
@pytest.mark.ci
@pytest.mark.integration
def test_start_command_runs_quick_start(mock_setup_run):
    """start routes to setup quick-start mode."""
    result = runner.invoke(app, ["start"])
    assert result.exit_code == 0
    mock_setup_run.assert_called_once_with(mode="quick-start", profile="default", dry_run=False)


@patch("file_organizer.cli.setup.setup_run")
@pytest.mark.ci
@pytest.mark.integration
def test_start_command_merges_global_dry_run(mock_setup_run):
    """Global --dry-run should propagate to start/quickstart setup."""
    result = runner.invoke(app, ["--dry-run", "start"])
    assert result.exit_code == 0
    mock_setup_run.assert_called_once_with(mode="quick-start", profile="default", dry_run=True)


@patch("file_organizer.cli.setup.setup_run")
@pytest.mark.ci
@pytest.mark.integration
def test_quickstart_alias_runs_quick_start(mock_setup_run):
    """quickstart alias routes to setup quick-start mode."""
    result = runner.invoke(app, ["quickstart", "--profile", "work", "--dry-run"])
    assert result.exit_code == 0
    mock_setup_run.assert_called_once_with(mode="quick-start", profile="work", dry_run=True)


@pytest.mark.uses_setup_gate
@patch("file_organizer.config.manager.ConfigManager")
def test_organize_requires_setup_completed(mock_cm):
    """organize exits with code 1 when setup is incomplete."""
    mock_cm.return_value.load.return_value.setup_completed = False
    result = runner.invoke(app, ["organize", "in", "out"])
    assert result.exit_code == 1
    assert "setup" in result.stdout.lower()


@pytest.mark.uses_setup_gate
@patch("file_organizer.config.manager.ConfigManager")
def test_preview_requires_setup_completed(mock_cm):
    """preview exits with code 1 when setup is incomplete."""
    mock_cm.return_value.load.return_value.setup_completed = False
    result = runner.invoke(app, ["preview", "in_dir"])
    assert result.exit_code == 1
    assert "setup" in result.stdout.lower()


@pytest.mark.ci
@pytest.mark.integration
def test_organize_help_hides_advanced_flags_by_default():
    """Default organize help focuses on first-touch options."""
    result = runner.invoke(app, ["organize", "--help"], terminal_width=120)
    assert result.exit_code == 0
    # Typer forces terminal colors when GITHUB_ACTIONS is set, and rich splits
    # option names across ANSI style segments — strip styling before matching.
    plain = _strip_ansi(result.stdout)
    assert "--advanced-help" in plain
    assert "--max-workers" not in plain
    assert "--prefetch-depth" not in plain
    assert "--no-prefetch" not in plain
    assert "--transcribe-audio" not in plain


@pytest.mark.ci
@pytest.mark.integration
def test_organize_advanced_help_lists_hidden_tuning_flags():
    """Advanced help should expose full tuning controls without args."""
    result = runner.invoke(app, ["organize", "--advanced-help"])
    assert result.exit_code == 0
    plain = _strip_ansi(result.stdout)
    assert "--max-workers" in plain
    assert "--prefetch-depth" in plain
    assert "--no-prefetch" in plain
    assert "--transcribe-audio" in plain


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.cli.organize._create_service")
def test_organize_command_live(mock_create_service, _mock_setup, tmp_path):
    """Test organize command executes the canonical service."""
    service = mock_create_service.return_value
    service.execute.return_value = OrganizationResult(processed_files=5, skipped_files=1)

    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir)])

    assert result.exit_code == 0
    assert "Organizing" in result.stdout
    request, plan = service.execute.call_args.args
    assert plan is None
    assert request.input_path == in_dir.resolve()
    assert request.output_path == out_dir.resolve()


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.cli.organize._create_service")
def test_organize_command_dry_run(mock_create_service, _mock_setup, tmp_path):
    """Test organize command processes dry-run flag."""
    service = mock_create_service.return_value
    service.preview.return_value = OrganizationResult(total_files=3, processed_files=3)

    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    # A.cli: input_dir must exist; output_dir may not (organizer creates it).
    in_dir.mkdir()

    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir), "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run mode" in result.stdout
    request = service.preview.call_args.args[0]
    assert request.input_path == in_dir.resolve()
    assert request.output_path == out_dir.resolve()


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.cli.organize._create_service")
def test_organize_command_error(mock_create_service, _mock_setup, tmp_path):
    """Test organize command handles exceptions gracefully."""
    mock_create_service.return_value.execute.side_effect = RuntimeError("Something broke")

    # A.cli: real directories required so the service-layer error path
    # (not CLI-arg-validation path) is exercised.
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir)])

    assert result.exit_code == 1
    assert "Error: Something broke" in result.stdout


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.cli.organize._create_service")
def test_preview_command(mock_create_service, _mock_setup, tmp_path):
    """Test preview command uses canonical scan and preview calls."""
    service = mock_create_service.return_value
    service.preview.return_value = OrganizationResult(total_files=10)

    in_dir = tmp_path / "in_dir"
    in_dir.mkdir()
    result = runner.invoke(app, ["preview", str(in_dir)])

    assert result.exit_code == 0
    assert "Previewing" in result.stdout
    resolved = in_dir.resolve()
    request = service.preview.call_args.args[0]
    assert request.input_path == request.output_path == resolved
    service.scan.assert_called_once_with(request)


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.cli.organize._create_service")
def test_preview_command_error(mock_create_service, _mock_setup, tmp_path):
    """Test preview command handles exceptions."""
    mock_create_service.return_value.preview.side_effect = ValueError("Bad input")

    in_dir = tmp_path / "in_dir"
    in_dir.mkdir()
    result = runner.invoke(app, ["preview", str(in_dir)])

    assert result.exit_code == 1
    assert "Error: Bad input" in result.stdout


@pytest.mark.ci
def test_profile_legacy_command_guidance():
    """`profile` should provide actionable guidance when unavailable."""
    result = runner.invoke(app, ["profile"])
    assert result.exit_code == 0
    assert "profile" in result.stdout.lower()
    assert "config show --profile" in result.stdout


@pytest.mark.ci
def test_profile_legacy_command_accepts_extra_args():
    """`profile list` should surface as unsupported, not as a successful command."""
    result = runner.invoke(app, ["profile", "list"])
    assert result.exit_code == 2
    assert "Received extra arguments: list" in result.stdout


@pytest.mark.ci
def test_register_profile_command_skips_when_already_registered():
    """_register_profile_command is a no-op when 'profile' is already in commands."""
    from file_organizer.cli.main import _register_profile_command

    mock_group = MagicMock()
    mock_group.commands = {"profile": MagicMock()}

    with patch("typer.main.get_group", return_value=mock_group):
        _register_profile_command()

    mock_group.add_command.assert_not_called()
