"""
Unit tests for PidFileManager.

Tests PID file creation, reading, removal, and liveness checking
with both real and synthetic PID values.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest

from file_organizer.daemon.pid import PidFileManager

pytestmark = [pytest.mark.unit, pytest.mark.smoke, pytest.mark.ci]


@pytest.fixture
def pid_manager() -> PidFileManager:
    """Create a PidFileManager instance."""
    return PidFileManager()


@pytest.fixture
def pid_file(tmp_path: Path) -> Path:
    """Return a temporary PID file path (not yet created)."""
    return tmp_path / "test_daemon.pid"


@pytest.mark.unit
class TestWritePid:
    """Tests for PidFileManager.write_pid."""

    def test_write_current_pid(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """write_pid writes the current PID by default."""
        pid_manager.write_pid(pid_file)

        assert pid_file.exists()
        content = pid_file.read_text().strip()
        assert int(content) == os.getpid()

    def test_write_specific_pid(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """write_pid writes the provided PID when given."""
        pid_manager.write_pid(pid_file, pid=12345)

        content = pid_file.read_text().strip()
        assert content == "12345"

    def test_write_creates_parent_directories(
        self, pid_manager: PidFileManager, tmp_path: Path
    ) -> None:
        """write_pid creates parent directories if missing."""
        nested = tmp_path / "a" / "b" / "c" / "daemon.pid"
        pid_manager.write_pid(nested)

        assert nested.exists()

    def test_write_overwrites_existing(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """write_pid overwrites an existing PID file."""
        pid_manager.write_pid(pid_file, pid=111)
        pid_manager.write_pid(pid_file, pid=222)

        assert pid_manager.read_pid(pid_file) == 222


@pytest.mark.unit
class TestReadPid:
    """Tests for PidFileManager.read_pid."""

    def test_read_existing_pid(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """read_pid returns the PID from an existing file."""
        pid_file.write_text("42")
        assert pid_manager.read_pid(pid_file) == 42

    def test_read_nonexistent_returns_none(
        self, pid_manager: PidFileManager, pid_file: Path
    ) -> None:
        """read_pid returns None when the file does not exist."""
        assert pid_manager.read_pid(pid_file) is None

    def test_read_empty_file_returns_none(
        self, pid_manager: PidFileManager, pid_file: Path
    ) -> None:
        """read_pid returns None for an empty file."""
        pid_file.write_text("")
        assert pid_manager.read_pid(pid_file) is None

    def test_read_invalid_content_returns_none(
        self, pid_manager: PidFileManager, pid_file: Path
    ) -> None:
        """read_pid returns None when the file contains non-numeric data."""
        pid_file.write_text("not-a-pid")
        assert pid_manager.read_pid(pid_file) is None

    def test_read_whitespace_stripped(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """read_pid strips whitespace before parsing."""
        pid_file.write_text("  99  \n")
        assert pid_manager.read_pid(pid_file) == 99


@pytest.mark.unit
class TestRemovePid:
    """Tests for PidFileManager.remove_pid."""

    def test_remove_existing_file(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """remove_pid deletes the PID file and returns True."""
        pid_file.write_text("42")
        assert pid_manager.remove_pid(pid_file) is True
        assert not pid_file.exists()

    def test_remove_nonexistent_returns_false(
        self, pid_manager: PidFileManager, pid_file: Path
    ) -> None:
        """remove_pid returns False for a nonexistent file."""
        assert pid_manager.remove_pid(pid_file) is False


@pytest.mark.unit
class TestIsRunning:
    """Tests for PidFileManager.is_running."""

    def test_current_process_is_running(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """is_running returns True for the current process."""
        pid_manager.write_pid(pid_file)
        assert pid_manager.is_running(pid_file) is True

    def test_nonexistent_file_not_running(
        self, pid_manager: PidFileManager, pid_file: Path
    ) -> None:
        """is_running returns False when the PID file does not exist."""
        assert pid_manager.is_running(pid_file) is False

    def test_dead_pid_not_running(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """is_running returns False for a PID that no longer exists."""
        # Use a very high PID that is almost certainly not running
        pid_file.write_text("4000000")
        assert pid_manager.is_running(pid_file) is False

    def test_empty_file_not_running(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """is_running returns False for an empty PID file."""
        pid_file.write_text("")
        assert pid_manager.is_running(pid_file) is False

    @pytest.mark.parametrize("bad_pid", ["0", "-1"])
    def test_non_positive_pid_not_running(
        self, pid_manager: PidFileManager, pid_file: Path, bad_pid: str
    ) -> None:
        """is_running rejects non-positive PIDs without probing.

        os.kill(0, 0) / os.kill(-1, 0) broadcast to whole process groups on
        POSIX, so a 0 or negative PID must short-circuit to False and must
        never reach os.kill.
        """
        pid_file.write_text(bad_pid)
        with mock.patch("file_organizer.daemon.pid.os.kill") as mock_kill:
            assert pid_manager.is_running(pid_file) is False
        mock_kill.assert_not_called()

    def test_is_running_on_windows_uses_psutil_not_os_kill(
        self, pid_manager: PidFileManager, pid_file: Path
    ) -> None:
        """On Windows, is_running must use psutil.pid_exists, never os.kill.

        os.kill on Windows maps signal 0 to TerminateProcess, so probing the
        current PID with os.kill would terminate this process. This regression
        guards the Windows CI hang/abort caused by that behavior.
        """
        pid_file.write_text(str(os.getpid()))
        fake_psutil = mock.MagicMock()
        fake_psutil.pid_exists.return_value = True
        with (
            mock.patch("file_organizer.daemon.pid.sys.platform", "win32"),
            mock.patch("file_organizer.daemon.pid.os.kill") as mock_kill,
            mock.patch.dict("sys.modules", {"psutil": fake_psutil}),
        ):
            assert pid_manager.is_running(pid_file) is True
        mock_kill.assert_not_called()
        fake_psutil.pid_exists.assert_called_once_with(os.getpid())

    def test_permission_error_means_running(
        self, pid_manager: PidFileManager, pid_file: Path
    ) -> None:
        """On POSIX, an EPERM from os.kill means the process exists.

        A process owned by another user raises PermissionError for signal 0,
        which still proves the process is alive.
        """
        pid_file.write_text("12345")
        with (
            mock.patch("file_organizer.daemon.pid.sys.platform", "linux"),
            mock.patch("file_organizer.daemon.pid.os.kill", side_effect=PermissionError),
        ):
            assert pid_manager.is_running(pid_file) is True

    def test_generic_oserror_not_running(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """On POSIX, any other OSError from os.kill is treated as not running."""
        pid_file.write_text("12345")
        with (
            mock.patch("file_organizer.daemon.pid.sys.platform", "linux"),
            mock.patch("file_organizer.daemon.pid.os.kill", side_effect=OSError),
        ):
            assert pid_manager.is_running(pid_file) is False

    def test_huge_pid_not_running(self, pid_manager: PidFileManager, pid_file: Path) -> None:
        """A corrupted PID file with an out-of-range PID is not running.

        On POSIX, os.kill raises OverflowError (not OSError) for an integer
        larger than the platform's pid_t. is_running must absorb it and return
        False rather than letting it crash callers like `daemon status`.
        """
        pid_file.write_text(str(10**100))
        with (
            mock.patch("file_organizer.daemon.pid.sys.platform", "linux"),
            mock.patch("file_organizer.daemon.pid.os.kill", side_effect=OverflowError),
        ):
            assert pid_manager.is_running(pid_file) is False

    def test_is_running_on_windows_reports_dead_pid(
        self, pid_manager: PidFileManager, pid_file: Path
    ) -> None:
        """On Windows, a PID psutil reports as absent is not running."""
        pid_file.write_text("4000000")
        fake_psutil = mock.MagicMock()
        fake_psutil.pid_exists.return_value = False
        with (
            mock.patch("file_organizer.daemon.pid.sys.platform", "win32"),
            mock.patch("file_organizer.daemon.pid.os.kill") as mock_kill,
            mock.patch.dict("sys.modules", {"psutil": fake_psutil}),
        ):
            assert pid_manager.is_running(pid_file) is False
        mock_kill.assert_not_called()
        fake_psutil.pid_exists.assert_called_once_with(4000000)
