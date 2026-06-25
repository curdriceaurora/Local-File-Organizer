"""Smoke tests for high-traffic CLI commands.

Markers: smoke + ci + unit. Runtime target: <30s.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.smoke, pytest.mark.ci, pytest.mark.unit]
runner = CliRunner()
_SETUP_PATCH = "file_organizer.cli.organize._check_setup_completed"


class TestOrganizeSmoke:
    """fo organize --dry-run exits 0 and reports processed count."""

    # FileOrganizer is lazy-imported inside organize(); patching at definition
    # site because cli.organize holds no module-level reference to the class.
    # _SETUP_PATCH uses new= so its mock is not injected as a parameter (PT019).
    @patch("file_organizer.core.organizer.FileOrganizer")
    @patch(_SETUP_PATCH, new=MagicMock(return_value=True))
    def test_organize_dry_run_exits_zero(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()
        for name in ("a.txt", "b.md", "c.csv"):
            (input_dir / name).write_text("x")

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        result_obj = MagicMock()
        result_obj.total_files = 3
        result_obj.processed_files = 3
        result_obj.skipped_files = 0
        result_obj.failed_files = 0
        mock_org.organize.return_value = result_obj

        result = runner.invoke(
            app,
            ["organize", str(input_dir), str(output_dir), "--dry-run"],
        )

        assert result.exit_code == 0, result.output
        mock_cls.assert_called_once_with(
            dry_run=True,
            parallel_workers=None,
            prefetch_depth=2,
            enable_vision=True,
            no_prefetch=False,
            transcribe_audio=False,
            max_transcribe_seconds=600.0,
        )


class TestSearchSmoke:
    """fo search glob exits 0 and names at least one match."""

    def test_search_glob_exits_zero(self, tmp_path: Path) -> None:
        (tmp_path / "report.txt").write_text("hello")
        (tmp_path / "notes.txt").write_text("world")

        result = runner.invoke(app, ["search", "*.txt", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert "report.txt" in result.output or "notes.txt" in result.output


class TestDedupeScanSmoke:
    """fo dedupe scan exits 0 and reports no duplicates."""

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_dedupe_scan_no_duplicates(self, mock_get_detector: MagicMock, tmp_path: Path) -> None:
        mock_det = MagicMock()
        mock_get_detector.return_value = mock_det
        mock_det.get_duplicate_groups.return_value = {}

        result = runner.invoke(app, ["dedupe", "scan", str(tmp_path)])

        assert result.exit_code == 0, result.output
        assert "No duplicates" in result.output
        mock_det.scan_directory.assert_called_once_with(tmp_path, ANY)


class TestCopilotStatusSmoke:
    """fo copilot status exits 0 and prints ready (Ollama optional)."""

    def test_copilot_status_exits_zero(self) -> None:
        result = runner.invoke(app, ["copilot", "status"])

        assert result.exit_code == 0, result.output
        assert "Copilot" in result.output
        assert "ready" in result.output
