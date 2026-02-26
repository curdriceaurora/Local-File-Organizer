"""Tests for file_organizer.tui.copilot_view module."""

from __future__ import annotations

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
