"""Tests for the dedupe_v2 Typer sub-app."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def mock_detector():
    """Return a mock DuplicateDetector with empty results."""
    detector = MagicMock()
    detector.get_duplicate_groups.return_value = {}
    detector.get_statistics.return_value = {"total_files": 0, "duplicate_files": 0}
    return detector


@pytest.fixture
def mock_detector_with_groups():
    """Return a mock DuplicateDetector with duplicate groups."""
    detector = MagicMock()

    file_meta_1 = MagicMock()
    file_meta_1.path = Path("/tmp/a.txt")
    file_meta_1.size = 1024
    file_meta_1.modified_time = datetime(2025, 1, 1, 12, 0)

    file_meta_2 = MagicMock()
    file_meta_2.path = Path("/tmp/b.txt")
    file_meta_2.size = 1024
    file_meta_2.modified_time = datetime(2025, 1, 2, 12, 0)

    group = MagicMock()
    group.files = [file_meta_1, file_meta_2]
    group.count = 2
    group.total_size = 2048
    group.wasted_space = 1024

    detector.get_duplicate_groups.return_value = {"abc123": group}
    detector.get_statistics.return_value = {"total_files": 10, "duplicate_files": 2}
    return detector


class TestDedupeImports:
    """Test that the module imports correctly."""

    def test_import_dedupe_app(self) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        assert dedupe_app is not None

    def test_registered_in_main(self) -> None:
        from file_organizer.cli.main import app

        # The dedupe sub-app should be registered
        assert app is not None


class TestDedupeScan:
    """Tests for the scan command."""

    def test_scan_no_duplicates(self, tmp_path: Path, mock_detector: MagicMock) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        with patch(
            "file_organizer.cli.dedupe_v2._get_detector",
            return_value=mock_detector,
        ):
            result = runner.invoke(dedupe_app, ["scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "no duplicates" in result.output.lower()

    def test_scan_with_duplicates(
        self, tmp_path: Path, mock_detector_with_groups: MagicMock
    ) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        with patch(
            "file_organizer.cli.dedupe_v2._get_detector",
            return_value=mock_detector_with_groups,
        ):
            result = runner.invoke(dedupe_app, ["scan", str(tmp_path)])
        assert result.exit_code == 0
        assert "1" in result.output  # 1 group

    def test_scan_json_output(self, tmp_path: Path, mock_detector_with_groups: MagicMock) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        with patch(
            "file_organizer.cli.dedupe_v2._get_detector",
            return_value=mock_detector_with_groups,
        ):
            result = runner.invoke(dedupe_app, ["scan", str(tmp_path), "--json"])
        assert result.exit_code == 0
        # Should be valid JSON (somewhere in the output)
        assert "abc123" in result.output


class TestDedupeResolve:
    """Tests for the resolve command."""

    def test_resolve_no_duplicates(self, tmp_path: Path, mock_detector: MagicMock) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        with patch(
            "file_organizer.cli.dedupe_v2._get_detector",
            return_value=mock_detector,
        ):
            result = runner.invoke(dedupe_app, ["resolve", str(tmp_path)])
        assert result.exit_code == 0
        assert "no duplicates" in result.output.lower()

    def test_resolve_dry_run(self, tmp_path: Path, mock_detector_with_groups: MagicMock) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        with patch(
            "file_organizer.cli.dedupe_v2._get_detector",
            return_value=mock_detector_with_groups,
        ):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(tmp_path), "--strategy", "oldest", "--dry-run"],
            )
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()


class TestDedupeReport:
    """Tests for the report command."""

    def test_report_empty(self, tmp_path: Path, mock_detector: MagicMock) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        with patch(
            "file_organizer.cli.dedupe_v2._get_detector",
            return_value=mock_detector,
        ):
            result = runner.invoke(dedupe_app, ["report", str(tmp_path)])
        assert result.exit_code == 0

    def test_report_json(self, tmp_path: Path, mock_detector: MagicMock) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        with patch(
            "file_organizer.cli.dedupe_v2._get_detector",
            return_value=mock_detector,
        ):
            result = runner.invoke(dedupe_app, ["report", str(tmp_path), "--json"])
        assert result.exit_code == 0


class TestFormatSize:
    """Test _format_size helper."""

    def test_bytes(self) -> None:
        from file_organizer.cli.dedupe_v2 import _format_size

        assert _format_size(100) == "100 B"

    def test_kilobytes(self) -> None:
        from file_organizer.cli.dedupe_v2 import _format_size

        assert "KB" in _format_size(2048)

    def test_zero(self) -> None:
        from file_organizer.cli.dedupe_v2 import _format_size

        assert _format_size(0) == "0 B"
