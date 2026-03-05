"""Coverage tests for file_organizer.cli.dedupe_v2 — uncovered lines 28-236."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

runner = CliRunner()


@dataclass
class _FakeFileMeta:
    path: Path
    size: int = 1024
    modified_time: datetime = field(default_factory=lambda: datetime(2024, 1, 1, tzinfo=UTC))


@dataclass
class _FakeDupGroup:
    count: int = 2
    total_size: int = 2048
    wasted_space: int = 1024
    files: list = field(default_factory=list)


class TestDedupeHelpers:
    """Covers _build_scan_options and _format_size."""

    def test_format_size_bytes(self) -> None:
        from file_organizer.cli.dedupe_v2 import _format_size

        assert _format_size(500) == "500 B"

    def test_format_size_kb(self) -> None:
        from file_organizer.cli.dedupe_v2 import _format_size

        assert "KB" in _format_size(2048)

    def test_format_size_mb(self) -> None:
        from file_organizer.cli.dedupe_v2 import _format_size

        assert "MB" in _format_size(2 * 1024 * 1024)

    def test_format_size_gb(self) -> None:
        from file_organizer.cli.dedupe_v2 import _format_size

        assert "GB" in _format_size(2 * 1024**3)

    def test_format_size_tb(self) -> None:
        from file_organizer.cli.dedupe_v2 import _format_size

        assert "TB" in _format_size(2 * 1024**4)

    def test_format_size_pb(self) -> None:
        from file_organizer.cli.dedupe_v2 import _format_size

        assert "PB" in _format_size(2 * 1024**5)


class TestDedupeScan:
    """Covers scan command."""

    def test_scan_no_duplicates(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = {}

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(dedupe_app, ["scan", str(tmp_path)])

        assert "No duplicates" in result.output

    def test_scan_with_duplicates_json(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        group = _FakeDupGroup(
            files=[
                _FakeFileMeta(path=tmp_path / "a.txt"),
                _FakeFileMeta(path=tmp_path / "b.txt"),
            ]
        )
        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = {"abc123": group}

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(dedupe_app, ["scan", str(tmp_path), "--json"])

        assert result.exit_code == 0

    def test_scan_with_duplicates_table(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        group = _FakeDupGroup(
            files=[
                _FakeFileMeta(path=tmp_path / "a.txt"),
                _FakeFileMeta(path=tmp_path / "b.txt"),
            ]
        )
        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = {"abc123": group}

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(dedupe_app, ["scan", str(tmp_path)])

        assert result.exit_code == 0
        assert "duplicate groups" in result.output.lower() or "1" in result.output


class TestDedupeResolve:
    """Covers resolve command."""

    def _make_groups(self, tmp_path: Path) -> dict:
        f1 = _FakeFileMeta(
            path=tmp_path / "a.txt",
            modified_time=datetime(2024, 1, 1, tzinfo=UTC),
            size=100,
        )
        f2 = _FakeFileMeta(
            path=tmp_path / "b.txt",
            modified_time=datetime(2024, 6, 1, tzinfo=UTC),
            size=200,
        )
        group = _FakeDupGroup(files=[f1, f2])
        return {"hash1": group}

    def test_resolve_no_duplicates(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = {}

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(dedupe_app, ["resolve", str(tmp_path)])

        assert "No duplicates" in result.output

    def test_resolve_oldest_dry_run(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = self._make_groups(tmp_path)

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(tmp_path), "--strategy", "oldest", "--dry-run"],
            )

        assert "Dry run" in result.output or "Would remove" in result.output

    def test_resolve_newest(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = self._make_groups(tmp_path)

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(tmp_path), "--strategy", "newest", "--dry-run"],
            )

        assert result.exit_code == 0

    def test_resolve_largest(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = self._make_groups(tmp_path)

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(tmp_path), "--strategy", "largest", "--dry-run"],
            )

        assert result.exit_code == 0

    def test_resolve_smallest(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = self._make_groups(tmp_path)

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(tmp_path), "--strategy", "smallest", "--dry-run"],
            )

        assert result.exit_code == 0

    def test_resolve_manual(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = self._make_groups(tmp_path)

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(tmp_path), "--strategy", "manual"],
            )

        assert result.exit_code == 0
        assert "Manual mode" in result.output


class TestDedupeReport:
    """Covers report command."""

    def test_report_json(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = {}
        mock_detector.get_statistics.return_value = {"total_files": 10}

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(dedupe_app, ["report", str(tmp_path), "--json"])

        assert result.exit_code == 0

    def test_report_table(self, tmp_path: Path) -> None:
        from file_organizer.cli.dedupe_v2 import dedupe_app

        group = _FakeDupGroup(wasted_space=512)
        mock_detector = MagicMock()
        mock_detector.get_duplicate_groups.return_value = {"h1": group}
        mock_detector.get_statistics.return_value = {
            "total_files": 10,
            "duplicate_files": 2,
        }

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=mock_detector):
            result = runner.invoke(dedupe_app, ["report", str(tmp_path)])

        assert result.exit_code == 0
        assert "Duplicate Report" in result.output
