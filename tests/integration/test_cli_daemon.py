"""Integration tests for daemon CLI sub-commands.

Covers: daemon start (foreground/background/dry-run), daemon stop
(no PID file, stale PID, permission denied, successful), daemon status,
daemon process (dry-run / error paths).
"""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app
from file_organizer.daemon.config import DaemonConfig
from file_organizer.daemon.pid import PidFileManager, PidRecord
from file_organizer.daemon.service import DaemonService

pytestmark = [pytest.mark.integration]

runner = CliRunner()


class TestDaemonStart:
    def test_start_background_dry_run(self, tmp_path: Path) -> None:
        """daemon start --dry-run in background mode shows dry-run hint."""
        mock_service = MagicMock()
        with (
            patch("file_organizer.daemon.service.DaemonService", return_value=mock_service),
            patch(
                "file_organizer.cli.daemon._DEFAULT_PID_FILE",
                tmp_path / "file_organizer.daemon.pid",
            ),
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
            patch(
                "file_organizer.cli.daemon._DEFAULT_PID_FILE",
                tmp_path / "file_organizer.daemon.pid",
            ),
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
            patch(
                "file_organizer.cli.daemon._DEFAULT_PID_FILE",
                tmp_path / "file_organizer.daemon.pid",
            ),
        ):
            result = runner.invoke(app, ["daemon", "start", "--foreground"])
        assert result.exit_code == 0
        assert "stopped" in result.output.lower() or "daemon" in result.output.lower()

    def test_start_with_watch_dir(self, tmp_path: Path) -> None:
        mock_cls = MagicMock()
        mock_service = mock_cls.return_value
        with (
            patch("file_organizer.daemon.service.DaemonService", mock_cls),
            patch(
                "file_organizer.cli.daemon._DEFAULT_PID_FILE",
                tmp_path / "file_organizer.daemon.pid",
            ),
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
            patch(
                "file_organizer.cli.daemon._DEFAULT_PID_FILE",
                tmp_path / "file_organizer.daemon.pid",
            ),
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
            patch(
                "file_organizer.cli.daemon._DEFAULT_PID_FILE",
                tmp_path / "file_organizer.daemon.pid",
            ),
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
        fake_pid = tmp_path / "file_organizer.daemon.pid"
        fake_pid.write_text("")  # empty → None from read_pid

        mock_mgr = MagicMock()
        mock_mgr.read_pid_record.return_value = None
        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", fake_pid),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
        ):
            result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 1
        mock_mgr.remove_pid.assert_called_once()

    def test_stop_stale_pid_exits_0_and_cleans_up(self, tmp_path: Path) -> None:
        """stop with a stale PID (process gone) exits 0 and removes PID file."""
        fake_pid = tmp_path / "file_organizer.daemon.pid"
        fake_pid.write_text("99999")

        mock_mgr = MagicMock()
        mock_mgr.read_pid_record.return_value = PidRecord(pid=99999, create_time=None)
        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", fake_pid),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
            patch("os.kill", side_effect=ProcessLookupError()),
        ):
            result = runner.invoke(app, ["daemon", "stop"])
        assert result.exit_code == 0
        mock_mgr.remove_pid.assert_called_once()

    def test_stop_permission_denied_exits_1(self, tmp_path: Path) -> None:
        fake_pid = tmp_path / "file_organizer.daemon.pid"
        fake_pid.write_text("1")

        mock_mgr = MagicMock()
        mock_mgr.read_pid_record.return_value = PidRecord(pid=1, create_time=None)
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
        fake_pid = tmp_path / "file_organizer.daemon.pid"
        fake_pid.write_text("12345")

        mock_mgr = MagicMock()
        mock_mgr.read_pid_record.return_value = PidRecord(pid=12345, create_time=None)
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
        mock_mgr.read_pid_record.return_value = None
        with (
            patch(
                "file_organizer.cli.daemon._DEFAULT_PID_FILE",
                tmp_path / "file_organizer.daemon.pid",
            ),
            patch("file_organizer.daemon.pid.PidFileManager", return_value=mock_mgr),
        ):
            result = runner.invoke(app, ["daemon", "status"])
        assert result.exit_code == 0
        # Table must contain some state information
        assert "daemon" in result.output.lower() or "state" in result.output.lower()

    def test_status_running_shows_pid(self, tmp_path: Path) -> None:
        mock_mgr = MagicMock()
        mock_mgr.is_running.return_value = True
        mock_mgr.read_pid_record.return_value = PidRecord(pid=42, create_time=None)
        fake_pid = tmp_path / "file_organizer.daemon.pid"
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
        stub_text_model: None,
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


# ---------------------------------------------------------------------------
# F4 hardening — signal-write failure tracking + pipe drain
# ---------------------------------------------------------------------------


