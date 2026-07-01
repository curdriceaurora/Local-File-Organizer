"""Tests for main Typer CLI app."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


def test_version_command():
    """Test the version command output."""
    with patch("file_organizer.version.__version__", "1.2.3"):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "fo 1.2.3" in result.stdout


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


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.core.organizer.FileOrganizer")
def test_organize_command_live(mock_organizer_cls, _mock_setup, tmp_path):
    """Test organize command executes FileOrganizer correctly."""
    mock_instance = MagicMock()
    mock_result = MagicMock(processed_files=5, skipped_files=1, failed_files=0)
    mock_instance.organize.return_value = mock_result
    mock_organizer_cls.return_value = mock_instance

    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir)])

    assert result.exit_code == 0
    assert "Organizing" in result.stdout
    mock_organizer_cls.assert_called_once_with(
        dry_run=False,
        parallel_workers=None,
        prefetch_depth=2,
        enable_vision=True,
        no_prefetch=False,
        transcribe_audio=False,
        max_transcribe_seconds=600.0,
    )
    mock_instance.organize.assert_called_once_with(in_dir, out_dir)


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.core.organizer.FileOrganizer")
def test_organize_command_dry_run(mock_organizer_cls, _mock_setup, tmp_path):
    """Test organize command processes dry-run flag."""
    mock_instance = MagicMock()
    mock_result = MagicMock(processed_files=3, skipped_files=0, failed_files=0)
    mock_instance.organize.return_value = mock_result
    mock_organizer_cls.return_value = mock_instance

    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    # A.cli: input_dir must exist; output_dir may not (organizer creates it).
    in_dir.mkdir()

    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir), "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run mode" in result.stdout
    mock_organizer_cls.assert_called_once_with(
        dry_run=True,
        parallel_workers=None,
        prefetch_depth=2,
        enable_vision=True,
        no_prefetch=False,
        transcribe_audio=False,
        max_transcribe_seconds=600.0,
    )
    # A.cli resolves the path args before dispatching; the service sees
    # the canonical absolute form.
    mock_instance.organize.assert_called_once_with(in_dir.resolve(), out_dir.resolve())


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.core.organizer.FileOrganizer")
def test_organize_command_error(mock_organizer_cls, _mock_setup, tmp_path):
    """Test organize command handles exceptions gracefully."""
    mock_instance = MagicMock()
    mock_instance.organize.side_effect = RuntimeError("Something broke")
    mock_organizer_cls.return_value = mock_instance

    # A.cli: real directories required so the service-layer error path
    # (not CLI-arg-validation path) is exercised.
    in_dir = tmp_path / "in"
    in_dir.mkdir()
    out_dir = tmp_path / "out"
    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir)])

    assert result.exit_code == 1
    assert "Error: Something broke" in result.stdout


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.core.organizer.FileOrganizer")
def test_preview_command(mock_organizer_cls, _mock_setup, tmp_path):
    """Test preview command runs organizer in dry_run mode."""
    mock_instance = MagicMock()
    mock_result = MagicMock(total_files=10)
    mock_instance.organize.return_value = mock_result
    mock_organizer_cls.return_value = mock_instance

    in_dir = tmp_path / "in_dir"
    in_dir.mkdir()
    result = runner.invoke(app, ["preview", str(in_dir)])

    assert result.exit_code == 0
    assert "Previewing" in result.stdout
    mock_organizer_cls.assert_called_once_with(
        dry_run=True,
        parallel_workers=None,
        prefetch_depth=2,
        enable_vision=True,
        no_prefetch=False,
        transcribe_audio=False,
        max_transcribe_seconds=600.0,
    )
    resolved = in_dir.resolve()
    mock_instance.organize.assert_called_once_with(resolved, resolved)


@patch("file_organizer.cli.organize._check_setup_completed", return_value=True)
@patch("file_organizer.core.organizer.FileOrganizer")
def test_preview_command_error(mock_organizer_cls, _mock_setup, tmp_path):
    """Test preview command handles exceptions."""
    mock_instance = MagicMock()
    mock_instance.organize.side_effect = ValueError("Bad input")
    mock_organizer_cls.return_value = mock_instance

    in_dir = tmp_path / "in_dir"
    in_dir.mkdir()
    result = runner.invoke(app, ["preview", str(in_dir)])

    assert result.exit_code == 1
    assert "Error: Bad input" in result.stdout


def test_profile_legacy_command_guidance():
    """`profile` should provide actionable guidance when unavailable."""
    result = runner.invoke(app, ["profile"])
    assert result.exit_code == 0
    assert "profile" in result.stdout.lower()
    assert "config show --profile" in result.stdout


def test_profile_legacy_command_accepts_extra_args():
    """`profile` shim should still handle unknown subcommand-style args."""
    result = runner.invoke(app, ["profile", "list"])
    assert result.exit_code == 0
    assert "Received extra arguments: list" in result.stdout
