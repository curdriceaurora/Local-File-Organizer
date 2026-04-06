"""Tests for DesktopAPI.browse_file().

Covers:
- Calls create_file_dialog with OPEN_DIALOG constant
- Returns the first selected path on confirm
- Forwards file_types argument exactly
- Returns empty string when the user cancels (None / empty sequence)
- Returns empty string on exception from create_file_dialog
- Always returns str (never None, list, or tuple)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestDesktopAPIBrowseFile:
    """Unit tests for DesktopAPI.browse_file()."""

    def _make_mock_webview(self, dialog_result):
        """Return a mock webview module whose active_window().create_file_dialog() returns dialog_result."""
        mock_window = MagicMock()
        mock_window.create_file_dialog.return_value = dialog_result
        mock_webview = MagicMock()
        mock_webview.active_window.return_value = mock_window
        mock_webview.OPEN_DIALOG = 10  # constant from pywebview
        return mock_webview, mock_window

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_returns_first_path_when_user_selects(self) -> None:
        """browse_file() must return the first element of the result tuple."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(("/mock/documents/config.json",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().browse_file()

        assert result == "/mock/documents/config.json"

    def test_calls_open_dialog_constant(self) -> None:
        """Must call create_file_dialog with OPEN_DIALOG, not a folder or save dialog."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/file.json",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().browse_file()

        mock_window.create_file_dialog.assert_called_once_with(
            mock_webview.OPEN_DIALOG,
            file_types=(),
        )

    def test_calls_active_window(self) -> None:
        """Must use the currently active webview window, not a hardcoded reference."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(("/mock/file.json",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().browse_file()

        mock_webview.active_window.assert_called_once()

    def test_passes_file_types_to_dialog(self) -> None:
        """Non-empty file_types must be forwarded to create_file_dialog exactly."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/file.json",))
        types = (("JSON files (*.json)", "*.json"),)

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().browse_file(file_types=types)

        mock_window.create_file_dialog.assert_called_once_with(
            mock_webview.OPEN_DIALOG,
            file_types=types,
        )

    def test_empty_file_types_forwarded_as_empty_tuple(self) -> None:
        """Default (empty) file_types must be forwarded as () — shows all files."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/file.json",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().browse_file()

        _, kwargs = mock_window.create_file_dialog.call_args
        assert kwargs["file_types"] == ()

    # ------------------------------------------------------------------
    # Cancellation (user closes dialog without selecting)
    # ------------------------------------------------------------------

    @pytest.mark.parametrize("cancel_value", [None, (), []])
    def test_returns_empty_string_on_cancel(self, cancel_value) -> None:
        """browse_file() must return '' for all cancel return values (None, (), [])."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(cancel_value)

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().browse_file()

        assert result == ""

    # ------------------------------------------------------------------
    # Exception handling
    # ------------------------------------------------------------------

    def test_returns_empty_string_on_dialog_exception(self) -> None:
        """If create_file_dialog raises, browse_file() must return '' gracefully."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview = MagicMock()
        mock_webview.active_window.return_value.create_file_dialog.side_effect = RuntimeError(
            "dialog unavailable"
        )
        mock_webview.OPEN_DIALOG = 10

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().browse_file()

        assert result == ""

    # ------------------------------------------------------------------
    # Return type contract
    # ------------------------------------------------------------------

    def test_always_returns_string(self) -> None:
        """Return type must always be str (never None, list, or tuple)."""
        from file_organizer.desktop.app import DesktopAPI

        cases: list[tuple[object, str]] = [
            (("/mock/path.json",), "/mock/path.json"),
            (None, ""),
            ((), ""),
            ([], ""),
        ]
        for dialog_result, expected in cases:
            mock_webview, _ = self._make_mock_webview(dialog_result)
            with patch.dict("sys.modules", {"webview": mock_webview}):
                result = DesktopAPI().browse_file()
            assert isinstance(result, str), (
                f"For {dialog_result!r}: expected str, got {type(result).__name__}"
            )
            assert result == expected, (
                f"For {dialog_result!r}: expected {expected!r}, got {result!r}"
            )
