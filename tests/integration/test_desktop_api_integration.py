"""Integration tests for desktop/app.py DesktopAPI.

Covers: browse_directory, browse_file, save_file, open_path —
cancellation, expected exceptions swallowed, unexpected exceptions
re-raised, path separators stripped, non-zero exit code,
empty path guard, active_window() raising, platform dispatch.

[VERIFIED in: src/file_organizer/desktop/app.py]
"""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.desktop.app import DesktopAPI

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_webview(dialog_result: list[str] | None = None) -> MagicMock:
    """Return a fully-configured mock of the ``webview`` module.

    Args:
        dialog_result: Value returned by ``create_file_dialog``.  Pass
            ``None`` to simulate the user cancelling the dialog, or an
            empty list to simulate the dialog returning no selection.
    """
    wv = MagicMock()
    wv.FOLDER_DIALOG = 1
    wv.OPEN_DIALOG = 2
    wv.SAVE_DIALOG = 3
    mock_window = MagicMock()
    mock_window.create_file_dialog.return_value = dialog_result
    wv.active_window.return_value = mock_window
    return wv


@pytest.fixture()
def api() -> DesktopAPI:
    """Return a plain DesktopAPI instance (no webview at import time)."""
    return DesktopAPI()


# ---------------------------------------------------------------------------
# TestBrowseFile
# ---------------------------------------------------------------------------


class TestBrowseFile:
    def test_browse_file_returns_selected_path(self, api: DesktopAPI) -> None:
        """When the dialog returns a path, browse_file returns that exact path."""
        wv = _make_webview(dialog_result=["/Users/demo/file.txt"])
        with patch.dict("sys.modules", {"webview": wv}):
            result = api.browse_file()
        assert result == "/Users/demo/file.txt"

    def test_browse_file_passes_open_dialog_constant(self, api: DesktopAPI) -> None:
        """browse_file must call create_file_dialog with OPEN_DIALOG, not another constant."""
        wv = _make_webview(dialog_result=["/some/path.csv"])
        with patch.dict("sys.modules", {"webview": wv}):
            api.browse_file()
        wv.active_window().create_file_dialog.assert_called_once_with(
            wv.OPEN_DIALOG,
            file_types=(),
        )

    def test_browse_file_cancellation_returns_empty_string(self, api: DesktopAPI) -> None:
        """When the dialog is cancelled (returns None), browse_file returns ''."""
        wv = _make_webview(dialog_result=None)
        with patch.dict("sys.modules", {"webview": wv}):
            result = api.browse_file()
        assert result == ""

    def test_browse_file_empty_list_returns_empty_string(self, api: DesktopAPI) -> None:
        """When the dialog returns an empty list, browse_file returns ''."""
        wv = _make_webview(dialog_result=[])
        with patch.dict("sys.modules", {"webview": wv}):
            result = api.browse_file()
        assert result == ""

    def test_browse_file_oserror_returns_empty_string(self, api: DesktopAPI) -> None:
        """OSError from create_file_dialog is swallowed; browse_file returns ''."""
        wv = _make_webview()
        wv.active_window().create_file_dialog.side_effect = OSError("dialog unavailable")
        with patch.dict("sys.modules", {"webview": wv}):
            result = api.browse_file()
        assert result == ""

    def test_browse_file_active_window_raises_runtime_error_returns_empty_string(
        self, api: DesktopAPI
    ) -> None:
        """RuntimeError from active_window() is swallowed; browse_file returns ''."""
        wv = _make_webview()
        wv.active_window.side_effect = RuntimeError("no active window")
        with patch.dict("sys.modules", {"webview": wv}):
            result = api.browse_file()
        assert result == ""

    def test_browse_file_unexpected_exception_is_reraised(self, api: DesktopAPI) -> None:
        """Unexpected exceptions (not OSError/RuntimeError/ValueError) must propagate."""
        wv = _make_webview()
        wv.active_window().create_file_dialog.side_effect = MemoryError("OOM")
        with patch.dict("sys.modules", {"webview": wv}):
            with pytest.raises(MemoryError):
                api.browse_file()


