"""Tests for DesktopAPI.save_file().

Covers:
- Calls create_file_dialog with SAVE_DIALOG constant
- Forwards suggested_name and file_types exactly
- Strips path separators from suggested_name (F4 security)
- Returns the first confirmed path on save
- Returns empty string when the user cancels (None / empty sequence)
- Returns empty string on exception from create_file_dialog
- Always returns str (never None, list, or tuple)
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestDesktopAPISaveFile:
    """Unit tests for DesktopAPI.save_file()."""

    def _make_mock_webview(self, dialog_result):
        """Return a mock webview module whose active_window().create_file_dialog() returns dialog_result."""
        mock_window = MagicMock()
        mock_window.create_file_dialog.return_value = dialog_result
        mock_webview = MagicMock()
        mock_webview.active_window.return_value = mock_window
        mock_webview.SAVE_DIALOG = 20  # constant from pywebview
        return mock_webview, mock_window

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------

    def test_returns_path_when_user_confirms(self) -> None:
        """save_file() must return the first element of the result tuple."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(("/mock/downloads/settings.json",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().save_file(suggested_name="settings.json")

        assert result == "/mock/downloads/settings.json"

    def test_calls_save_dialog_constant(self) -> None:
        """Must call create_file_dialog with SAVE_DIALOG, not OPEN_DIALOG or FOLDER_DIALOG."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/out.json",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().save_file(
                suggested_name="out.json",
                file_types=(("JSON files (*.json)", "*.json"),),
            )

        mock_window.create_file_dialog.assert_called_once_with(
            mock_webview.SAVE_DIALOG,
            save_filename="out.json",
            file_types=(("JSON files (*.json)", "*.json"),),
        )

    def test_passes_suggested_name_to_dialog(self) -> None:
        """suggested_name must be forwarded as save_filename kwarg."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/out.json",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().save_file(suggested_name="my-export.json")

        _, kwargs = mock_window.create_file_dialog.call_args
        assert kwargs["save_filename"] == "my-export.json"

    def test_passes_file_types_to_dialog(self) -> None:
        """file_types must be forwarded exactly to create_file_dialog."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/out.json",))
        types = (("JSON files (*.json)", "*.json"),)

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().save_file(file_types=types)

        _, kwargs = mock_window.create_file_dialog.call_args
        assert kwargs["file_types"] == types

    # ------------------------------------------------------------------
    # Security: path-separator sanitisation (F4)
    # ------------------------------------------------------------------

    def test_strips_forward_slashes_from_suggested_name(self) -> None:
        """Forward slashes in suggested_name must be removed before forwarding."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/out",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().save_file(suggested_name="../../etc/passwd")

        _, kwargs = mock_window.create_file_dialog.call_args
        assert "/" not in kwargs["save_filename"]
        assert kwargs["save_filename"] == "....etcpasswd"

    def test_strips_backslashes_from_suggested_name(self) -> None:
        """Backslashes in suggested_name must be removed before forwarding."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/out",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().save_file(suggested_name="..\\Windows\\system32\\file")

        _, kwargs = mock_window.create_file_dialog.call_args
        assert "\\" not in kwargs["save_filename"]

    def test_empty_suggested_name_forwarded_as_empty_string(self) -> None:
        """Default empty suggested_name must arrive at the dialog as ''."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, mock_window = self._make_mock_webview(("/mock/out.json",))

        with patch.dict("sys.modules", {"webview": mock_webview}):
            DesktopAPI().save_file()

        _, kwargs = mock_window.create_file_dialog.call_args
        assert kwargs["save_filename"] == ""

    # ------------------------------------------------------------------
    # Cancellation (user closes dialog without confirming)
    # ------------------------------------------------------------------

    def test_returns_empty_string_when_none_returned(self) -> None:
        """webview returns None on cancel — save_file() must return ''."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(None)

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().save_file()

        assert result == ""

    def test_returns_empty_string_when_empty_tuple_returned(self) -> None:
        """webview may return () on cancel — save_file() must return ''."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview(())

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().save_file()

        assert result == ""

    def test_returns_empty_string_when_empty_list_returned(self) -> None:
        """webview may return [] on cancel — save_file() must return ''."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview, _ = self._make_mock_webview([])

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().save_file()

        assert result == ""

    # ------------------------------------------------------------------
    # Exception handling
    # ------------------------------------------------------------------

    def test_returns_empty_string_on_dialog_exception(self) -> None:
        """If create_file_dialog raises, save_file() must return '' gracefully."""
        from file_organizer.desktop.app import DesktopAPI

        mock_webview = MagicMock()
        mock_webview.active_window.return_value.create_file_dialog.side_effect = OSError(
            "dialog not available"
        )
        mock_webview.SAVE_DIALOG = 20

        with patch.dict("sys.modules", {"webview": mock_webview}):
            result = DesktopAPI().save_file()

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
        ]
        for dialog_result, expected in cases:
            mock_webview, _ = self._make_mock_webview(dialog_result)
            with patch.dict("sys.modules", {"webview": mock_webview}):
                result = DesktopAPI().save_file()
            assert isinstance(result, str), (
                f"For {dialog_result!r}: expected str, got {type(result).__name__}"
            )
            assert result == expected, (
                f"For {dialog_result!r}: expected {expected!r}, got {result!r}"
            )
