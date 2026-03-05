"""Coverage tests for file_organizer.cli.daemon — uncovered lines 51-208."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

runner = CliRunner()


@dataclass
class _FakeOrganizeResult:
    total_files: int = 5
    processed_files: int = 4
    skipped_files: int = 1
    failed_files: int = 0
    organized_structure: dict = field(default_factory=lambda: {"docs": [], "imgs": []})
    errors: list = field(default_factory=list)


class TestDaemonStart:
    """Covers lines 51-80."""

    def test_start_foreground(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        mock_service = MagicMock()
        mock_service.start.side_effect = KeyboardInterrupt()

        with (
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_service),
            patch("file_organizer.daemon.config.DaemonConfig"),
        ):
            result = runner.invoke(
                daemon_app,
                ["start", "--foreground", "--watch-dir", str(tmp_path)],
            )

        assert result.exit_code == 0
        assert "foreground" in result.output.lower() or "Daemon" in result.output

    def test_start_background(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        mock_service = MagicMock()

        with (
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_service),
            patch("file_organizer.daemon.config.DaemonConfig"),
        ):
            result = runner.invoke(
                daemon_app,
                ["start", "--watch-dir", str(tmp_path)],
            )

        assert result.exit_code == 0
        mock_service.start_background.assert_called_once()

    def test_start_foreground_dry_run(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        mock_service = MagicMock()
        mock_service.start.side_effect = KeyboardInterrupt()

        with (
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_service),
            patch("file_organizer.daemon.config.DaemonConfig"),
        ):
            result = runner.invoke(
                daemon_app,
                ["start", "--foreground", "--dry-run", "--watch-dir", str(tmp_path)],
            )

        assert result.exit_code == 0
        assert "Dry-run" in result.output

    def test_start_background_dry_run(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        mock_service = MagicMock()

        with (
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_service),
            patch("file_organizer.daemon.config.DaemonConfig"),
        ):
            result = runner.invoke(
                daemon_app,
                ["start", "--dry-run", "--watch-dir", str(tmp_path)],
            )

        assert result.exit_code == 0
        assert "Dry-run" in result.output


class TestDaemonStop:
    """Covers lines 86-112."""

    def test_stop_no_pid_file(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        with patch(
            "file_organizer.cli.daemon._DEFAULT_PID_FILE",
            tmp_path / "nonexistent_daemon_test.pid",
        ):
            result = runner.invoke(daemon_app, ["stop"])

        assert result.exit_code == 1
        assert "No PID file" in result.output

    def test_stop_unreadable_pid(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("not_a_number")

        mock_mgr = MagicMock()
        mock_mgr.read_pid.return_value = None

        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
        ):
            result = runner.invoke(daemon_app, ["stop"])

        assert result.exit_code == 1
        assert "Could not read PID" in result.output

    def test_stop_success(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("12345")

        mock_mgr = MagicMock()
        mock_mgr.read_pid.return_value = 12345

        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
            patch("os.kill"),
        ):
            result = runner.invoke(daemon_app, ["stop"])

        assert result.exit_code == 0
        assert "stopped" in result.output.lower()

    def test_stop_process_not_found(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("99999")

        mock_mgr = MagicMock()
        mock_mgr.read_pid.return_value = 99999

        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
            patch("os.kill", side_effect=ProcessLookupError()),
        ):
            result = runner.invoke(daemon_app, ["stop"])

        assert result.exit_code == 0
        assert "not found" in result.output.lower()

    def test_stop_permission_error(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("1")

        mock_mgr = MagicMock()
        mock_mgr.read_pid.return_value = 1

        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
            patch("os.kill", side_effect=PermissionError()),
        ):
            result = runner.invoke(daemon_app, ["stop"])

        assert result.exit_code == 1
        assert "Permission denied" in result.output


class TestDaemonStatus:
    """Covers lines 118-136."""

    def test_status_running(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        pid_file = tmp_path / "daemon.pid"
        pid_file.write_text("12345")

        mock_mgr = MagicMock()
        mock_mgr.is_running.return_value = True
        mock_mgr.read_pid.return_value = 12345

        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
        ):
            result = runner.invoke(daemon_app, ["status"])

        assert result.exit_code == 0
        assert "Running" in result.output

    def test_status_stopped(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        mock_mgr = MagicMock()
        mock_mgr.is_running.return_value = False

        with (
            patch(
                "file_organizer.cli.daemon._DEFAULT_PID_FILE",
                tmp_path / "nonexistent.pid",
            ),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
        ):
            result = runner.invoke(daemon_app, ["status"])

        assert result.exit_code == 0
        assert "Stopped" in result.output


class TestDaemonProcess:
    """Covers lines 177-208."""

    def test_process_success(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        (tmp_path / "file.txt").write_text("hello")
        output_dir = tmp_path / "output"

        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = _FakeOrganizeResult()

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer):
            result = runner.invoke(daemon_app, ["process", str(tmp_path), str(output_dir)])

        assert result.exit_code == 0
        assert "Processing Summary" in result.output

    def test_process_dry_run(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        output_dir = tmp_path / "output"
        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = _FakeOrganizeResult()

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer):
            result = runner.invoke(
                daemon_app,
                ["process", str(tmp_path), str(output_dir), "--dry-run"],
            )

        assert result.exit_code == 0
        assert "Dry-run" in result.output

    def test_process_with_errors(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        output_dir = tmp_path / "output"
        fake_result = _FakeOrganizeResult(
            errors=[("file1.txt", "permission denied"), ("file2.pdf", "corrupt")]
        )
        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = fake_result

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer):
            result = runner.invoke(daemon_app, ["process", str(tmp_path), str(output_dir)])

        assert result.exit_code == 0
        assert "Errors" in result.output

    def test_process_exception(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        output_dir = tmp_path / "output"
        mock_organizer = MagicMock()
        mock_organizer.organize.side_effect = RuntimeError("boom")

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer):
            result = runner.invoke(daemon_app, ["process", str(tmp_path), str(output_dir)])

        assert result.exit_code == 1

    def test_process_many_errors_truncated(self, tmp_path: Path) -> None:
        from file_organizer.cli.daemon import daemon_app

        output_dir = tmp_path / "output"
        errors = [(f"file{i}.txt", "err") for i in range(15)]
        fake_result = _FakeOrganizeResult(errors=errors)
        mock_organizer = MagicMock()
        mock_organizer.organize.return_value = fake_result

        with patch("file_organizer.core.organizer.FileOrganizer", return_value=mock_organizer):
            result = runner.invoke(daemon_app, ["process", str(tmp_path), str(output_dir)])

        assert result.exit_code == 0
        assert "5 more" in result.output