# ---------------------------------------------------------------------------
# TestSaveFile
# ---------------------------------------------------------------------------


class TestSaveFile:
    def test_save_file_returns_destination_path(self, api: DesktopAPI) -> None:
        """When the dialog returns a path, save_file returns that exact path."""
        wv = _make_webview(dialog_result=["/out/report.pdf"])
        with patch.dict("sys.modules", {"webview": wv}):
            result = api.save_file(suggested_name="report.pdf")
        assert result == "/out/report.pdf"

    def test_save_file_strips_forward_slash_from_suggested_name(self, api: DesktopAPI) -> None:
        """Forward slashes in suggested_name are stripped before reaching the dialog."""
        wv = _make_webview(dialog_result=["/dest/abc.txt"])
        with patch.dict("sys.modules", {"webview": wv}):
            api.save_file(suggested_name="a/b/c.txt")
        _, kwargs = wv.active_window().create_file_dialog.call_args
        assert kwargs["save_filename"] == "abc.txt"

    def test_save_file_strips_backslash_from_suggested_name(self, api: DesktopAPI) -> None:
        r"""Backslashes in suggested_name are stripped before reaching the dialog."""
        wv = _make_webview(dialog_result=["/dest/abc.txt"])
        with patch.dict("sys.modules", {"webview": wv}):
            api.save_file(suggested_name="a\\b\\c.txt")
        _, kwargs = wv.active_window().create_file_dialog.call_args
        assert kwargs["save_filename"] == "abc.txt"

    def test_save_file_strips_mixed_path_separators_from_suggested_name(
        self, api: DesktopAPI
    ) -> None:
        r"""Both / and \ in suggested_name are stripped, yielding a plain filename."""
        wv = _make_webview(dialog_result=["/dest/out.csv"])
        with patch.dict("sys.modules", {"webview": wv}):
            api.save_file(suggested_name="a/b\\c")
        _, kwargs = wv.active_window().create_file_dialog.call_args
        assert kwargs["save_filename"] == "abc"

    def test_save_file_cancellation_returns_empty_string(self, api: DesktopAPI) -> None:
        """When the dialog is cancelled (returns None), save_file returns ''."""
        wv = _make_webview(dialog_result=None)
        with patch.dict("sys.modules", {"webview": wv}):
            result = api.save_file()
        assert result == ""

    def test_save_file_valueerror_returns_empty_string(self, api: DesktopAPI) -> None:
        """ValueError from create_file_dialog is swallowed; save_file returns ''."""
        wv = _make_webview()
        wv.active_window().create_file_dialog.side_effect = ValueError("bad args")
        with patch.dict("sys.modules", {"webview": wv}):
            result = api.save_file()
        assert result == ""

    def test_save_file_unexpected_exception_is_reraised(self, api: DesktopAPI) -> None:
        """Unexpected exceptions (not OSError/RuntimeError/ValueError) must propagate."""
        wv = _make_webview()
        wv.active_window().create_file_dialog.side_effect = MemoryError("OOM")
        with patch.dict("sys.modules", {"webview": wv}):
            with pytest.raises(MemoryError):
                api.save_file()

    def test_save_file_passes_save_dialog_constant(self, api: DesktopAPI) -> None:
        """save_file must call create_file_dialog with SAVE_DIALOG, not another constant."""
        wv = _make_webview(dialog_result=["/out/file.txt"])
        with patch.dict("sys.modules", {"webview": wv}):
            api.save_file(suggested_name="file.txt", file_types=(("Text", "*.txt"),))
        wv.active_window().create_file_dialog.assert_called_once_with(
            wv.SAVE_DIALOG,
            save_filename="file.txt",
            file_types=(("Text", "*.txt"),),
        )


# ---------------------------------------------------------------------------
# TestOpenPath
# ---------------------------------------------------------------------------


