"""Unit and integration coverage tests for file_organizer.tui.copilot_view.

Targets 100% statement and branch coverage for CopilotView and its sub-widgets.
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from textual.widgets import Input

from file_organizer.services.copilot.models import MessageRole
from file_organizer.tui.copilot_view import (
    CopilotInput,
    CopilotMessageLog,
    CopilotView,
    _escape,
)

pytestmark = pytest.mark.unit


def _create_view_with_mocks() -> tuple[CopilotView, MagicMock, MagicMock, MagicMock]:
    """Helper to create a CopilotView with its children and app mocked."""
    view = CopilotView()

    # Mock panels/inputs
    mock_log = MagicMock(spec=CopilotMessageLog)
    mock_input = MagicMock(spec=CopilotInput)

    widgets = {
        CopilotMessageLog: mock_log,
        CopilotInput: mock_input,
    }

    def mock_query_one(widget_type):
        return widgets.get(widget_type, MagicMock())

    view.query_one = MagicMock(side_effect=mock_query_one)

    # Mock app property
    mock_app = MagicMock()
    app_prop = PropertyMock(return_value=mock_app)
    type(view).app = app_prop

    # Force call_from_thread to execute synchronously in tests
    mock_app.call_from_thread = lambda func, *args, **kwargs: func(*args, **kwargs)

    return view, mock_log, mock_input, mock_app


# --- Panel & Input Tests ---


def test_copilot_message_log_add_message() -> None:
    """Verify CopilotMessageLog formats user, assistant, and other message roles correctly."""
    log = CopilotMessageLog()

    # Mock mount to intercept widgets
    mounted_widgets = []

    def mock_mount(widget):
        mounted_widgets.append(widget)

    with patch.object(log, "mount", side_effect=mock_mount):
        # 1. User message
        log.add_message(MessageRole.USER, "hello [world]")
        assert len(mounted_widgets) == 1
        assert "You>" in mounted_widgets[0].renderable
        assert "\\[world]" in mounted_widgets[0].renderable  # check escaping

        # 2. Assistant message
        log.add_message(MessageRole.ASSISTANT, "hi there")
        assert len(mounted_widgets) == 2
        assert "Copilot>" in mounted_widgets[1].renderable

        # 3. Fallback/Other role
        log.add_message("system", "alert")
        assert len(mounted_widgets) == 3
        assert "You>" not in mounted_widgets[2].renderable
        assert "Copilot>" not in mounted_widgets[2].renderable


def test_copilot_message_log_add_system_note() -> None:
    """Verify system note mounting."""
    log = CopilotMessageLog()
    mounted_widgets = []

    with patch.object(log, "mount", side_effect=lambda w: mounted_widgets.append(w)):
        log.add_system_note("This is a system [warning]")
        assert len(mounted_widgets) == 1
        assert "italic" in mounted_widgets[0].renderable
        assert "\\[warning]" in mounted_widgets[0].renderable


# --- CopilotView Tests ---


def test_copilot_view_initialization() -> None:
    """Verify copilot view default engine state."""
    view = CopilotView()
    assert view._engine is None


def test_copilot_view_compose() -> None:
    """Verify compose yields expected widgets."""
    view = CopilotView()
    widgets = list(view.compose())
    assert len(widgets) == 3
    assert widgets[0].id == "copilot-header"
    assert isinstance(widgets[1], CopilotMessageLog)
    assert isinstance(widgets[2], CopilotInput)


def test_copilot_view_on_mount() -> None:
    """Verify on_mount focuses input and adds system note."""
    view, mock_log, mock_input, _ = _create_view_with_mocks()
    view.on_mount()
    mock_log.add_system_note.assert_called_once()
    mock_input.focus.assert_called_once()


def test_copilot_view_on_input_submitted_empty() -> None:
    """Verify on_input_submitted returns immediately for empty inputs."""
    view, mock_log, mock_input, _ = _create_view_with_mocks()

    # Setup mock event with empty value
    mock_event = MagicMock(spec=Input.Submitted)
    mock_event.value = "   "

    with patch.object(view, "_process_message") as mock_process:
        view.on_input_submitted(mock_event)
        mock_input.value = ""  # should not be touched
        mock_log.add_message.assert_not_called()
        mock_process.assert_not_called()


def test_copilot_view_on_input_submitted_valid() -> None:
    """Verify on_input_submitted clears input and triggers processing."""
    view, mock_log, mock_input, _ = _create_view_with_mocks()

    mock_event = MagicMock(spec=Input.Submitted)
    mock_event.value = "organise downloads"

    with patch.object(view, "_process_message") as mock_process:
        view.on_input_submitted(mock_event)

        # Verify input value is cleared
        assert mock_input.value == ""

        # Verify user message added
        mock_log.add_message.assert_called_once_with(MessageRole.USER, "organise downloads")

        # Verify background processor triggered
        mock_process.assert_called_once_with("organise downloads")


def test_copilot_view_action_clear_input() -> None:
    """Verify clear input action clears the input widget value."""
    view, _, mock_input, _ = _create_view_with_mocks()
    mock_input.value = "unsaved text"
    view.action_clear_input()
    assert mock_input.value == ""


def test_copilot_view_process_message_success() -> None:
    """Verify message processing updates log with assistant response and sets status."""
    view, mock_log, _, _ = _create_view_with_mocks()

    mock_engine = MagicMock()
    mock_engine.chat.return_value = "Done organizing."
    view._engine = mock_engine

    with patch.object(view, "_set_status") as mock_status:
        view._process_message.__wrapped__(view, "do something")

        mock_engine.chat.assert_called_once_with("do something")
        mock_log.add_message.assert_called_once_with(MessageRole.ASSISTANT, "Done organizing.")
        mock_status.assert_called_once_with("Copilot: ready")


def test_copilot_view_process_message_failure() -> None:
    """Verify message processing failures are logged as system notes."""
    view, mock_log, _, _ = _create_view_with_mocks()

    mock_engine = MagicMock()
    mock_engine.chat.side_effect = RuntimeError("API key invalid")
    view._engine = mock_engine

    with patch.object(view, "_set_status") as mock_status:
        view._process_message.__wrapped__(view, "hello")

        mock_log.add_system_note.assert_called_once_with("Error: API key invalid")
        mock_status.assert_called_once_with("Copilot: ready")


def test_copilot_view_get_engine() -> None:
    """Verify lazy initialization of CopilotEngine."""
    view = CopilotView()
    assert view._engine is None

    mock_engine_class = MagicMock()
    with patch("file_organizer.services.copilot.engine.CopilotEngine", mock_engine_class):
        # First call -> initializes
        engine = view._get_engine()
        assert view._engine is not None
        mock_engine_class.assert_called_once()

        # Second call -> returns cached
        engine2 = view._get_engine()
        assert engine2 is engine
        assert mock_engine_class.call_count == 1


def test_copilot_view_status_bar_updates() -> None:
    """Verify status updates resolve cleanly or log on failure."""
    view, _, _, mock_app = _create_view_with_mocks()

    # 1. Success
    mock_status_bar = MagicMock()
    mock_app.query_one.return_value = mock_status_bar
    view._set_status("Ready")
    mock_status_bar.set_status.assert_called_once_with("Ready")

    # 2. Exception fallback
    mock_app.query_one.side_effect = Exception("No status bar")
    with patch("file_organizer.tui.copilot_view.logger") as mock_logger:
        view._set_status("Ready")
        mock_logger.debug.assert_called_once()


# --- Helper Function Tests ---


def test_escape_helper() -> None:
    """Verify _escape helper correctly escapes rich brackets."""
    assert _escape("hello") == "hello"
    assert _escape("hello [world]") == "hello \\[world]"
