"""Tests for file_organizer.cli.daemon module.

Tests the daemon control CLI commands:
- start: Start the background file organization daemon
- stop: Stop the running daemon
- status: Show daemon status
- watch: Monitor a directory for file events
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()

pytestmark = [pytest.mark.unit]


class TestDaemonStart:
    """Tests for daemon start command."""

    @patch("file_organizer.cli.daemon.DaemonService")
    def test_start_foreground(self, mock_service_cls, tmp_path):
        """Test starting daemon in foreground mode."""
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        result = runner.invoke(
            app,
            ["daemon", "start", "--watch-dir", str(watch_dir), "--foreground"],
        )

        assert result.exit_code == 0
        assert "Starting daemon" in result.stdout
        mock_service.start.assert_called_once()

    @patch("file_organizer.cli.daemon.DaemonService")
    def test_start_background(self, mock_service_cls, tmp_path):
        """Test starting daemon in background mode."""
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        result = runner.invoke(
            app,
            ["daemon", "start", "--watch-dir", str(watch_dir)],
        )

        assert result.exit_code == 0
        assert "Starting daemon" in result.stdout
        mock_service.start_background.assert_called_once()

    @patch("file_organizer.cli.daemon.DaemonService")
    def test_start_with_output_dir(self, mock_service_cls, tmp_path):
        """Test starting daemon with output directory option."""
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        watch_dir = tmp_path / "watch"
        output_dir = tmp_path / "output"
        watch_dir.mkdir()
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "start",
                "--watch-dir",
                str(watch_dir),
                "--output-dir",
                str(output_dir),
                "--foreground",
            ],
        )

        assert result.exit_code == 0
        mock_service.start.assert_called_once()

    @patch("file_organizer.cli.daemon.DaemonService")
    def test_start_with_dry_run(self, mock_service_cls, tmp_path):
        """Test starting daemon with dry-run flag."""
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        result = runner.invoke(
            app,
            ["daemon", "start", "--watch-dir", str(watch_dir), "--dry-run", "--foreground"],
        )

        assert result.exit_code == 0
        assert "Dry-run mode" in result.stdout
        mock_service.start.assert_called_once()

    @patch("file_organizer.cli.daemon.DaemonService")
    def test_start_with_poll_interval(self, mock_service_cls, tmp_path):
        """Test starting daemon with custom poll interval."""
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "start",
                "--watch-dir",
                str(watch_dir),
                "--poll-interval",
                "2.5",
                "--foreground",
            ],
        )

        assert result.exit_code == 0
        mock_service.start.assert_called_once()

    @patch("file_organizer.cli.daemon.DaemonService")
    def test_start_keyboard_interrupt(self, mock_service_cls, tmp_path):
        """Test daemon handles keyboard interrupt gracefully."""
        mock_service = MagicMock()
        mock_service.start.side_effect = KeyboardInterrupt()
        mock_service_cls.return_value = mock_service

        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        result = runner.invoke(
            app,
            ["daemon", "start", "--watch-dir", str(watch_dir), "--foreground"],
        )

        assert result.exit_code == 0
        assert "Daemon stopped" in result.stdout

    @patch("file_organizer.cli.daemon.DaemonService")
    def test_start_no_watch_dir(self, mock_service_cls):
        """Test starting daemon without watch directory (uses default)."""
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        result = runner.invoke(
            app,
            ["daemon", "start", "--foreground"],
        )

        assert result.exit_code == 0
        mock_service.start.assert_called_once()


class TestDaemonStop:
    """Tests for daemon stop command."""

    @patch("file_organizer.cli.daemon.PidFileManager")
    def test_stop_running_daemon(self, mock_pidmgr_cls, tmp_path):
        """Test stopping a running daemon."""
        mock_pidmgr = MagicMock()
        mock_pidmgr.read_pid.return_value = 12345
        mock_pidmgr.is_running.return_value = True
        mock_pidmgr_cls.return_value = mock_pidmgr

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("12345")

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            with patch("os.kill"):
                result = runner.invoke(app, ["daemon", "stop"])

        assert result.exit_code == 0
        assert "Daemon stopped" in result.stdout
        mock_pidmgr.remove_pid.assert_called_once()

    @patch("file_organizer.cli.daemon.PidFileManager")
    def test_stop_no_pid_file(self, mock_pidmgr_cls, tmp_path):
        """Test stopping when no PID file exists."""
        mock_pidmgr = MagicMock()
        mock_pidmgr_cls.return_value = mock_pidmgr

        pid_file = tmp_path / "nonexistent.pid"

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            result = runner.invoke(app, ["daemon", "stop"])

        assert result.exit_code == 1
        assert "No PID file found" in result.stdout

    @patch("file_organizer.cli.daemon.PidFileManager")
    def test_stop_process_not_found(self, mock_pidmgr_cls, tmp_path):
        """Test stopping when process doesn't exist."""
        mock_pidmgr = MagicMock()
        mock_pidmgr.read_pid.return_value = 99999
        mock_pidmgr_cls.return_value = mock_pidmgr

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("99999")

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            with patch("os.kill", side_effect=ProcessLookupError()):
                result = runner.invoke(app, ["daemon", "stop"])

        assert result.exit_code == 0
        assert "Process not found" in result.stdout

    @patch("file_organizer.cli.daemon.PidFileManager")
    def test_stop_permission_denied(self, mock_pidmgr_cls, tmp_path):
        """Test stopping when permission is denied."""
        mock_pidmgr = MagicMock()
        mock_pidmgr.read_pid.return_value = 12345
        mock_pidmgr_cls.return_value = mock_pidmgr

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("12345")

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            with patch("os.kill", side_effect=PermissionError()):
                result = runner.invoke(app, ["daemon", "stop"])

        assert result.exit_code == 1
        assert "Permission denied" in result.stdout

    @patch("file_organizer.cli.daemon.PidFileManager")
    def test_stop_invalid_pid(self, mock_pidmgr_cls, tmp_path):
        """Test stopping when PID file cannot be read."""
        mock_pidmgr = MagicMock()
        mock_pidmgr.read_pid.return_value = None
        mock_pidmgr_cls.return_value = mock_pidmgr

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("invalid")

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            result = runner.invoke(app, ["daemon", "stop"])

        assert result.exit_code == 1
        assert "Could not read PID" in result.stdout


