"""Tests for file_organizer.cli.organize module.

Tests the organize and preview CLI commands:
- organize: Organize files in a directory using AI
- preview: Preview how files would be organized
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.organize import organize, preview

runner = CliRunner()

pytestmark = [pytest.mark.unit]


class TestOrganizeCommand:
    """Tests for organize command."""

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_organize_basic(self, mock_organizer_cls, tmp_path):
        """Test basic organize command."""
        mock_organizer = MagicMock()
        mock_result = MagicMock()
        mock_result.processed_files = 5
        mock_result.skipped_files = 1
        mock_result.failed_files = 0
        mock_organizer.organize.return_value = mock_result
        mock_organizer_cls.return_value = mock_organizer

        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir()
        out_dir.mkdir()

        from typer.testing import CliRunner
        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["organize", str(in_dir), str(out_dir)]
        )

        assert result.exit_code == 0
        assert "Organizing" in result.stdout

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_organize_dry_run(self, mock_organizer_cls, tmp_path):
        """Test organize with dry-run flag."""
        mock_organizer = MagicMock()
        mock_result = MagicMock()
        mock_result.processed_files = 3
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_organizer.organize.return_value = mock_result
        mock_organizer_cls.return_value = mock_organizer

        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir()
        out_dir.mkdir()

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["organize", str(in_dir), str(out_dir), "--dry-run"]
        )

        assert result.exit_code == 0
        assert "Dry run mode" in result.stdout
        mock_organizer_cls.assert_called_once_with(dry_run=True)

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_organize_with_verbose(self, mock_organizer_cls, tmp_path):
        """Test organize with verbose flag."""
        mock_organizer = MagicMock()
        mock_result = MagicMock()
        mock_result.processed_files = 2
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_organizer.organize.return_value = mock_result
        mock_organizer_cls.return_value = mock_organizer

        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir()
        out_dir.mkdir()

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["organize", str(in_dir), str(out_dir), "--verbose"]
        )

        assert result.exit_code == 0

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_organize_shows_summary(self, mock_organizer_cls, tmp_path):
        """Test organize displays file processing summary."""
        mock_organizer = MagicMock()
        mock_result = MagicMock()
        mock_result.processed_files = 10
        mock_result.skipped_files = 2
        mock_result.failed_files = 1
        mock_organizer.organize.return_value = mock_result
        mock_organizer_cls.return_value = mock_organizer

        in_dir = tmp_path / "input"
        out_dir = tmp_path / "output"
        in_dir.mkdir()
        out_dir.mkdir()

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["organize", str(in_dir), str(out_dir)]
        )

        assert result.exit_code == 0
        assert "Done:" in result.stdout or "processed" in result.stdout

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_organize_error_handling(self, mock_organizer_cls, tmp_path):
        """Test organize handles exceptions gracefully."""
        mock_organizer = MagicMock()
        mock_organizer.organize.side_effect = ValueError("Invalid input")
        mock_organizer_cls.return_value = mock_organizer

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(
            app, ["organize", "input", "output"]
        )

        assert result.exit_code == 1
        assert "Error" in result.stdout

    def test_organize_missing_output_dir(self):
        """Test organize with missing output directory argument."""
        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["organize", "input"])

        assert result.exit_code != 0


class TestPreviewCommand:
    """Tests for preview command."""

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_preview_basic(self, mock_organizer_cls, tmp_path):
        """Test basic preview command."""
        mock_organizer = MagicMock()
        mock_result = MagicMock()
        mock_result.total_files = 10
        mock_organizer.organize.return_value = mock_result
        mock_organizer_cls.return_value = mock_organizer

        in_dir = tmp_path / "input"
        in_dir.mkdir()

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["preview", str(in_dir)])

        assert result.exit_code == 0
        assert "Previewing" in result.stdout

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_preview_dry_run(self, mock_organizer_cls, tmp_path):
        """Test preview always uses dry-run mode."""
        mock_organizer = MagicMock()
        mock_result = MagicMock()
        mock_result.total_files = 5
        mock_organizer.organize.return_value = mock_result
        mock_organizer_cls.return_value = mock_organizer

        in_dir = tmp_path / "input"
        in_dir.mkdir()

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["preview", str(in_dir)])

        assert result.exit_code == 0
        mock_organizer_cls.assert_called_once_with(dry_run=True)

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_preview_shows_file_count(self, mock_organizer_cls, tmp_path):
        """Test preview displays file count."""
        mock_organizer = MagicMock()
        mock_result = MagicMock()
        mock_result.total_files = 42
        mock_organizer.organize.return_value = mock_result
        mock_organizer_cls.return_value = mock_organizer

        in_dir = tmp_path / "input"
        in_dir.mkdir()

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["preview", str(in_dir)])

        assert result.exit_code == 0
        assert "42" in result.stdout or "files would be" in result.stdout

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_preview_error_handling(self, mock_organizer_cls):
        """Test preview handles exceptions gracefully."""
        mock_organizer = MagicMock()
        mock_organizer.organize.side_effect = RuntimeError("Preview failed")
        mock_organizer_cls.return_value = mock_organizer

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["preview", "input"])

        assert result.exit_code == 1
        assert "Error" in result.stdout

    def test_preview_missing_directory(self):
        """Test preview with missing directory argument."""
        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["preview"])

        assert result.exit_code != 0

    @patch("file_organizer.cli.organize.FileOrganizer")
    def test_preview_uses_same_dir(self, mock_organizer_cls, tmp_path):
        """Test preview uses same directory for input and output."""
        mock_organizer = MagicMock()
        mock_result = MagicMock()
        mock_result.total_files = 5
        mock_organizer.organize.return_value = mock_result
        mock_organizer_cls.return_value = mock_organizer

        in_dir = tmp_path / "input"
        in_dir.mkdir()

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["preview", str(in_dir)])

        assert result.exit_code == 0
        # Should call organize with same directory twice
        organize_call = mock_organizer.organize.call_args
        assert organize_call[0][0] == Path(str(in_dir))
        assert organize_call[0][1] == Path(str(in_dir))
