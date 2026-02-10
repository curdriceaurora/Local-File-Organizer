"""Tests for daemon CLI commands."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from file_organizer.cli.daemon import daemon_app

runner = CliRunner()


class TestDaemonStart:
    """Tests for 'daemon start' command."""

    @patch("file_organizer.daemon.service.DaemonService")
    @patch("file_organizer.daemon.config.DaemonConfig")
    def test_start_foreground(self, mock_config_cls: MagicMock, mock_svc_cls: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc
        mock_svc.start.side_effect = KeyboardInterrupt

        result = runner.invoke(daemon_app, ["start", "--foreground"])
        assert result.exit_code == 0
        mock_svc.start.assert_called_once()

    @patch("file_organizer.daemon.service.DaemonService")
    @patch("file_organizer.daemon.config.DaemonConfig")
    def test_start_background(self, mock_config_cls: MagicMock, mock_svc_cls: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(daemon_app, ["start"])
        assert result.exit_code == 0
        mock_svc.start_background.assert_called_once()

    @patch("file_organizer.daemon.service.DaemonService")
    @patch("file_organizer.daemon.config.DaemonConfig")
    def test_start_with_dry_run(self, mock_config_cls: MagicMock, mock_svc_cls: MagicMock) -> None:
        mock_svc = MagicMock()
        mock_svc_cls.return_value = mock_svc

        result = runner.invoke(daemon_app, [
            "start",
            "--watch-dir", "/tmp/watch",
            "--output-dir", "/tmp/out",
            "--poll-interval", "2.0",
            "--dry-run",
        ])
        assert result.exit_code == 0
        assert "Dry-run" in result.output


class TestDaemonStop:
    """Tests for 'daemon stop' command."""

    @patch("file_organizer.daemon.pid.PidFileManager")
    def test_stop_no_pid_file(self, mock_mgr_cls: MagicMock, tmp_path: Path) -> None:
        # Use a non-existent PID file
        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", tmp_path / "nopid"):
            result = runner.invoke(daemon_app, ["stop"])
        assert result.exit_code == 1

    @patch("file_organizer.cli.daemon.os.kill")
    @patch("file_organizer.daemon.pid.PidFileManager")
    def test_stop_success(self, mock_mgr_cls: MagicMock, mock_kill: MagicMock, tmp_path: Path) -> None:
        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("12345")
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.read_pid.return_value = 12345

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            result = runner.invoke(daemon_app, ["stop"])
        assert result.exit_code == 0
        assert "stopped" in result.output.lower()


class TestDaemonStatus:
    """Tests for 'daemon status' command."""

    @patch("file_organizer.daemon.pid.PidFileManager")
    def test_status_not_running(self, mock_mgr_cls: MagicMock, tmp_path: Path) -> None:
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.is_running.return_value = False

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", tmp_path / "nopid"):
            result = runner.invoke(daemon_app, ["status"])
        assert result.exit_code == 0
        assert "Stopped" in result.output

    @patch("file_organizer.daemon.pid.PidFileManager")
    def test_status_running(self, mock_mgr_cls: MagicMock, tmp_path: Path) -> None:
        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("99999")
        mock_mgr = MagicMock()
        mock_mgr_cls.return_value = mock_mgr
        mock_mgr.is_running.return_value = True
        mock_mgr.read_pid.return_value = 99999

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            result = runner.invoke(daemon_app, ["status"])
        assert result.exit_code == 0
        assert "Running" in result.output


class TestDaemonProcess:
    """Tests for 'daemon process' command."""

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_process_success(self, mock_org_cls: MagicMock) -> None:
        mock_org = MagicMock()
        mock_org_cls.return_value = mock_org

        mock_result = MagicMock()
        mock_result.total_files = 10
        mock_result.processed_files = 8
        mock_result.skipped_files = 1
        mock_result.failed_files = 1
        mock_result.organized_structure = {"Docs": ["a.pdf"], "Imgs": ["b.jpg"]}
        mock_result.errors = [("bad.txt", "Cannot read")]
        mock_org.organize.return_value = mock_result

        result = runner.invoke(daemon_app, ["process", "/tmp/in", "/tmp/out"])
        assert result.exit_code == 0
        assert "10" in result.output

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_process_dry_run(self, mock_org_cls: MagicMock) -> None:
        mock_org = MagicMock()
        mock_org_cls.return_value = mock_org

        mock_result = MagicMock()
        mock_result.total_files = 5
        mock_result.processed_files = 5
        mock_result.skipped_files = 0
        mock_result.failed_files = 0
        mock_result.organized_structure = {}
        mock_result.errors = []
        mock_org.organize.return_value = mock_result

        result = runner.invoke(daemon_app, ["process", "/tmp/in", "/tmp/out", "--dry-run"])
        assert result.exit_code == 0
        assert "Dry-run" in result.output


class TestDaemonHelp:
    """Verify help text renders."""

    def test_daemon_help(self) -> None:
        result = runner.invoke(daemon_app, ["--help"])
        assert result.exit_code == 0
        assert "daemon" in result.output.lower() or "background" in result.output.lower()

    def test_start_help(self) -> None:
        result = runner.invoke(daemon_app, ["start", "--help"])
        assert result.exit_code == 0
        assert "watch-dir" in result.output or "foreground" in result.output

    def test_process_help(self) -> None:
        result = runner.invoke(daemon_app, ["process", "--help"])
        assert result.exit_code == 0
