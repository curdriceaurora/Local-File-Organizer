"""Tests for the daemon CLI sub-app (daemon.py).

Tests ``daemon start``, ``stop``, ``status``, ``watch``, and ``process`` commands.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app
from file_organizer.daemon.pid import PidRecord

pytestmark = [pytest.mark.unit, pytest.mark.integration]

runner = CliRunner()


# ---------------------------------------------------------------------------
# daemon start
# ---------------------------------------------------------------------------


class TestDaemonStart:
    """Tests for ``daemon start``."""

    @patch("file_organizer.daemon.service.DaemonService")
    @patch("file_organizer.daemon.config.DaemonConfig")
    def test_start_foreground(
        self, mock_config_cls: MagicMock, mock_svc_cls: MagicMock, tmp_path: Path
    ) -> None:
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc
        # Simulate immediate return (no blocking)
        mock_svc.start.return_value = None

        result = runner.invoke(
            app,
            [
                "daemon",
                "start",
                "--watch-dir",
                str(tmp_path),
                "--foreground",
            ],
        )
        assert result.exit_code == 0
        assert "foreground" in result.output.lower()
        mock_svc.start.assert_called_once()

    @patch("file_organizer.daemon.service.DaemonService")
    @patch("file_organizer.daemon.config.DaemonConfig")
    def test_start_background(
        self, mock_config_cls: MagicMock, mock_svc_cls: MagicMock, tmp_path: Path
    ) -> None:
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(
            app,
            ["daemon", "start", "--watch-dir", str(tmp_path)],
        )
        assert result.exit_code == 0
        assert "background" in result.output.lower()
        mock_svc.start_background.assert_called_once()

    @patch("file_organizer.daemon.service.DaemonService")
    @patch("file_organizer.daemon.config.DaemonConfig")
    def test_start_dry_run(
        self, mock_config_cls: MagicMock, mock_svc_cls: MagicMock, tmp_path: Path
    ) -> None:
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(
            app,
            ["daemon", "start", "--watch-dir", str(tmp_path), "--dry-run"],
        )
        assert result.exit_code == 0
        assert "dry-run" in result.output.lower() or "Dry-run" in result.output


# ---------------------------------------------------------------------------
# daemon stop
# ---------------------------------------------------------------------------


class TestDaemonStop:
    """Tests for ``daemon stop``."""

    @patch("file_organizer.cli.daemon._DEFAULT_PID_FILE")
    @patch("file_organizer.daemon.pid.PidFileManager")
    def test_stop_no_pid_file(self, mock_pid_cls: MagicMock, mock_pid_file: MagicMock) -> None:
        mock_pid_file.exists.return_value = False

        result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 1
        assert "No PID file" in result.output or "not be running" in result.output

    @patch("file_organizer.cli.daemon.os.kill")
    @patch("file_organizer.cli.daemon._DEFAULT_PID_FILE")
    @patch("file_organizer.daemon.pid.PidFileManager")
    def test_stop_success(
        self,
        mock_pid_cls: MagicMock,
        mock_pid_file: MagicMock,
        mock_kill: MagicMock,
    ) -> None:
        mock_pid_file.exists.return_value = True
        mock_mgr = MagicMock()
        mock_pid_cls.return_value = mock_mgr
        mock_mgr.read_pid_record.return_value = PidRecord(pid=12345, create_time=None)

        result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0
        assert "stopped" in result.output.lower()

    @patch("file_organizer.cli.daemon.os.kill", side_effect=ProcessLookupError)
    @patch("file_organizer.cli.daemon._DEFAULT_PID_FILE")
    @patch("file_organizer.daemon.pid.PidFileManager")
    def test_stop_process_not_found(
        self,
        mock_pid_cls: MagicMock,
        mock_pid_file: MagicMock,
        mock_kill: MagicMock,
    ) -> None:
        mock_pid_file.exists.return_value = True
        mock_mgr = MagicMock()
        mock_pid_cls.return_value = mock_mgr
        mock_mgr.read_pid_record.return_value = PidRecord(pid=99999, create_time=None)

        result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


# ---------------------------------------------------------------------------
# daemon status
# ---------------------------------------------------------------------------


class TestDaemonStatus:
    """Tests for ``daemon status``."""

    @patch("file_organizer.cli.daemon._DEFAULT_PID_FILE")
    @patch("file_organizer.daemon.pid.PidFileManager")
    def test_status_running(self, mock_pid_cls: MagicMock, mock_pid_file: MagicMock) -> None:
        mock_pid_file.exists.return_value = True
        mock_mgr = MagicMock()
        mock_pid_cls.return_value = mock_mgr
        mock_mgr.is_running.return_value = True
        mock_mgr.read_pid_record.return_value = PidRecord(pid=12345, create_time=None)

        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        assert "Running" in result.output

    @patch("file_organizer.cli.daemon._DEFAULT_PID_FILE")
    @patch("file_organizer.daemon.pid.PidFileManager")
    def test_status_stopped(self, mock_pid_cls: MagicMock, mock_pid_file: MagicMock) -> None:
        mock_pid_file.exists.return_value = False
        mock_mgr = MagicMock()
        mock_pid_cls.return_value = mock_mgr
        mock_mgr.is_running.return_value = False

        result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        assert "Stopped" in result.output


# ---------------------------------------------------------------------------
# daemon process
# ---------------------------------------------------------------------------


class TestDaemonProcess:
    """Tests for ``daemon process``."""

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_process_success(self, mock_org_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_org_cls.return_value = mock_org
        mock_result = MagicMock()
        mock_result.total_files = 10
        mock_result.processed_files = 8
        mock_result.skipped_files = 1
        mock_result.failed_files = 1
        mock_result.organized_structure = {"docs": [], "images": []}
        mock_result.errors = []
        mock_org.organize.return_value = mock_result

        result = runner.invoke(app, ["daemon", "process", str(input_dir), str(output_dir)])
        assert result.exit_code == 0
        assert "10" in result.output
        assert "8" in result.output

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_process_with_errors(self, mock_org_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_org_cls.return_value = mock_org
        mock_result = MagicMock()
        mock_result.total_files = 5
        mock_result.processed_files = 3
        mock_result.skipped_files = 0
        mock_result.failed_files = 2
        mock_result.organized_structure = {}
        mock_result.errors = [("file1.txt", "read error"), ("file2.pdf", "corrupt")]
        mock_org.organize.return_value = mock_result

        result = runner.invoke(app, ["daemon", "process", str(input_dir), str(output_dir)])
        assert result.exit_code == 0
        assert "Errors" in result.output
        assert "file1.txt" in result.output

    @patch(
        "file_organizer.core.organizer.FileOrganizer",
        side_effect=RuntimeError("Model unavailable"),
    )
    def test_process_exception(self, mock_org_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        result = runner.invoke(app, ["daemon", "process", str(input_dir), str(output_dir)])
        assert result.exit_code == 1
        assert "Model unavailable" in result.output


class TestDaemonWatch:
    """Tests for ``fo daemon watch`` — the polling loop that D#167 left
    uncovered when the legacy watch entry point was removed.
    """

    @patch("file_organizer.watcher.monitor.FileMonitor")
    @patch("file_organizer.watcher.config.WatcherConfig")
    def test_watch_prints_events_then_exits_on_ctrl_c(
        self, mock_config_cls: MagicMock, mock_monitor_cls: MagicMock, tmp_path: Path
    ) -> None:
        watch_dir = tmp_path / "watched"
        watch_dir.mkdir()

        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor

        evt = MagicMock()
        evt.event_type = "created"
        evt.path = str(watch_dir / "new.txt")
        # First poll yields an event; second poll raises KeyboardInterrupt
        # so the command exits cleanly (that's the documented stop mechanism).
        mock_monitor.get_events_blocking.side_effect = [[evt], KeyboardInterrupt()]

        result = runner.invoke(app, ["daemon", "watch", str(watch_dir)])
        assert result.exit_code == 0
        # Rich wraps long paths at the CliRunner terminal width — normalize
        # line breaks before asserting file-name substrings so the test
        # passes regardless of the platform's reported width.
        normalized_output = result.output.replace("\n", "")
        assert "Watching" in result.output
        assert "new.txt" in normalized_output
        assert "Stopped watching" in result.output
        mock_monitor.start.assert_called_once()
        mock_monitor.stop.assert_called_once()

    @patch("file_organizer.watcher.monitor.FileMonitor")
    @patch("file_organizer.watcher.config.WatcherConfig")
    def test_watch_uses_event_src_path_fallback_when_path_missing(
        self, mock_config_cls: MagicMock, mock_monitor_cls: MagicMock, tmp_path: Path
    ) -> None:
        watch_dir = tmp_path / "watched"
        watch_dir.mkdir()

        mock_monitor = MagicMock()
        mock_monitor_cls.return_value = mock_monitor

        class _EventNoPath:
            event_type = "modified"
            src_path = str(watch_dir / "fallback.txt")

        mock_monitor.get_events_blocking.side_effect = [
            [_EventNoPath()],
            KeyboardInterrupt(),
        ]

        result = runner.invoke(app, ["daemon", "watch", str(watch_dir)])
        assert result.exit_code == 0
        # Rich wraps long paths at the terminal width that CliRunner exposes,
        # which can split "fallback.txt" across a newline on narrow Linux CI
        # runners. Normalize line breaks before matching so the assertion is
        # about *content*, not Rich's layout.
        normalized_output = result.output.replace("\n", "")
        assert "fallback.txt" in normalized_output
