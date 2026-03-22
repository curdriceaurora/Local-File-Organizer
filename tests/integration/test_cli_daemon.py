"""Integration tests for daemon CLI sub-commands.

Covers: daemon start (foreground/background/dry-run), daemon stop
(no PID file, stale PID, permission denied, successful), daemon status,
daemon process (dry-run / error paths).
"""

from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.integration]

runner = CliRunner()


class TestDaemonStart:
    def test_start_background_dry_run(self, tmp_path: Path) -> None:
        """daemon start --dry-run in background mode shows dry-run hint."""
        mock_service = MagicMock()
        with (
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_service),
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", tmp_path / "daemon.pid"),
        ):
            result = runner.invoke(
                app,
                ["daemon", "start", "--dry-run"],
            )
        assert result.exit_code == 0
        mock_service.start_background.assert_called_once()

    def test_start_foreground_calls_service_start(self, tmp_path: Path) -> None:
        """daemon start --foreground calls service.start() (not start_background)."""
        mock_service = MagicMock()
        with (
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_service),
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", tmp_path / "daemon.pid"),
        ):
            result = runner.invoke(
                app,
                ["daemon", "start", "--foreground"],
            )
        assert result.exit_code == 0
        mock_service.start.assert_called_once()
        mock_service.start_background.assert_not_called()

    def test_start_foreground_keyboard_interrupt_exits_cleanly(self, tmp_path: Path) -> None:
        """KeyboardInterrupt in foreground mode prints stop message and exits 0."""
        mock_service = MagicMock()
        mock_service.start.side_effect = KeyboardInterrupt()
        with (
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_service),
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", tmp_path / "daemon.pid"),
        ):
            result = runner.invoke(app, ["daemon", "start", "--foreground"])
        assert result.exit_code == 0
        assert "stopped" in result.output.lower() or "daemon" in result.output.lower()

    def test_start_with_watch_dir(self, tmp_path: Path) -> None:
        mock_cls = MagicMock()
        mock_service = mock_cls.return_value
        with (
            patch("file_organizer.daemon.service.DaemonService", mock_cls),
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", tmp_path / "daemon.pid"),
        ):
            result = runner.invoke(
                app,
                [
                    "daemon",
                    "start",
                    "--watch-dir",
                    str(tmp_path),
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0
        config = mock_cls.call_args.args[0]
        assert tmp_path in config.watch_directories
        mock_service.start_background.assert_called_once()

    def test_start_with_output_dir(self, tmp_path: Path) -> None:
        mock_cls = MagicMock()
        mock_service = mock_cls.return_value
        with (
            patch("file_organizer.daemon.service.DaemonService", mock_cls),
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", tmp_path / "daemon.pid"),
        ):
            result = runner.invoke(
                app,
                [
                    "daemon",
                    "start",
                    "--output-dir",
                    str(tmp_path / "out"),
                    "--dry-run",
                ],
            )
        assert result.exit_code == 0
        config = mock_cls.call_args.args[0]
        assert config.output_directory == tmp_path / "out"
        mock_service.start_background.assert_called_once()

    def test_start_background_dry_run_shows_hint(self, tmp_path: Path) -> None:
        mock_service = MagicMock()
        with (
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_service),
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", tmp_path / "daemon.pid"),
        ):
            result = runner.invoke(app, ["daemon", "start", "--dry-run"])
        assert "dry" in result.output.lower()


class TestDaemonStop:
    def test_stop_no_pid_file_exits_1(self, tmp_path: Path) -> None:
        """stop with no PID file exits 1 with helpful message."""
        fake_pid = tmp_path / "nonexistent.pid"
        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", fake_pid):
            result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 1
        assert "pid" in result.output.lower() or "daemon" in result.output.lower()

    def test_stop_corrupt_pid_file_exits_1(self, tmp_path: Path) -> None:
        """stop with unreadable PID exits 1 and removes the file."""
        fake_pid = tmp_path / "daemon.pid"
        fake_pid.write_text("")  # empty → None from read_pid

        mock_mgr = MagicMock()
        mock_mgr.read_pid.return_value = None
        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", fake_pid),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
        ):
            result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 1
        mock_mgr.remove_pid.assert_called_once()

    def test_stop_stale_pid_exits_0_and_cleans_up(self, tmp_path: Path) -> None:
        """stop with a stale PID (process gone) exits 0 and removes PID file."""
        fake_pid = tmp_path / "daemon.pid"
        fake_pid.write_text("99999")

        mock_mgr = MagicMock()
        mock_mgr.read_pid.return_value = 99999
        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", fake_pid),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
            patch("os.kill", side_effect=ProcessLookupError()),
        ):
            result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0
        mock_mgr.remove_pid.assert_called_once()

    def test_stop_permission_denied_exits_1(self, tmp_path: Path) -> None:
        fake_pid = tmp_path / "daemon.pid"
        fake_pid.write_text("1")

        mock_mgr = MagicMock()
        mock_mgr.read_pid.return_value = 1
        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", fake_pid),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
            patch("os.kill", side_effect=PermissionError()),
        ):
            result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 1
        assert "permission" in result.output.lower() or "sudo" in result.output.lower()

    def test_stop_successful(self, tmp_path: Path) -> None:
        """stop with a live PID sends SIGTERM and exits 0."""
        fake_pid = tmp_path / "daemon.pid"
        fake_pid.write_text("12345")

        mock_mgr = MagicMock()
        mock_mgr.read_pid.return_value = 12345
        kill_calls: list[tuple[int, int]] = []

        def fake_kill(pid: int, sig: int) -> None:
            kill_calls.append((pid, sig))

        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", fake_pid),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
            patch("os.kill", side_effect=fake_kill),
        ):
            result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0
        assert kill_calls == [(12345, signal.SIGTERM)]
        mock_mgr.remove_pid.assert_called_once()


class TestDaemonStatus:
    def test_status_shows_state(self, tmp_path: Path) -> None:
        mock_mgr = MagicMock()
        mock_mgr.is_running.return_value = False
        mock_mgr.read_pid.return_value = None
        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", tmp_path / "daemon.pid"),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
        ):
            result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        # Table must contain some state information
        assert "daemon" in result.output.lower() or "state" in result.output.lower()

    def test_status_running_shows_pid(self, tmp_path: Path) -> None:
        mock_mgr = MagicMock()
        mock_mgr.is_running.return_value = True
        mock_mgr.read_pid.return_value = 42
        fake_pid = tmp_path / "daemon.pid"
        fake_pid.write_text("42")
        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", fake_pid),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
        ):
            result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        assert "42" in result.output


class TestDaemonProcess:
    def test_process_dry_run(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        result = runner.invoke(
            app,
            [
                "daemon",
                "process",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        # Summary table should contain metrics
        assert "total" in result.output.lower() or "processed" in result.output.lower()

    def test_process_exception_exits_1(
        self,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        with patch(
            "file_organizer.core.organizer.FileOrganizer.organize",
            side_effect=RuntimeError("organizer failed"),
        ):
            result = runner.invoke(
                app,
                [
                    "daemon",
                    "process",
                    str(integration_source_dir),
                    str(integration_output_dir),
                ],
            )
        assert result.exit_code == 1
        assert "error" in result.output.lower()