class TestSignalWriteFailureTrackingIntegration:
    """F4 (hardening roadmap #159): integration-level coverage for the
    signal-write failure counter and the full-drain path so the
    daemon/service.py integration floor is preserved."""

    def test_closed_pipe_bumps_failure_counter(self) -> None:
        """Signal handler increments the counter when ``os.write`` fails."""
        daemon = DaemonService(DaemonConfig())
        r, w = os.pipe()
        os.close(r)
        os.close(w)
        daemon._sig_wakeup_w = w

        daemon._handle_signal(signal.SIGTERM, None)
        daemon._handle_signal(signal.SIGTERM, None)
        assert daemon._signal_write_failures == 2

    def test_drain_empties_full_pipe(self) -> None:
        """The drain helper reads every buffered byte until EAGAIN."""
        daemon = DaemonService(DaemonConfig())
        r, w = os.pipe()
        os.set_blocking(r, False)
        os.set_blocking(w, False)
        try:
            for _ in range(20):
                os.write(w, b"\x00")
            daemon._drain_signal_pipe(r)
            with pytest.raises(BlockingIOError):
                os.read(r, 1)
        finally:
            os.close(r)
            os.close(w)

    def test_log_helper_emits_on_delta(
        self,
        caplog: pytest.LogCaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Bypass the rate-limit interval so the per-delta contract is
        # exercised deterministically from the integration suite.
        monkeypatch.setattr("file_organizer.daemon.service._SIGNAL_LOG_MIN_INTERVAL_S", 0.0)
        daemon = DaemonService(DaemonConfig())
        daemon._signal_write_failures = 4

        with caplog.at_level("WARNING", logger="file_organizer.daemon.service"):
            daemon._log_signal_write_failures_if_new()
            daemon._log_signal_write_failures_if_new()  # no delta → no extra log

        hits = [r for r in caplog.records if "write failures" in r.message]
        assert len(hits) == 1


# ---------------------------------------------------------------------------
# F2 hardening — JSON PID file boundary exercised through the CLI
# ---------------------------------------------------------------------------


@pytest.mark.ci
class TestJSONPidFileCLIBoundary:
    """F2 (hardening roadmap #159): the service writes PID files via
    ``write_pid_record`` (JSON) but the legacy ``read_pid`` helper only
    parses plain integers. These tests drive real JSON records through
    ``daemon status`` and ``daemon stop`` to lock in that the CLI reads
    the JSON payload — regressing to ``read_pid`` would orphan the
    daemon process (stop would delete a valid PID file and exit 1).

    Marked ``ci`` (in addition to the module-level ``integration``) so
    PR-level diff coverage counts these for the new ``read_pid_record``
    lines in ``cli/daemon.py``.
    """

    def test_status_reads_json_pid_record(self, tmp_path: Path) -> None:
        """`daemon status` renders the PID recorded in a JSON file.

        Writes a real ``{"pid": ..., "create_time": ...}`` payload with
        the current process's PID + start time so ``is_running`` sees a
        live process and the CLI must parse the JSON record (not fall
        through to the legacy text-only reader) to surface the PID.
        """
        pid_file = tmp_path / "file_organizer.daemon.pid"
        PidFileManager().write_pid_record(pid_file)

        with patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file):
            result = runner.invoke(app, ["daemon", "status"])

        assert result.exit_code == 0
        assert str(os.getpid()) in result.output, (
            "daemon status did not render the PID from the JSON record; "
            "likely regressed to the legacy read_pid code path"
        )
        assert "Running" in result.output

    def test_stop_reads_json_pid_record(self, tmp_path: Path) -> None:
        """`daemon stop` parses a JSON PID record and does not orphan
        the file.

        ``os.kill`` is mocked to raise ``ProcessLookupError`` — the CLI
        then removes the PID file and reports a clean stop. Regressing
        to ``read_pid`` would return ``None``, print "Could not read
        PID", still remove the file, but exit code 1 (not 0).

        Mocking (rather than relying on the PID itself being unused)
        keeps the test deterministic on hosts with large ``pid_max``
        where a sentinel might happen to be allocated, and matches the
        pattern used by ``test_stop_stale_pid_exits_0_and_cleans_up``.
        """
        pid_file = tmp_path / "file_organizer.daemon.pid"
        pid_file.write_text(json.dumps({"pid": 99999999, "create_time": 1.0}))

        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file),
            patch("os.kill", side_effect=ProcessLookupError()),
        ):
            result = runner.invoke(app, ["daemon", "stop"])

        assert result.exit_code == 0, (
            f"daemon stop failed to parse JSON PID record: {result.output!r}"
        )
        assert "Process not found" in result.output
        assert not pid_file.exists(), "stale PID file should be cleaned up"

    def test_stop_falls_back_to_legacy_int_pid(self, tmp_path: Path) -> None:
        """Backward compatibility: pre-F2 PID files (plain integer
        text) still work through the new CLI read path.

        ``os.kill`` is mocked for the same determinism reason as
        ``test_stop_reads_json_pid_record`` above.
        """
        pid_file = tmp_path / "file_organizer.daemon.pid"
        pid_file.write_text("99999998")

        with (
            patch("file_organizer.cli.daemon._DEFAULT_PID_FILE", pid_file),
            patch("os.kill", side_effect=ProcessLookupError()),
        ):
            result = runner.invoke(app, ["daemon", "stop"])

        assert result.exit_code == 0
        assert "Process not found" in result.output
        assert not pid_file.exists()