class TestOpenPath:
    def test_open_path_empty_string_returns_false(self, api: DesktopAPI) -> None:
        """open_path('') returns False immediately without spawning any subprocess."""
        with patch("file_organizer.desktop.app.subprocess.run") as mock_run:
            result = api.open_path("")
        assert result is False
        mock_run.assert_not_called()

    def test_open_path_darwin_dispatches_open_r(self, api: DesktopAPI) -> None:
        """On macOS, open_path uses 'open -R <resolved_path>' and returns True."""
        with (
            patch("file_organizer.desktop.app.sys") as mock_sys,
            patch("file_organizer.desktop.app.subprocess.run") as mock_run,
        ):
            mock_sys.platform = "darwin"
            mock_run.return_value = CompletedProcess(args=[], returncode=0)
            result = api.open_path("/some/file.txt")

        assert result is True
        args_passed = mock_run.call_args[0][0]
        assert args_passed[0] == "open"
        assert args_passed[1] == "-R"
        assert len(args_passed) == 3
        assert args_passed[2] == str(Path("/some/file.txt").resolve())

    def test_open_path_win32_dispatches_explorer_select(self, api: DesktopAPI) -> None:
        """On Windows, open_path uses 'explorer /select,<path>' and returns True."""
        with (
            patch("file_organizer.desktop.app.sys") as mock_sys,
            patch("file_organizer.desktop.app.subprocess.run") as mock_run,
        ):
            mock_sys.platform = "win32"
            mock_run.return_value = CompletedProcess(args=[], returncode=0)
            result = api.open_path("/some/file.txt")

        assert result is True
        args_passed = mock_run.call_args[0][0]
        assert args_passed[0] == "explorer"
        assert args_passed[1].startswith("/select,")

    def test_open_path_linux_dispatches_xdg_open(self, api: DesktopAPI, tmp_path: Path) -> None:
        """On Linux, open_path uses 'xdg-open <dir>' for a directory and returns True."""
        with (
            patch("file_organizer.desktop.app.sys") as mock_sys,
            patch("file_organizer.desktop.app.subprocess.run") as mock_run,
        ):
            mock_sys.platform = "linux"
            mock_run.return_value = CompletedProcess(args=[], returncode=0)
            # Use a real directory path so Path.is_dir() returns True without extra mocking.
            result = api.open_path(str(tmp_path))

        assert result is True
        args_passed = mock_run.call_args[0][0]
        assert args_passed[0] == "xdg-open"

    def test_open_path_nonzero_exit_returns_false(self, api: DesktopAPI) -> None:
        """When the subprocess exits with a non-zero code, open_path returns False."""
        with (
            patch("file_organizer.desktop.app.sys") as mock_sys,
            patch("file_organizer.desktop.app.subprocess.run") as mock_run,
        ):
            mock_sys.platform = "darwin"
            mock_run.return_value = CompletedProcess(args=[], returncode=1)
            result = api.open_path("/some/path")

        assert result is False

    def test_open_path_subprocess_oserror_returns_false(self, api: DesktopAPI) -> None:
        """OSError raised by subprocess.run is swallowed; open_path returns False."""
        with (
            patch("file_organizer.desktop.app.sys") as mock_sys,
            patch("file_organizer.desktop.app.subprocess.run") as mock_run,
        ):
            mock_sys.platform = "darwin"
            mock_run.side_effect = OSError("executable not found")
            result = api.open_path("/some/path")

        assert result is False

    def test_open_path_unknown_platform_returns_false(self, api: DesktopAPI) -> None:
        """On an unrecognised platform, open_path returns False without spawning anything."""
        with (
            patch("file_organizer.desktop.app.sys") as mock_sys,
            patch("file_organizer.desktop.app.subprocess.run") as mock_run,
        ):
            # "freebsd13" is not "darwin"/"win32" and doesn't startswith("linux")
            # so all three branches are skipped and open_path returns False.
            mock_sys.platform = "freebsd13"
            result = api.open_path("/some/path")

        assert result is False
        mock_run.assert_not_called()
