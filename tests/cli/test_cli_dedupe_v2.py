"""Tests for the dedupe v2 CLI sub-app (dedupe_v2.py).

Tests the ``dedupe scan``, ``dedupe resolve``, and ``dedupe report`` commands.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit]

runner = CliRunner()


def _make_file_meta(path: str, size: int = 1024) -> MagicMock:
    """Create a mock file metadata entry."""
    meta = MagicMock()
    meta.path = Path(path)
    meta.size = size
    meta.modified_time = datetime(2025, 1, 15, 10, 30, tzinfo=UTC)
    return meta


def _make_group(files: list[MagicMock]) -> MagicMock:
    """Create a mock duplicate group."""
    group = MagicMock()
    group.files = files
    group.count = len(files)
    group.total_size = sum(f.size for f in files)
    group.wasted_space = sum(f.size for f in files[1:])
    return group


# ---------------------------------------------------------------------------
# dedupe scan
# ---------------------------------------------------------------------------


class TestDedupeScan:
    """Tests for ``dedupe scan``."""

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_no_duplicates(self, mock_get_det: MagicMock, tmp_path: Path) -> None:
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det
        mock_det.get_duplicate_groups.return_value = {}

        result = runner.invoke(app, ["dedupe", "scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "No duplicates" in result.output

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_with_duplicates(self, mock_get_det: MagicMock, tmp_path: Path) -> None:
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det

        files = [
            _make_file_meta(str(tmp_path / "a.txt")),
            _make_file_meta(str(tmp_path / "b.txt")),
        ]
        groups = {"abc123": _make_group(files)}
        mock_det.get_duplicate_groups.return_value = groups

        result = runner.invoke(app, ["dedupe", "scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "1" in result.output  # 1 duplicate group

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_json_output(self, mock_get_det: MagicMock, tmp_path: Path) -> None:
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det

        files = [
            _make_file_meta(str(tmp_path / "a.txt")),
            _make_file_meta(str(tmp_path / "b.txt")),
        ]
        groups = {"abc123": _make_group(files)}
        mock_det.get_duplicate_groups.return_value = groups

        result = runner.invoke(app, ["dedupe", "scan", str(tmp_path), "--json"])
        assert result.exit_code == 0
        assert "abc123" in result.output

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_with_options(self, mock_get_det: MagicMock, tmp_path: Path) -> None:
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det
        mock_det.get_duplicate_groups.return_value = {}

        result = runner.invoke(
            app,
            [
                "dedupe",
                "scan",
                str(tmp_path),
                "--algorithm",
                "md5",
                "--min-size",
                "100",
                "--no-recursive",
            ],
        )
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# dedupe resolve
# ---------------------------------------------------------------------------


class TestDedupeResolve:
    """Tests for ``dedupe resolve``."""

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_resolve_no_duplicates(self, mock_get_det: MagicMock, tmp_path: Path) -> None:
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det
        mock_det.get_duplicate_groups.return_value = {}

        result = runner.invoke(app, ["dedupe", "resolve", str(tmp_path), "--strategy", "oldest"])
        assert result.exit_code == 0
        assert "No duplicates" in result.output

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_resolve_dry_run(self, mock_get_det: MagicMock, tmp_path: Path) -> None:
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det

        files = [
            _make_file_meta(str(tmp_path / "old.txt"), size=100),
            _make_file_meta(str(tmp_path / "new.txt"), size=100),
        ]
        groups = {"abc": _make_group(files)}
        mock_det.get_duplicate_groups.return_value = groups

        result = runner.invoke(
            app,
            [
                "dedupe",
                "resolve",
                str(tmp_path),
                "--strategy",
                "oldest",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Dry run" in result.output or "dry run" in result.output.lower()

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_resolve_manual_strategy(self, mock_get_det: MagicMock, tmp_path: Path) -> None:
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det

        files = [
            _make_file_meta(str(tmp_path / "a.txt")),
            _make_file_meta(str(tmp_path / "b.txt")),
        ]
        groups = {"abc": _make_group(files)}
        mock_det.get_duplicate_groups.return_value = groups

        result = runner.invoke(
            app,
            ["dedupe", "resolve", str(tmp_path), "--strategy", "manual"],
        )
        assert result.exit_code == 0
        assert "Manual" in result.output or "manual" in result.output.lower()


# ---------------------------------------------------------------------------
# dedupe report
# ---------------------------------------------------------------------------


class TestDedupeReport:
    """Tests for ``dedupe report``."""

    @patch("file_organizer.services.deduplication.detector.ScanOptions")
    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_report_table(
        self,
        mock_get_det: MagicMock,
        mock_scan_opts: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det
        mock_det.get_statistics.return_value = {
            "total_files": 100,
            "duplicate_files": 10,
        }
        files = [
            _make_file_meta(str(tmp_path / "a.txt")),
            _make_file_meta(str(tmp_path / "b.txt")),
        ]
        mock_det.get_duplicate_groups.return_value = {"h1": _make_group(files)}

        result = runner.invoke(app, ["dedupe", "report", str(tmp_path)])
        assert result.exit_code == 0
        assert "Duplicate Report" in result.output
        assert "100" in result.output

    @patch("file_organizer.services.deduplication.detector.ScanOptions")
    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_report_json(
        self,
        mock_get_det: MagicMock,
        mock_scan_opts: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det
        mock_det.get_statistics.return_value = {
            "total_files": 50,
            "duplicate_files": 5,
        }
        mock_det.get_duplicate_groups.return_value = {}

        result = runner.invoke(app, ["dedupe", "report", str(tmp_path), "--json"])
        assert result.exit_code == 0
        assert "50" in result.output
