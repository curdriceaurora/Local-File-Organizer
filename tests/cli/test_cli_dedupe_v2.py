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

        result = runner.invoke(app, ["dedupe", "scan", str(tmp_path), "--format", "json"])
        assert result.exit_code == 0
        assert "abc123" in result.output
        # Envelope is valid JSON with the documented schema
        import json as _json

        envelope = _json.loads(result.output)
        assert envelope["version"] == 1
        assert envelope["command"] == "scan"
        assert len(envelope["groups"]) == 1
        assert envelope["groups"][0]["hash"] == "abc123"

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
        # Pin that the patched dependency is what the code consulted.
        mock_scan_opts.assert_called()

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

        result = runner.invoke(app, ["dedupe", "report", str(tmp_path), "--format", "json"])
        assert result.exit_code == 0
        assert "50" in result.output
        import json as _json

        envelope = _json.loads(result.output)
        assert envelope["version"] == 1
        assert envelope["command"] == "report"
        assert envelope["summary"]["total_files"] == 50
        assert envelope["summary"]["duplicate_files"] == 5
        # Pin that the patched dependency is what the code consulted.
        mock_scan_opts.assert_called()


# ---------------------------------------------------------------------------
# --include-hidden opt-in (#170)
# ---------------------------------------------------------------------------


@pytest.mark.ci
@pytest.mark.integration
class TestDedupeIncludeHidden:
    """#170: ``--include-hidden`` opts into dotfile / hidden-dir traversal.

    Default behaviour keeps credential-bearing paths (``.env``, ``.ssh/*``)
    out of the dedupe hash index so ``dedupe resolve`` can't delete them by
    accident. These tests verify the flag plumbs from the CLI into
    ``ScanOptions.include_hidden``, and that ``resolve --include-hidden``
    prompts for an explicit confirmation before touching hidden files.
    """

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_default_sets_include_hidden_false(
        self, mock_get_det: MagicMock, tmp_path: Path
    ) -> None:
        """Without the flag, the ScanOptions handed to the detector must
        have ``include_hidden=False``."""
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det
        mock_det.get_duplicate_groups.return_value = {}

        result = runner.invoke(app, ["dedupe", "scan", str(tmp_path)])
        assert result.exit_code == 0
        mock_det.scan_directory.assert_called_once()
        options = mock_det.scan_directory.call_args[0][1]
        assert options.include_hidden is False

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_scan_with_include_hidden_flag(self, mock_get_det: MagicMock, tmp_path: Path) -> None:
        """``scan --include-hidden`` → ``ScanOptions.include_hidden=True``."""
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det
        mock_det.get_duplicate_groups.return_value = {}

        result = runner.invoke(app, ["dedupe", "scan", str(tmp_path), "--include-hidden"])
        assert result.exit_code == 0
        options = mock_det.scan_directory.call_args[0][1]
        assert options.include_hidden is True

    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_report_with_include_hidden_flag(self, mock_get_det: MagicMock, tmp_path: Path) -> None:
        """``report --include-hidden`` plumbs through ScanOptions."""
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det
        mock_det.get_statistics.return_value = {"total_files": 0, "duplicate_files": 0}
        mock_det.get_duplicate_groups.return_value = {}

        result = runner.invoke(app, ["dedupe", "report", str(tmp_path), "--include-hidden"])
        assert result.exit_code == 0
        options = mock_det.scan_directory.call_args[0][1]
        assert options.include_hidden is True

    @patch("file_organizer.cli.dedupe_v2.confirm_action")
    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_resolve_include_hidden_prompts_for_confirmation(
        self,
        mock_get_det: MagicMock,
        mock_confirm: MagicMock,
        tmp_path: Path,
    ) -> None:
        """``resolve --include-hidden`` must prompt before deleting hidden
        files, with a message explicitly mentioning credential risk.
        """
        mock_confirm.return_value = False  # user declines → bail out
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det

        result = runner.invoke(
            app,
            [
                "dedupe",
                "resolve",
                str(tmp_path),
                "--strategy",
                "oldest",
                "--include-hidden",
            ],
        )

        # Exactly one prompt — catches accidental double-prompting regressions.
        mock_confirm.assert_called_once()
        message = mock_confirm.call_args[0][0]
        assert "hidden" in message.lower()
        assert "credential" in message.lower() or "sensitive" in message.lower()
        # Declined → command exits before scanning; detector.scan_directory
        # must NOT be called. Assert the factory too: without this, the
        # scan_directory check passes trivially because the code never
        # received this detector in the first place.
        mock_get_det.assert_not_called()
        mock_det.scan_directory.assert_not_called()
        # Non-zero exit so shell scripts (`&&` chains, CI gates) can
        # distinguish user-cancellation from "no duplicates found".
        assert result.exit_code == 1

    @patch("file_organizer.cli.dedupe_v2.confirm_action")
    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_resolve_without_include_hidden_skips_prompt(
        self,
        mock_get_det: MagicMock,
        mock_confirm: MagicMock,
        tmp_path: Path,
    ) -> None:
        """Default ``resolve`` (no ``--include-hidden``) over a non-hidden
        root must NOT invoke the hidden-file confirmation.
        """
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det
        mock_det.get_duplicate_groups.return_value = {}

        result = runner.invoke(app, ["dedupe", "resolve", str(tmp_path), "--strategy", "oldest"])
        assert result.exit_code == 0
        mock_confirm.assert_not_called()

    @patch("file_organizer.cli.dedupe_v2.confirm_action")
    @patch("file_organizer.cli.dedupe_v2._get_detector")
    def test_resolve_hidden_root_triggers_prompt_without_flag(
        self,
        mock_get_det: MagicMock,
        mock_confirm: MagicMock,
        tmp_path: Path,
    ) -> None:
        """codex P1: ``fo dedupe resolve ~/.ssh --strategy oldest`` traverses
        the scan root even without ``--include-hidden`` — ``safe_walk``'s
        hidden filter is relative to root. The confirmation gate must fire
        based on whether hidden files will actually be scanned, not just the
        flag. A scan root whose path contains a dot-prefixed component
        (``.ssh``) qualifies.
        """
        hidden_root = tmp_path / ".ssh"
        hidden_root.mkdir()
        mock_confirm.return_value = False  # decline
        mock_det = MagicMock()
        mock_get_det.return_value = mock_det

        result = runner.invoke(app, ["dedupe", "resolve", str(hidden_root), "--strategy", "oldest"])

        mock_confirm.assert_called_once()
        # The detector is never even constructed once the user declines.
        mock_get_det.assert_not_called()
        mock_det.scan_directory.assert_not_called()
        assert result.exit_code == 1
