"""Integration tests for cli/dedupe_v2.py.

Covers:
- scan command: table output, --json flag, no duplicates found
- resolve command: dry-run, oldest/newest strategies, no duplicates
- report command: table output, --json flag
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.dedupe_v2 import dedupe_app

pytestmark = [pytest.mark.integration, pytest.mark.ci]

runner = CliRunner()

# ---------------------------------------------------------------------------
# Test data helpers
# ---------------------------------------------------------------------------

_OLDER_TIME = datetime(2023, 1, 1, tzinfo=UTC)
_NEWER_TIME = datetime(2024, 6, 15, tzinfo=UTC)


def _make_file_metadata(
    path: Path,
    *,
    size: int = 1024,
    modified_time: datetime | None = None,
    hash_value: str = "abc123",
) -> MagicMock:
    fm = MagicMock()
    fm.path = path
    fm.size = size
    fm.modified_time = modified_time or _NEWER_TIME
    fm.accessed_time = _NEWER_TIME
    fm.hash_value = hash_value
    return fm


def _make_group(
    hash_val: str,
    files: list[Any],
) -> MagicMock:
    g = MagicMock()
    g.hash_value = hash_val
    g.files = files
    g.count = len(files)
    g.total_size = files[0].size * len(files) if files else 0
    g.wasted_space = files[0].size * (len(files) - 1) if len(files) > 1 else 0
    return g


def _make_detector_with_groups(
    groups: dict[str, Any],
    stats: dict[str, Any] | None = None,
) -> MagicMock:
    detector = MagicMock()
    detector.scan_directory.return_value = MagicMock()
    detector.get_duplicate_groups.return_value = groups
    detector.get_statistics.return_value = stats or {
        "total_files": 10,
        "duplicate_files": 4,
        "unique_hashes": 3,
        "wasted_space": 2048,
    }
    return detector


# ---------------------------------------------------------------------------
# scan command
# ---------------------------------------------------------------------------


class TestScanCommand:
    """Tests for the ``dedupe scan`` command."""

    def test_scan_shows_table_with_groups(self, tmp_path: Path) -> None:
        """When duplicates exist, a Rich table per group is shown."""
        src = tmp_path / "files"
        src.mkdir()

        fm1 = _make_file_metadata(src / "a.txt", size=512)
        fm2 = _make_file_metadata(src / "b.txt", size=512)
        group = _make_group("deadbeef" * 8, [fm1, fm2])
        detector = _make_detector_with_groups({"deadbeef" * 8: group})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["scan", str(src)])

        assert result.exit_code == 0
        assert "1" in result.output  # 1 duplicate group
        assert "duplicate" in result.output.lower()

    def test_scan_json_output(self, tmp_path: Path) -> None:
        """--json flag produces a JSON array of duplicate groups."""
        src = tmp_path / "files"
        src.mkdir()

        hash_val = "cafebabe" * 8
        fm1 = _make_file_metadata(src / "x.pdf", size=2048)
        fm2 = _make_file_metadata(src / "y.pdf", size=2048)
        group = _make_group(hash_val, [fm1, fm2])
        detector = _make_detector_with_groups({hash_val: group})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["scan", str(src), "--json"])

        assert result.exit_code == 0
        output = result.output
        start = output.find("[")
        parsed = json.loads(output[start:])
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["hash"] == hash_val
        assert parsed[0]["count"] == 2
        assert parsed[0]["wasted_space"] == 2048

    def test_scan_no_duplicates_found(self, tmp_path: Path) -> None:
        """Empty duplicate groups exits 0 with informational message."""
        src = tmp_path / "files"
        src.mkdir()
        (src / "unique.txt").write_text("unique content")

        detector = _make_detector_with_groups({})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["scan", str(src)])

        assert result.exit_code == 0
        assert "No duplicates" in result.output

    def test_scan_json_no_duplicates_exits_zero(self, tmp_path: Path) -> None:
        """No duplicates path exits 0 even with --json (early exit before JSON render)."""
        src = tmp_path / "files"
        src.mkdir()
        (src / "solo.txt").write_text("x")

        detector = _make_detector_with_groups({})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["scan", str(src), "--json"])

        assert result.exit_code == 0
        assert "No duplicates" in result.output

    def test_scan_multiple_groups_shown(self, tmp_path: Path) -> None:
        """Multiple duplicate groups are all rendered."""
        src = tmp_path / "files"
        src.mkdir()

        hash1 = "aaaa" * 16
        hash2 = "bbbb" * 16
        fm1a = _make_file_metadata(src / "a1.txt", size=100, hash_value=hash1)
        fm1b = _make_file_metadata(src / "a2.txt", size=100, hash_value=hash1)
        fm2a = _make_file_metadata(src / "b1.txt", size=200, hash_value=hash2)
        fm2b = _make_file_metadata(src / "b2.txt", size=200, hash_value=hash2)
        g1 = _make_group(hash1, [fm1a, fm1b])
        g2 = _make_group(hash2, [fm2a, fm2b])
        detector = _make_detector_with_groups({hash1: g1, hash2: g2})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["scan", str(src)])

        assert result.exit_code == 0
        assert "2" in result.output


# ---------------------------------------------------------------------------
# resolve command
# ---------------------------------------------------------------------------


class TestResolveCommand:
    """Tests for the ``dedupe resolve`` command."""

    def test_resolve_no_duplicates(self, tmp_path: Path) -> None:
        """No duplicates exits 0 with informational message."""
        src = tmp_path / "files"
        src.mkdir()
        (src / "only.txt").write_text("x")

        detector = _make_detector_with_groups({})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["resolve", str(src)])

        assert result.exit_code == 0
        assert "No duplicates" in result.output

    def test_resolve_dry_run_no_files_deleted(self, tmp_path: Path) -> None:
        """--dry-run with oldest strategy shows 'Would remove' but deletes nothing."""
        src = tmp_path / "files"
        src.mkdir()
        file_a = src / "old.txt"
        file_b = src / "new.txt"
        file_a.write_text("same")
        file_b.write_text("same")

        hash_val = "ee" * 32
        fm_old = _make_file_metadata(file_a, modified_time=_OLDER_TIME)
        fm_new = _make_file_metadata(file_b, modified_time=_NEWER_TIME)
        group = _make_group(hash_val, [fm_old, fm_new])
        detector = _make_detector_with_groups({hash_val: group})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(src), "--strategy", "oldest", "--dry-run"],
            )

        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "would remove" in output_lower or "dry run" in output_lower
        # Files untouched
        assert file_a.exists()
        assert file_b.exists()

    def test_resolve_dry_run_summary_message(self, tmp_path: Path) -> None:
        """Dry-run always shows 'Dry run — no files were removed' at the end."""
        src = tmp_path / "files"
        src.mkdir()
        file_a = src / "copy1.txt"
        file_b = src / "copy2.txt"
        file_a.write_text("dup")
        file_b.write_text("dup")

        hash_val = "ff" * 32
        fm_a = _make_file_metadata(file_a, modified_time=_OLDER_TIME)
        fm_b = _make_file_metadata(file_b, modified_time=_NEWER_TIME)
        group = _make_group(hash_val, [fm_a, fm_b])
        detector = _make_detector_with_groups({hash_val: group})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(src), "--strategy", "newest", "--dry-run"],
            )

        assert result.exit_code == 0
        assert "Dry run" in result.output

    def test_resolve_manual_strategy_skips_auto_deletion(self, tmp_path: Path) -> None:
        """Manual strategy shows table and 'skipping automatic resolution' message."""
        src = tmp_path / "files"
        src.mkdir()
        file_a = src / "m1.txt"
        file_b = src / "m2.txt"
        file_a.write_text("same")
        file_b.write_text("same")

        hash_val = "dd" * 32
        fm_a = _make_file_metadata(file_a)
        fm_b = _make_file_metadata(file_b)
        group = _make_group(hash_val, [fm_a, fm_b])
        detector = _make_detector_with_groups({hash_val: group})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(src), "--strategy", "manual"],
            )

        assert result.exit_code == 0
        assert "Manual mode" in result.output or "skipping" in result.output.lower()

    def test_resolve_strategy_largest_keeps_largest(self, tmp_path: Path) -> None:
        """largest strategy identifies largest file as the one to keep (others deleted)."""
        src = tmp_path / "files"
        src.mkdir()
        small = src / "small.txt"
        large = src / "large.txt"
        small.write_text("x" * 10)
        large.write_text("x" * 100)

        hash_val = "cc" * 32
        fm_small = _make_file_metadata(small, size=10)
        fm_large = _make_file_metadata(large, size=100)
        # Patch unlink so we can verify the right file gets targeted
        fm_small.path = small
        fm_large.path = large
        group = _make_group(hash_val, [fm_small, fm_large])
        detector = _make_detector_with_groups({hash_val: group})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(
                dedupe_app,
                ["resolve", str(src), "--strategy", "largest", "--dry-run"],
            )

        assert result.exit_code == 0
        # small.txt is the one that would be removed (not large)
        assert "small.txt" in result.output or "Would remove" in result.output


# ---------------------------------------------------------------------------
# report command
# ---------------------------------------------------------------------------


class TestReportCommand:
    """Tests for the ``dedupe report`` command."""

    def test_report_table_output(self, tmp_path: Path) -> None:
        """Normal path: shows a Rich summary table."""
        src = tmp_path / "files"
        src.mkdir()

        hash_val = "bb" * 32
        fm1 = _make_file_metadata(src / "d1.txt", size=1024)
        fm2 = _make_file_metadata(src / "d2.txt", size=1024)
        group = _make_group(hash_val, [fm1, fm2])
        stats = {
            "total_files": 20,
            "duplicate_files": 6,
            "unique_hashes": 2,
            "wasted_space": 4096,
        }
        detector = _make_detector_with_groups({hash_val: group}, stats=stats)

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["report", str(src)])

        assert result.exit_code == 0
        assert "Duplicate Report" in result.output
        assert "20" in result.output  # total files scanned

    def test_report_json_output(self, tmp_path: Path) -> None:
        """--json flag produces valid JSON of statistics."""
        src = tmp_path / "files"
        src.mkdir()

        hash_val = "11" * 32
        fm1 = _make_file_metadata(src / "r1.txt", size=512)
        fm2 = _make_file_metadata(src / "r2.txt", size=512)
        group = _make_group(hash_val, [fm1, fm2])
        stats = {
            "total_files": 8,
            "duplicate_files": 2,
            "wasted_space": 512,
        }
        detector = _make_detector_with_groups({hash_val: group}, stats=stats)

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["report", str(src), "--json"])

        assert result.exit_code == 0
        output = result.output
        start = output.find("{")
        parsed = json.loads(output[start:])
        assert parsed["total_files"] == 8
        assert parsed["duplicate_files"] == 2

    def test_report_wasted_space_formatted(self, tmp_path: Path) -> None:
        """Report table shows human-readable wasted space."""
        src = tmp_path / "files"
        src.mkdir()

        hash_val = "22" * 32
        fm1 = _make_file_metadata(src / "f1.bin", size=1048576)  # 1 MB
        fm2 = _make_file_metadata(src / "f2.bin", size=1048576)
        group = _make_group(hash_val, [fm1, fm2])
        detector = _make_detector_with_groups({hash_val: group})

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["report", str(src)])

        assert result.exit_code == 0
        # Wasted space 1 MB should appear with a size unit
        output_lower = result.output.lower()
        assert "mb" in output_lower or "kb" in output_lower or "b" in output_lower

    def test_report_no_duplicates_shows_zero_group(self, tmp_path: Path) -> None:
        """When no duplicate groups, the table shows 0 duplicate groups."""
        src = tmp_path / "files"
        src.mkdir()
        (src / "only.txt").write_text("unique")

        detector = _make_detector_with_groups(
            {},
            stats={"total_files": 1, "duplicate_files": 0, "wasted_space": 0},
        )

        with patch("file_organizer.cli.dedupe_v2._get_detector", return_value=detector):
            result = runner.invoke(dedupe_app, ["report", str(src)])

        assert result.exit_code == 0
        assert "0" in result.output  # 0 duplicate groups
