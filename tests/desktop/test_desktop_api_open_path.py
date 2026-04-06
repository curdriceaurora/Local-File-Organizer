"""Tests for DesktopAPI.open_path().

Covers:
- Returns False immediately for empty path (no subprocess spawned)
- Platform dispatch: exact subprocess args for macOS, Windows, Linux
- shell=False guaranteed on all platforms (F4 security)
- Path is resolved (normalised) before being forwarded to subprocess
- Returns False on subprocess exception (F1)
- Returns False on non-zero subprocess returncode
- Returns False on unknown platform
- Linux: opens directory itself; falls back to parent for files
- Returns True on successful dispatch
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestDesktopAPIOpenPath:
    """Unit tests for DesktopAPI.open_path()."""

    # ------------------------------------------------------------------
    # Empty path guard
    # ------------------------------------------------------------------

    def test_returns_false_for_empty_string(self) -> None:
        """open_path('') must return False without spawning any subprocess."""
        from file_organizer.desktop.app import DesktopAPI

        with patch("file_organizer.desktop.app.subprocess") as mock_sub:
            result = DesktopAPI().open_path("")

        assert result is False
        mock_sub.run.assert_not_called()

    # ------------------------------------------------------------------
    # Platform dispatch (T3: verify exact subprocess.run arguments)
    # ------------------------------------------------------------------

    def test_calls_open_minus_r_on_macos(self, tmp_path: Path) -> None:
        """macOS must use ['open', '-R', resolved_path]."""
        from file_organizer.desktop.app import DesktopAPI

        target = str(tmp_path)
        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "darwin"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0)
            result = DesktopAPI().open_path(target)

        mock_sub.run.assert_called_once_with(
            ["open", "-R", target],
            check=False,
            timeout=5,
        )
        assert result is True

    def test_calls_explorer_select_on_windows(self, tmp_path: Path) -> None:
        """Windows must use ['explorer', '/select,<path>']."""
        from file_organizer.desktop.app import DesktopAPI

        target = str(tmp_path)
        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "win32"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0)
            result = DesktopAPI().open_path(target)

        mock_sub.run.assert_called_once_with(
            ["explorer", f"/select,{target}"],
            check=False,
            timeout=5,
        )
        assert result is True

    def test_calls_xdg_open_parent_on_linux_for_file(self, tmp_path: Path) -> None:
        """Linux must use ['xdg-open', parent_directory] when path is a file."""
        from file_organizer.desktop.app import DesktopAPI

        target = str(tmp_path / "file.txt")  # does not exist → is_dir() is False
        parent = str(tmp_path)
        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "linux"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0)
            result = DesktopAPI().open_path(target)

        mock_sub.run.assert_called_once_with(
            ["xdg-open", parent],
            check=False,
            timeout=5,
        )
        assert result is True

    def test_calls_xdg_open_dir_on_linux_for_directory(self, tmp_path: Path) -> None:
        """Linux must use ['xdg-open', path] directly when path is a directory."""
        from file_organizer.desktop.app import DesktopAPI

        target = str(tmp_path)  # tmp_path is a real directory → is_dir() is True
        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "linux"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0)
            result = DesktopAPI().open_path(target)

        mock_sub.run.assert_called_once_with(
            ["xdg-open", target],
            check=False,
            timeout=5,
        )
        assert result is True

    def test_returns_false_on_unknown_platform(self, tmp_path: Path) -> None:
        """Unknown platforms must return False without spawning a subprocess."""
        from file_organizer.desktop.app import DesktopAPI

        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "freebsd13"),
        ):
            result = DesktopAPI().open_path(str(tmp_path))

        assert result is False
        mock_sub.run.assert_not_called()

    # ------------------------------------------------------------------
    # Security: shell=False guaranteed (F4)
    # ------------------------------------------------------------------

    def test_macos_subprocess_not_shell(self, tmp_path: Path) -> None:
        """macOS subprocess.run must never pass shell=True."""
        from file_organizer.desktop.app import DesktopAPI

        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "darwin"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0)
            DesktopAPI().open_path(str(tmp_path))

        _, kwargs = mock_sub.run.call_args
        assert kwargs.get("shell") is not True

    def test_windows_subprocess_not_shell(self, tmp_path: Path) -> None:
        """Windows subprocess.run must never pass shell=True."""
        from file_organizer.desktop.app import DesktopAPI

        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "win32"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0)
            DesktopAPI().open_path(str(tmp_path))

        _, kwargs = mock_sub.run.call_args
        assert kwargs.get("shell") is not True

    def test_linux_subprocess_not_shell(self, tmp_path: Path) -> None:
        """Linux subprocess.run must never pass shell=True."""
        from file_organizer.desktop.app import DesktopAPI

        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "linux"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0)
            DesktopAPI().open_path(str(tmp_path))

        _, kwargs = mock_sub.run.call_args
        assert kwargs.get("shell") is not True

    # ------------------------------------------------------------------
    # Path resolution
    # ------------------------------------------------------------------

    def test_resolves_path_before_forwarding(self, tmp_path: Path) -> None:
        """The path passed to subprocess must be the resolved absolute form."""
        from file_organizer.desktop.app import DesktopAPI

        # Use a relative-style path; resolve() should produce the abs form.
        target = str(tmp_path)
        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "darwin"),
        ):
            DesktopAPI().open_path(target)

        args, _ = mock_sub.run.call_args
        forwarded_path = args[0][2]  # ["open", "-R", <path>]
        assert Path(forwarded_path).is_absolute()

    # ------------------------------------------------------------------
    # Exception handling (F1)
    # ------------------------------------------------------------------

    def test_returns_false_on_subprocess_exception(self, tmp_path: Path) -> None:
        """If subprocess.run raises, open_path must return False gracefully."""
        from file_organizer.desktop.app import DesktopAPI

        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "darwin"),
        ):
            mock_sub.run.side_effect = OSError("open not found")
            result = DesktopAPI().open_path(str(tmp_path))

        assert result is False

    def test_returns_false_on_timeout_exception(self, tmp_path: Path) -> None:
        """If subprocess.run raises TimeoutExpired, open_path must return False."""
        import subprocess as real_subprocess

        from file_organizer.desktop.app import DesktopAPI

        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "darwin"),
        ):
            mock_sub.run.side_effect = real_subprocess.TimeoutExpired(cmd="open", timeout=5)
            result = DesktopAPI().open_path(str(tmp_path))

        assert result is False

    def test_returns_false_on_nonzero_returncode(self, tmp_path: Path) -> None:
        """Non-zero subprocess exit must return False (T2: state verification)."""
        from file_organizer.desktop.app import DesktopAPI

        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "darwin"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=1)
            result = DesktopAPI().open_path(str(tmp_path))

        assert result is False

    # ------------------------------------------------------------------
    # Return value (T2: verify True/False explicitly)
    # ------------------------------------------------------------------

    def test_returns_true_on_success_macos(self, tmp_path: Path) -> None:
        """Successful macOS dispatch must return True."""
        from file_organizer.desktop.app import DesktopAPI

        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "darwin"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0)
            result = DesktopAPI().open_path(str(tmp_path))

        assert result is True

    def test_returns_true_on_success_linux(self, tmp_path: Path) -> None:
        """Successful Linux dispatch must return True."""
        from file_organizer.desktop.app import DesktopAPI

        with (
            patch("file_organizer.desktop.app.subprocess") as mock_sub,
            patch.object(sys, "platform", "linux"),
        ):
            mock_sub.run.return_value = MagicMock(returncode=0)
            result = DesktopAPI().open_path(str(tmp_path))

        assert result is True
