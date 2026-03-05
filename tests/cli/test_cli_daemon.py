"""Tests for the daemon CLI sub-app (daemon.py).

Tests ``daemon start``, ``stop``, ``status``, ``watch``, and ``process`` commands.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit]

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
        mock_mgr.read_pid.return_value = 12345

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
        mock_mgr.read_pid.return_value = 99999

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
        mock_mgr.read_pid.return_value = 12345

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