class TestDaemonStatus:
    """Tests for daemon status command."""

    @patch("file_organizer.cli.daemon.PidFileManager")
    def test_status_running(self, mock_pidmgr_cls, tmp_path):
        """Test daemon status when running."""
        mock_pidmgr = MagicMock()
        mock_pidmgr.is_running.return_value = True
        mock_pidmgr.read_pid.return_value = 12345
        mock_pidmgr_cls.return_value = mock_pidmgr

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("12345")

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            result = runner.invoke(app, ["daemon", "status"])

        assert result.exit_code == 0
        assert "Running" in result.stdout or "12345" in result.stdout

    @patch("file_organizer.cli.daemon.PidFileManager")
    def test_status_stopped(self, mock_pidmgr_cls, tmp_path):
        """Test daemon status when stopped."""
        mock_pidmgr = MagicMock()
        mock_pidmgr.is_running.return_value = False
        mock_pidmgr.read_pid.return_value = None
        mock_pidmgr_cls.return_value = mock_pidmgr

        pid_file = tmp_path / "nonexistent.pid"

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            result = runner.invoke(app, ["daemon", "status"])

        assert result.exit_code == 0
        assert "Stopped" in result.stdout or "Status" in result.stdout

    @patch("file_organizer.cli.daemon.PidFileManager")
    def test_status_shows_python_version(self, mock_pidmgr_cls, tmp_path):
        """Test daemon status includes Python version."""
        mock_pidmgr = MagicMock()
        mock_pidmgr.is_running.return_value = False
        mock_pidmgr_cls.return_value = mock_pidmgr

        pid_file = tmp_path / "daemon.pid"

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            result = runner.invoke(app, ["daemon", "status"])

        assert result.exit_code == 0
        # Status should show Python version
        assert "Python" in result.stdout or "3." in result.stdout


class TestDaemonWatch:
    """Tests for daemon watch command."""

    @patch("file_organizer.cli.daemon.FileMonitor")
    def test_watch_directory(self, mock_monitor_cls, tmp_path):
        """Test watching a directory for file events."""
        mock_monitor = MagicMock()
        mock_monitor.get_events_blocking.side_effect = KeyboardInterrupt()
        mock_monitor_cls.return_value = mock_monitor

        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        result = runner.invoke(app, ["daemon", "watch", str(watch_dir)])

        assert result.exit_code == 0
        mock_monitor.start.assert_called_once()

    @patch("file_organizer.cli.daemon.FileMonitor")
    def test_watch_with_poll_interval(self, mock_monitor_cls, tmp_path):
        """Test watching with custom poll interval."""
        mock_monitor = MagicMock()
        mock_monitor.get_events_blocking.side_effect = KeyboardInterrupt()
        mock_monitor_cls.return_value = mock_monitor

        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        result = runner.invoke(
            app, ["daemon", "watch", str(watch_dir), "--poll-interval", "2.0"]
        )

        assert result.exit_code == 0
        mock_monitor.start.assert_called_once()

    @patch("file_organizer.cli.daemon.FileMonitor")
    def test_watch_shows_status(self, mock_monitor_cls, tmp_path):
        """Test watch command shows watching status."""
        mock_monitor = MagicMock()
        mock_monitor.get_events_blocking.side_effect = KeyboardInterrupt()
        mock_monitor_cls.return_value = mock_monitor

        watch_dir = tmp_path / "watch"
        watch_dir.mkdir()

        result = runner.invoke(app, ["daemon", "watch", str(watch_dir)])

        assert result.exit_code == 0
        assert "Watching" in result.stdout

    def test_watch_missing_directory(self):
        """Test watch with missing directory argument."""
        result = runner.invoke(app, ["watch"])

        assert result.exit_code != 0
