"""Tests for the organize CLI commands (organize.py).

Tests the ``organize`` and ``preview`` top-level commands with mocked
FileOrganizer service.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit]

runner = CliRunner()


def _mock_result(
    total: int = 10,
    processed: int = 8,
    skipped: int = 1,
    failed: int = 1,
) -> MagicMock:
    """Create a mock organize result."""
    result = MagicMock()
    result.total_files = total
    result.processed_files = processed
    result.skipped_files = skipped
    result.failed_files = failed
    return result


# ---------------------------------------------------------------------------
# organize
# ---------------------------------------------------------------------------


class TestOrganize:
    """Tests for the ``organize`` command."""

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_basic(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(app, ["organize", str(input_dir), str(output_dir)])
        assert result.exit_code == 0
        assert "8 processed" in result.output
        assert "1 skipped" in result.output

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_dry_run(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(app, ["organize", str(input_dir), str(output_dir), "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in result.output.lower() or "Dry run" in result.output

    @patch(
        "file_organizer.core.organizer.FileOrganizer",
        side_effect=RuntimeError("Ollama not running"),
    )
    def test_organize_error(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        result = runner.invoke(app, ["organize", str(input_dir), str(output_dir)])
        assert result.exit_code == 1
        assert "Ollama not running" in result.output


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------


class TestPreview:
    """Tests for the ``preview`` command."""

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_preview_basic(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result(total=15)

        result = runner.invoke(app, ["preview", str(tmp_path)])
        assert result.exit_code == 0
        assert "15" in result.output
        # FileOrganizer should be instantiated with dry_run=True
        mock_cls.assert_called_once_with(dry_run=True)

    @patch(
        "file_organizer.core.organizer.FileOrganizer",
        side_effect=ValueError("Invalid directory"),
    )
    def test_preview_error(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        result = runner.invoke(app, ["preview", str(tmp_path)])
        assert result.exit_code == 1
        assert "Invalid directory" in result.output
