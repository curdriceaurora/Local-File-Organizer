from unittest.mock import MagicMock, patch

import pytest
from textual.app import App, ComposeResult
from textual.widgets import Input

from file_organizer.services.copilot.models import MessageRole
from file_organizer.tui.app import StatusBar
from file_organizer.tui.copilot_view import CopilotInput, CopilotMessageLog, CopilotView


class MinimalApp(App):
    def compose(self) -> ComposeResult:
        yield CopilotView()
        yield StatusBar()


@pytest.mark.asyncio
async def test_copilot_message_log_add_message():
    app = MinimalApp()
    async with app.run_test():
        log = app.query_one(CopilotMessageLog)
        assert len(log.children) == 1
        # Test USER
        log.add_message(MessageRole.USER, "Hello[world]")
        assert "Hello\\[world]" in str(log.children[-1].render()) or "Hello[world]" in str(
            log.children[-1].render()
        )

        # Test ASSISTANT
        log.add_message(MessageRole.ASSISTANT, "Assistant here")
        assert "Assistant here" in str(log.children[-1].render())

        # Test SYSTEM
        log.add_message(MessageRole.SYSTEM, "System message")
        assert "System message" in str(log.children[-1].render())


@pytest.mark.asyncio
async def test_copilot_view_input_submitted():
    app = MinimalApp()
    async with app.run_test() as pilot:
        view = app.query_one(CopilotView)
        inp = app.query_one(CopilotInput)

        # Blank submit
        inp.value = "   "
        await inp.action_submit()

        # Valid submit
        inp.value = "Test message"
        with patch.object(view, "_process_message") as mock_process:
            # We mock call_from_thread on the view to prevent workers from crashing
            app.call_from_thread = MagicMock(side_effect=lambda func, *args: func(*args))
            # Textual 0.x input action_submit sometimes needs event explicitly called for parent binding
            view.on_input_submitted(Input.Submitted(inp, "Test message"))
            await pilot.pause()

            assert inp.value == ""
            mock_process.assert_called_once_with("Test message")


@pytest.mark.asyncio
async def test_copilot_view_action_clear_input():
    app = MinimalApp()
    async with app.run_test():
        view = app.query_one(CopilotView)
        inp = app.query_one(CopilotInput)

        inp.value = "Test Message"
        view.action_clear_input()
        assert inp.value == ""


@pytest.mark.asyncio
async def test_copilot_view_process_message_success():
    app = MinimalApp()
    async with app.run_test() as pilot:
        view = app.query_one(CopilotView)
        mock_engine = MagicMock()
        mock_engine.chat.return_value = "Response"
        view._get_engine = MagicMock(return_value=mock_engine)

        # Patch call_from_thread to execute immediately on the same thread for test purposes
        app.call_from_thread = MagicMock(side_effect=lambda func, *args: func(*args))

        # Actually execute the thread worker synchronously for test using underlying func
        view._process_message.__wrapped__(view, "Test")
        await pilot.pause()

        log = app.query_one(CopilotMessageLog)
        assert "Response" in str(log.children[-1].render())


@pytest.mark.asyncio
async def test_copilot_view_process_message_error():
    app = MinimalApp()
    async with app.run_test() as pilot:
        view = app.query_one(CopilotView)
        mock_engine = MagicMock()
        mock_engine.chat.side_effect = Exception("Crash")
        view._get_engine = MagicMock(return_value=mock_engine)

        app.call_from_thread = MagicMock(side_effect=lambda func, *args: func(*args))

        view._process_message.__wrapped__(view, "Test")
        await pilot.pause()

        log = app.query_one(CopilotMessageLog)
        assert "Crash" in str(log.children[-1].render())


def test_copilot_view_get_engine():
    with patch("file_organizer.services.copilot.engine.CopilotEngine") as mock_engine_class:
        mock_engine_instance = MagicMock()
        mock_engine_class.return_value = mock_engine_instance

        view = CopilotView()
        engine = view._get_engine()
        # It's an instance of the mock
        assert engine is not None

        # Second call returns the cached instance
        assert view._get_engine() is engine
