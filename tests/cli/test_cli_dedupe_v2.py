"""Tests for file_organizer.cli.dedupe_v2 module.

Tests the modern Typer sub-app for duplicate detection:
- scan: Scan directory for duplicates
- report: Generate duplicate report
- resolve: Resolve duplicate files
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.dedupe_v2 import dedupe_app

runner = CliRunner()

pytestmark = [pytest.mark.unit]


class TestDedupeScan:
    """Tests for dedupe scan command."""

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_basic(self, mock_detector_fn, tmp_path):
        """Test basic scan operation."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {
            "group1": MagicMock(count=2, total_size=1000, wasted_space=500)
        }
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(dedupe_app, ["scan", str(test_dir)])

        assert result.exit_code == 0
        mock_detector.scan.assert_called_once()

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_recursive(self, mock_detector_fn, tmp_path):
        """Test scan with recursive flag."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(
            dedupe_app, ["scan", str(test_dir), "--recursive"]
        )

        assert result.exit_code == 0
        # Verify recursive option was passed
        call_kwargs = mock_detector.scan.call_args[1]
        assert call_kwargs.get("scan_options").recursive is True

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_with_algorithm(self, mock_detector_fn, tmp_path):
        """Test scan with specific algorithm."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(
            dedupe_app, ["scan", str(test_dir), "--algorithm", "md5"]
        )

        assert result.exit_code == 0

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_with_file_size_filters(self, mock_detector_fn, tmp_path):
        """Test scan with min/max file size filters."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(
            dedupe_app,
            [
                "scan",
                str(test_dir),
                "--min-size",
                "1000",
                "--max-size",
                "1000000",
            ],
        )

        assert result.exit_code == 0

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_json_output(self, mock_detector_fn, tmp_path):
        """Test scan with JSON output."""
        mock_detector = MagicMock()
        group = MagicMock()
        group.count = 2
        group.total_size = 1000
        group.wasted_space = 500
        group.files = []
        mock_detector.scan.return_value = {"hash1": group}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(
            dedupe_app, ["scan", str(test_dir), "--json"]
        )

        assert result.exit_code == 0

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_with_include_pattern(self, mock_detector_fn, tmp_path):
        """Test scan with include file patterns."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(
            dedupe_app,
            [
                "scan",
                str(test_dir),
                "--include",
                "*.jpg,*.png",
            ],
        )

        assert result.exit_code == 0

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_with_exclude_pattern(self, mock_detector_fn, tmp_path):
        """Test scan with exclude file patterns."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(
            dedupe_app,
            [
                "scan",
                str(test_dir),
                "--exclude",
                "*.tmp,*.bak",
            ],
        )

        assert result.exit_code == 0

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_no_duplicates(self, mock_detector_fn, tmp_path):
        """Test scan with no duplicates found."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(dedupe_app, ["scan", str(test_dir)])

        assert result.exit_code == 0


class TestDedupeReport:
    """Tests for dedupe report command."""

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_report_basic(self, mock_detector_fn, tmp_path):
        """Test basic report generation."""
        mock_detector = MagicMock()
        group = MagicMock()
        group.count = 3
        group.total_size = 3000
        group.wasted_space = 2000
        group.files = []
        mock_detector.scan.return_value = {"hash1": group}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(dedupe_app, ["report", str(test_dir)])

        assert result.exit_code == 0
        mock_detector.scan.assert_called_once()

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_report_shows_wasted_space(self, mock_detector_fn, tmp_path):
        """Test report displays wasted space."""
        mock_detector = MagicMock()
        group = MagicMock()
        group.count = 5
        group.total_size = 5000
        group.wasted_space = 4000
        group.files = []
        mock_detector.scan.return_value = {"hash1": group}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(dedupe_app, ["report", str(test_dir)])

        assert result.exit_code == 0


class TestDedupeResolve:
    """Tests for dedupe resolve command."""

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_resolve_basic(self, mock_detector_fn, tmp_path):
        """Test basic resolve operation."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {}
        mock_detector.resolve.return_value = {"removed": 2, "bytes_freed": 2000}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(dedupe_app, ["resolve", str(test_dir)])

        assert result.exit_code == 0
        mock_detector.resolve.assert_called_once()

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_resolve_dry_run(self, mock_detector_fn, tmp_path):
        """Test resolve with dry-run flag."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {}
        mock_detector.resolve.return_value = {"removed": 0, "bytes_freed": 0}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(
            dedupe_app, ["resolve", str(test_dir), "--dry-run"]
        )

        assert result.exit_code == 0

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_resolve_with_strategy(self, mock_detector_fn, tmp_path):
        """Test resolve with deletion strategy."""
        mock_detector = MagicMock()
        mock_detector.scan.return_value = {}
        mock_detector.resolve.return_value = {}
        mock_detector_fn.return_value = mock_detector

        test_dir = tmp_path / "test"
        test_dir.mkdir()

        result = runner.invoke(
            dedupe_app, ["resolve", str(test_dir), "--strategy", "keep-newest"]
        )

        assert result.exit_code == 0


class TestBuildScanOptions:
    """Tests for _build_scan_options helper."""

    def test_scan_options_basic(self):
        """Test building basic scan options."""
        from file_organizer.cli.dedupe_v2 import _build_scan_options

        opts = _build_scan_options(
            Path("/test"),
            "md5",
            recursive=True,
            min_size=1000,
            max_size=None,
            include=None,
            exclude=None,
        )

        assert opts.algorithm == "md5"
        assert opts.recursive is True
        assert opts.min_file_size == 1000

    def test_scan_options_with_patterns(self):
        """Test building scan options with patterns."""
        from file_organizer.cli.dedupe_v2 import _build_scan_options

        opts = _build_scan_options(
            Path("/test"),
            "sha256",
            recursive=False,
            min_size=0,
            max_size=1000000,
            include="*.jpg,*.png",
            exclude="*.tmp",
        )

        assert opts.algorithm == "sha256"
        assert opts.file_patterns == ["*.jpg", "*.png"]
        assert opts.exclude_patterns == ["*.tmp"]


class TestDisplayGroupsTable:
    """Tests for _display_groups_table helper."""

    def test_display_groups_json_format(self):
        """Test displaying groups in JSON format."""
        from file_organizer.cli.dedupe_v2 import _display_groups_table

        group = MagicMock()
        group.count = 2
        group.total_size = 2000
        group.wasted_space = 1000
        group.files = []

        groups = {"hash1": group}

        # Should not raise
        _display_groups_table(groups, json_output=True)

    def test_display_groups_table_format(self):
        """Test displaying groups in table format."""
        from file_organizer.cli.dedupe_v2 import _display_groups_table

        group = MagicMock()
        group.count = 3
        group.total_size = 3000
        group.wasted_space = 2000
        file_obj = MagicMock()
        file_obj.path = Path("/path/to/file")
        group.files = [file_obj]

        groups = {"abcdef": group}

        # Should not raise
        _display_groups_table(groups, json_output=False)
