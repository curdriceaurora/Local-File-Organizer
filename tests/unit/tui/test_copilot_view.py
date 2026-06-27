from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from file_organizer.services.copilot.models import MessageRole
from file_organizer.tui.copilot_view import CopilotInput, CopilotMessageLog, CopilotView


def _capture_log_mounts(log: CopilotMessageLog) -> list[object]:
    mounted: list[object] = []
    log.mount = MagicMock(side_effect=mounted.append)
    return mounted


def test_copilot_message_log_add_message():
    log = CopilotMessageLog()
    mounted = _capture_log_mounts(log)

    log.add_message(MessageRole.USER, "Hello[world]")
    assert "Hello\\[world]" in str(mounted[-1].render()) or "Hello[world]" in str(
        mounted[-1].render()
    )

    log.add_message(MessageRole.ASSISTANT, "Assistant here")
    assert "Assistant here" in str(mounted[-1].render())

    log.add_message(MessageRole.SYSTEM, "System message")
    assert "System message" in str(mounted[-1].render())


def test_copilot_view_input_submitted():
    view = CopilotView()
    inp = MagicMock(spec=CopilotInput)
    inp.value = "   "
    log = MagicMock(spec=CopilotMessageLog)
    view.query_one = MagicMock(side_effect=[inp, log])

    view.on_input_submitted(SimpleNamespace(value="   "))

    log.add_message.assert_not_called()

    view.query_one = MagicMock(side_effect=[inp, log])
    with patch.object(view, "_process_message") as mock_process:
        view.on_input_submitted(SimpleNamespace(value="Test message"))

    assert inp.value == ""
    log.add_message.assert_called_once_with(MessageRole.USER, "Test message")
    mock_process.assert_called_once_with("Test message")


def test_copilot_view_action_clear_input():
    view = CopilotView()
    inp = MagicMock(spec=CopilotInput)
    inp.value = "Test Message"
    view.query_one = MagicMock(return_value=inp)

    view.action_clear_input()

    assert inp.value == ""


def test_copilot_view_process_message_success():
    view = CopilotView()
    log = CopilotMessageLog()
    mounted = _capture_log_mounts(log)
    mock_engine = MagicMock()
    mock_engine.chat.return_value = "Response"
    mock_app = MagicMock()
    mock_app.call_from_thread = MagicMock(side_effect=lambda func, *args: func(*args))
    view.query_one = MagicMock(return_value=log)
    view._get_engine = MagicMock(return_value=mock_engine)

    with patch.object(CopilotView, "app", new_callable=PropertyMock, return_value=mock_app):
        CopilotView._process_message.__wrapped__(view, "Test")

    assert "Response" in str(mounted[-1].render())


def test_copilot_view_process_message_error():
    view = CopilotView()
    log = CopilotMessageLog()
    mounted = _capture_log_mounts(log)
    mock_engine = MagicMock()
    mock_engine.chat.side_effect = Exception("Crash")
    mock_app = MagicMock()
    mock_app.call_from_thread = MagicMock(side_effect=lambda func, *args: func(*args))
    view.query_one = MagicMock(return_value=log)
    view._get_engine = MagicMock(return_value=mock_engine)

    with patch.object(CopilotView, "app", new_callable=PropertyMock, return_value=mock_app):
        CopilotView._process_message.__wrapped__(view, "Test")

    assert "Crash" in str(mounted[-1].render())


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
