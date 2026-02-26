"""Tests for file_organizer.tui.copilot_view module.

Covers _escape helper, CopilotMessageLog (add_message role branching,
add_system_note), CopilotInput, CopilotView (on_input_submitted,
_process_message, _get_engine, _set_status, action_clear_input).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Input

from file_organizer.tui.copilot_view import (
    CopilotInput,
    CopilotMessageLog,
    CopilotView,
    _escape,
)

pytestmark = [pytest.mark.unit]


class TestEscapeFunction:
    """Tests for the _escape helper function."""

    def test_escape_single_bracket(self) -> None:
        assert _escape("[bold]") == "\\[bold]"

    def test_escape_multiple_brackets(self) -> None:
        assert _escape("[a] and [b]") == "\\[a] and \\[b]"

    def test_escape_nested_brackets(self) -> None:
        assert _escape("[[nested]]") == "\\[\\[nested]]"

    def test_escape_no_brackets(self) -> None:
        assert _escape("plain text") == "plain text"

    def test_escape_empty_string(self) -> None:
        assert _escape("") == ""

    def test_escape_only_opening_bracket(self) -> None:
        assert _escape("[") == "\\["

    def test_escape_closing_bracket_unchanged(self) -> None:
        assert _escape("]") == "]"

    def test_escape_mixed_content(self) -> None:
        result = _escape("Hello [world], how [are] you?")
        assert result == "Hello \\[world], how \\[are] you?"


class TestCopilotMessageLog:
    """Tests for CopilotMessageLog class attributes and structure."""

    def test_inherits_from_vertical_scroll(self) -> None:
        assert issubclass(CopilotMessageLog, VerticalScroll)

    def test_has_add_message_method(self) -> None:
        assert callable(getattr(CopilotMessageLog, "add_message", None))

    def test_has_add_system_note_method(self) -> None:
        assert callable(getattr(CopilotMessageLog, "add_system_note", None))

    def test_default_css_defined(self) -> None:
        assert "CopilotMessageLog" in CopilotMessageLog.DEFAULT_CSS


class TestCopilotMessageLogAddMessage:
    """Test CopilotMessageLog.add_message role branching (lines 36-45)."""

    def test_user_role(self) -> None:
        from file_organizer.services.copilot.models import MessageRole

        log = CopilotMessageLog()
        log.mount = MagicMock()
        mock_widget = MagicMock()
        with patch("file_organizer.tui.copilot_view.Static", return_value=mock_widget) as mock_static:
            log.add_message(MessageRole.USER, "hello")
        markup = mock_static.call_args[0][0]
        assert "You>" in markup
        assert "bold blue" in markup

    def test_assistant_role(self) -> None:
        from file_organizer.services.copilot.models import MessageRole

        log = CopilotMessageLog()
        log.mount = MagicMock()
        mock_widget = MagicMock()
        with patch("file_organizer.tui.copilot_view.Static", return_value=mock_widget) as mock_static:
            log.add_message(MessageRole.ASSISTANT, "I can help")
        markup = mock_static.call_args[0][0]
        assert "Copilot>" in markup
        assert "bold green" in markup

    def test_system_role(self) -> None:
        from file_organizer.services.copilot.models import MessageRole

        log = CopilotMessageLog()
        log.mount = MagicMock()
        mock_widget = MagicMock()
        with patch("file_organizer.tui.copilot_view.Static", return_value=mock_widget) as mock_static:
            log.add_message(MessageRole.SYSTEM, "system msg")
        markup = mock_static.call_args[0][0]
        assert "dim" in markup

    def test_message_escapes_brackets(self) -> None:
        from file_organizer.services.copilot.models import MessageRole

        log = CopilotMessageLog()
        log.mount = MagicMock()
        mock_widget = MagicMock()
        with patch("file_organizer.tui.copilot_view.Static", return_value=mock_widget) as mock_static:
            log.add_message(MessageRole.USER, "[test]")
        markup = mock_static.call_args[0][0]
        assert "\\[test]" in markup

    def test_scroll_visible_called(self) -> None:
        from file_organizer.services.copilot.models import MessageRole

        log = CopilotMessageLog()
        mock_widget = MagicMock()
        log.mount = MagicMock()
        with patch("file_organizer.tui.copilot_view.Static", return_value=mock_widget):
            log.add_message(MessageRole.USER, "hi")
        mock_widget.scroll_visible.assert_called_once()

    def test_add_system_note(self) -> None:
        log = CopilotMessageLog()
        log.mount = MagicMock()
        mock_widget = MagicMock()
        with patch("file_organizer.tui.copilot_view.Static", return_value=mock_widget) as mock_static:
            log.add_system_note("Welcome!")
        markup = mock_static.call_args[0][0]
        assert "dim italic" in markup


class TestCopilotInput:
    """Tests for CopilotInput class attributes and structure."""

    def test_inherits_from_input(self) -> None:
        assert issubclass(CopilotInput, Input)

    def test_default_css_defined(self) -> None:
        assert "CopilotInput" in CopilotInput.DEFAULT_CSS


class TestCopilotView:
    """Tests for CopilotView class attributes and structure."""

    def test_inherits_from_vertical(self) -> None:
        assert issubclass(CopilotView, Vertical)

    def test_has_bindings(self) -> None:
        assert isinstance(CopilotView.BINDINGS, list)
        assert len(CopilotView.BINDINGS) >= 1

    def test_escape_binding_present(self) -> None:
        keys = [b.key for b in CopilotView.BINDINGS if isinstance(b, Binding)]
        assert "escape" in keys

    def test_has_compose_method(self) -> None:
        assert callable(getattr(CopilotView, "compose", None))

    def test_has_action_clear_input_method(self) -> None:
        assert callable(getattr(CopilotView, "action_clear_input", None))

    def test_default_css_defined(self) -> None:
        assert "CopilotView" in CopilotView.DEFAULT_CSS

    def test_engine_initially_none(self) -> None:
        view = CopilotView()
        assert view._engine is None


# ---------------------------------------------------------------------------
# CopilotView — on_input_submitted (lines 113-128)
# ---------------------------------------------------------------------------


class TestCopilotViewInputSubmitted:
    """Test on_input_submitted handler."""

    def test_empty_input_ignored(self) -> None:
        view = CopilotView()
        event = MagicMock()
        event.value = "   "
        view.query_one = MagicMock()
        view.on_input_submitted(event)
        # _process_message should NOT be called for empty input
        # query_one not called since we return early
        view.query_one.assert_not_called()

    def test_valid_input_clears_and_processes(self) -> None:
        view = CopilotView()
        event = MagicMock()
        event.value = "organise my files"

        mock_input = MagicMock()
        mock_log = MagicMock()

        def query_side(cls):
            if cls is CopilotInput:
                return mock_input
            return mock_log

        view.query_one = query_side
        view._process_message = MagicMock()

        view.on_input_submitted(event)

        # Input should be cleared
        assert mock_input.value == ""
        # User message added to log
        mock_log.add_message.assert_called_once()
        # Process should be triggered
        view._process_message.assert_called_once_with("organise my files")


# ---------------------------------------------------------------------------
# CopilotView — action_clear_input (line 132)
# ---------------------------------------------------------------------------


class TestCopilotViewClearInput:
    """Test action_clear_input."""

    def test_clears_input_value(self) -> None:
        view = CopilotView()
        mock_input = MagicMock()
        mock_input.value = "some text"
        view.query_one = MagicMock(return_value=mock_input)
        view.action_clear_input()
        assert mock_input.value == ""


# ---------------------------------------------------------------------------
# CopilotView — _process_message (lines 134-156)
# ---------------------------------------------------------------------------


class TestCopilotViewProcessMessage:
    """Test _process_message worker."""

    def test_success_path(self) -> None:
        view = CopilotView()
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Here is the result"
        view._engine = mock_engine

        mock_log = MagicMock()
        view.query_one = MagicMock(return_value=mock_log)
        view.call_from_thread = lambda fn, *a, **kw: fn(*a, **kw)
        view._set_status = MagicMock()

        # Call the underlying function (skip @work decorator)
        CopilotView._process_message.__wrapped__(view, "test message")

        mock_engine.chat.assert_called_once_with("test message")
        mock_log.add_message.assert_called_once()

    def test_error_path(self) -> None:
        view = CopilotView()
        mock_engine = MagicMock()
        mock_engine.chat.side_effect = RuntimeError("model failed")
        view._engine = mock_engine

        mock_log = MagicMock()
        view.query_one = MagicMock(return_value=mock_log)
        view.call_from_thread = lambda fn, *a, **kw: fn(*a, **kw)
        view._set_status = MagicMock()

        CopilotView._process_message.__wrapped__(view, "test")

        mock_log.add_system_note.assert_called_once()
        assert "model failed" in mock_log.add_system_note.call_args[0][0]

    def test_status_updated_after_success(self) -> None:
        view = CopilotView()
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "ok"
        view._engine = mock_engine

        view.query_one = MagicMock(return_value=MagicMock())
        view.call_from_thread = lambda fn, *a, **kw: fn(*a, **kw)
        view._set_status = MagicMock()

        CopilotView._process_message.__wrapped__(view, "test")

        view._set_status.assert_called_with("Copilot: ready")


# ---------------------------------------------------------------------------
# CopilotView — _get_engine (lines 158-168)
# ---------------------------------------------------------------------------


class TestCopilotViewGetEngine:
    """Test _get_engine lazy initializer."""

    def test_creates_engine_on_first_call(self) -> None:
        view = CopilotView()
        assert view._engine is None

        mock_engine = MagicMock()
        with patch(
            "file_organizer.services.copilot.engine.CopilotEngine",
            return_value=mock_engine,
        ):
            result = view._get_engine()

        assert result is mock_engine
        assert view._engine is mock_engine

    def test_returns_cached_engine(self) -> None:
        view = CopilotView()
        mock_engine = MagicMock()
        view._engine = mock_engine
        result = view._get_engine()
        assert result is mock_engine


# ---------------------------------------------------------------------------
# CopilotView — _set_status (lines 170-177)
# ---------------------------------------------------------------------------


class TestCopilotViewSetStatus:
    """Test _set_status helper."""

    def test_no_app_doesnt_crash(self) -> None:
        view = CopilotView()
        # Should not raise even without an app
        view._set_status("test status")

    def test_with_app(self) -> None:
        view = CopilotView()
        mock_status = MagicMock()
        mock_app = MagicMock()
        mock_app.query_one.return_value = mock_status
        view._app = mock_app
        view._set_status("ready")

    def test_exception_swallowed(self) -> None:
        view = CopilotView()
        mock_app = MagicMock()
        mock_app.query_one.side_effect = Exception("no StatusBar")
        view._app = mock_app
        # Should not raise
        view._set_status("test")
