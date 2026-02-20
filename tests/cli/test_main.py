"""Tests for main Typer CLI app."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


def test_version_command():
    """Test the version command output."""
    with patch("file_organizer.version.__version__", "1.2.3"):
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "file-organizer 1.2.3" in result.stdout


@patch("file_organizer.core.organizer.FileOrganizer")
def test_organize_command_live(mock_organizer_cls, tmp_path):
    """Test organize command executes FileOrganizer correctly."""
    mock_instance = MagicMock()
    mock_organizer_cls.return_value = mock_instance

    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir)])

    assert result.exit_code == 0
    assert "Organizing" in result.stdout
    mock_organizer_cls.assert_called_once_with(
        input_dir=in_dir, output_dir=out_dir, dry_run=False
    )
    mock_instance.run.assert_called_once()


@patch("file_organizer.core.organizer.FileOrganizer")
def test_organize_command_dry_run(mock_organizer_cls, tmp_path):
    """Test organize command processes dry-run flag."""
    mock_instance = MagicMock()
    mock_organizer_cls.return_value = mock_instance

    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"

    result = runner.invoke(app, ["organize", str(in_dir), str(out_dir), "--dry-run"])

    assert result.exit_code == 0
    assert "Dry run mode" in result.stdout
    mock_organizer_cls.assert_called_once_with(
        input_dir=in_dir, output_dir=out_dir, dry_run=True
    )


@patch("file_organizer.core.organizer.FileOrganizer")
def test_organize_command_error(mock_organizer_cls, tmp_path):
    """Test organize command handles exceptions gracefully."""
    mock_instance = MagicMock()
    mock_instance.run.side_effect = RuntimeError("Something broke")
    mock_organizer_cls.return_value = mock_instance

    result = runner.invoke(app, ["organize", "in", "out"])

    assert result.exit_code == 1
    assert "Error: Something broke" in result.stdout


@patch("file_organizer.core.organizer.FileOrganizer")
def test_preview_command(mock_organizer_cls, tmp_path):
    """Test preview command runs organizer in dry_run mode."""
    mock_instance = MagicMock()
    mock_organizer_cls.return_value = mock_instance

    result = runner.invoke(app, ["preview", "in_dir"])

    assert result.exit_code == 0
    assert "Previewing" in result.stdout
    mock_organizer_cls.assert_called_once_with(input_dir=Path("in_dir"), dry_run=True)
    mock_instance.run.assert_called_once()


@patch("file_organizer.core.organizer.FileOrganizer")
def test_preview_command_error(mock_organizer_cls, tmp_path):
    """Test preview command handles exceptions."""
    mock_instance = MagicMock()
    mock_instance.run.side_effect = ValueError("Bad input")
    mock_organizer_cls.return_value = mock_instance

    result = runner.invoke(app, ["preview", "in_dir"])

    assert result.exit_code == 1
    assert "Error: Bad input" in result.stdout


@patch("file_organizer.tui.run_tui")
def test_tui_command(mock_run_tui):
    """Test launching TUI."""
    result = runner.invoke(app, ["tui"])
    assert result.exit_code == 0
    mock_run_tui.assert_called_once()
