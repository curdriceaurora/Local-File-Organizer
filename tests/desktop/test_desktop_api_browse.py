"""Tests for DesktopAPI — the Python class exposed to the webview JS context.

Covers:
- browse_directory() calls webview.active_window().create_file_dialog(FOLDER_DIALOG)
- Returns the first selected path on confirm
- Returns empty string when user cancels (None or empty list returned by webview)
- Returns empty string on exception from create_file_dialog
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestDesktopAPIBrowseDirectory:
    """Unit tests for DesktopAPI.browse_directory()."""

    def _make_mock_webview(self, dialog_result):
        """Return a mock webview module whose active_window().create_file_dialog() returns dialog_result."""
        mock_window = MagicMock()
        mock_window.create_file_dialog.return_value = dialog_result
        mock_webview = MagicMock()
        mock_webview.active_window.return_value = mock_window
        mock_webview.FOLDER_DIALOG = 1  # constant from pywebview
        return mock_webview, mock_window

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_returns_first_path_when_user_selects(self) -> None:
        """browse_directory() must return the first element of the result tuple."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(("/Users/rahul/Documents",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            api = DesktopAPI()
            result = api.browse_directory()

        assert result == "/Users/rahul/Documents"

    def test_calls_folder_dialog_constant(self) -> None:
        """Must call create_file_dialog with FOLDER_DIALOG, not a file dialog."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/test",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            api = DesktopAPI()
            api.browse_directory()

        mock_window.create_file_dialog.assert_called_once_with(mock_webview.FOLDER_DIALOG)

    def test_calls_active_window(self) -> None:
        """Must use the currently active webview window, not a hardcoded reference."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(("/mock/test",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            api = DesktopAPI()
            api.browse_directory()

        mock_webview.active_window.assert_called_once()

    # ------------------------------------------------------------------
    # Cancellation (user closes dialog without selecting)
    # ------------------------------------------------------------------

    def test_returns_empty_string_when_none_returned(self) -> None:
        """webview returns None when user cancels — browse_directory() must return ''."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(None)

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().browse_directory()

        assert result == ""

    def test_returns_empty_string_when_empty_tuple_returned(self) -> None:
        """webview may return () on cancel — browse_directory() must return ''."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(())

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().browse_directory()

        assert result == ""

    def test_returns_empty_string_when_empty_list_returned(self) -> None:
        """webview may return [] on cancel — browse_directory() must return ''."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview([])

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().browse_directory()

        assert result == ""

    # ------------------------------------------------------------------
    # Exception handling
    # ------------------------------------------------------------------

    def test_returns_empty_string_on_dialog_exception(self) -> None:
        """If create_file_dialog raises, browse_directory() must return '' gracefully."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview = MagicMock()
        mock_webview.active_window.return_value.create_file_dialog.side_effect = RuntimeError(
            "dialog unavailable"
        )
        mock_webview.FOLDER_DIALOG = 1

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().browse_directory()

        assert result == ""

    # ------------------------------------------------------------------
    # Return type contract
    # ------------------------------------------------------------------

    def test_always_returns_string(self) -> None:
        """Return type must always be str (never None, list, or tuple)."""
        from file_organizer.desktop.app import DesktopAPI

        cases: list[tuple[object, str]] = [
            (("/mock/path",), "/mock/path"),
            (None, ""),
            ((), ""),
            ([], ""),
        ]
        for dialog_result, expected in cases:
            mock_webview, _ = self._make_mock_webview(dialog_result)
            with patch.dict("sys.modules", {"webview": mock_webview}):
                result = DesktopAPI().browse_directory()
            assert result == expected, (
                f"For {dialog_result!r}: expected {expected!r}, got {result!r}"
            )
