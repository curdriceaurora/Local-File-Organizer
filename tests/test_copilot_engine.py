"""Tests for copilot engine, conversation manager, intent parser, and executor."""

from __future__ import annotations
import pytest

from pathlib import Path
from unittest.mock import MagicMock

from file_organizer.services.copilot.conversation import ConversationManager
from file_organizer.services.copilot.engine import CopilotEngine
from file_organizer.services.copilot.executor import CommandExecutor
from file_organizer.services.copilot.intent_parser import IntentParser
from file_organizer.services.copilot.models import (
    CopilotMessage,
    CopilotSession,
    ExecutionResult,
    Intent,
    IntentType,
    MessageRole,
)

# ---------------------------------------------------------------------------
# IntentParser
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestIntentParser:
    def setup_method(self) -> None:
        self.parser = IntentParser()

    def test_organize_intent(self) -> None:
        intent = self.parser.parse("Organize my Downloads folder")
        assert intent.intent_type == IntentType.ORGANIZE
        assert intent.confidence >= 0.8

    def test_undo_intent(self) -> None:
        intent = self.parser.parse("undo the last operation")
        assert intent.intent_type == IntentType.UNDO
        assert intent.confidence >= 0.9

    def test_redo_intent(self) -> None:
        intent = self.parser.parse("redo please")
        assert intent.intent_type == IntentType.REDO

    def test_find_intent(self) -> None:
        intent = self.parser.parse("find my report.pdf")
        assert intent.intent_type == IntentType.FIND
        assert "query" in intent.parameters

    def test_move_intent(self) -> None:
        intent = self.parser.parse("move ~/report.pdf to ~/Documents")
        assert intent.intent_type == IntentType.MOVE

    def test_rename_intent(self) -> None:
        intent = self.parser.parse('rename ~/old.txt to "new.txt"')
        assert intent.intent_type == IntentType.RENAME

    def test_preview_intent(self) -> None:
        intent = self.parser.parse("preview what would happen")
        assert intent.intent_type == IntentType.PREVIEW

    def test_suggest_intent(self) -> None:
        intent = self.parser.parse("suggest a better location for this file")
        assert intent.intent_type == IntentType.SUGGEST

    def test_help_intent(self) -> None:
        intent = self.parser.parse("what can you do?")
        assert intent.intent_type == IntentType.HELP

    def test_status_intent(self) -> None:
        intent = self.parser.parse("show me the status")
        assert intent.intent_type == IntentType.STATUS

    def test_chat_fallback(self) -> None:
        intent = self.parser.parse("hello there")
        assert intent.intent_type == IntentType.CHAT
        assert intent.confidence <= 0.5

    def test_empty_input(self) -> None:
        intent = self.parser.parse("")
        assert intent.intent_type == IntentType.UNKNOWN

    def test_path_extraction(self) -> None:
        intent = self.parser.parse("organize ~/Downloads ~/Organized")
        assert "paths" in intent.parameters
        assert len(intent.parameters["paths"]) == 2

    def test_quoted_args(self) -> None:
        intent = self.parser.parse('rename "old name" to "new name"')
        assert "quoted_args" in intent.parameters

    def test_dry_run_detection(self) -> None:
        intent = self.parser.parse("organize ~/Downloads --dry-run")
        assert intent.parameters.get("dry_run") is True


# ---------------------------------------------------------------------------
# ConversationManager
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConversationManager:
    def test_add_and_retrieve(self) -> None:
        mgr = ConversationManager(max_turns=3)
        msg = CopilotMessage(role=MessageRole.USER, content="hello")
        mgr.add_message(msg)
        assert mgr.message_count == 1
        assert mgr.get_recent_messages()[0].content == "hello"

    def test_eviction(self) -> None:
        mgr = ConversationManager(max_turns=2)  # 4 messages max
        for i in range(6):
            role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT
            mgr.add_message(CopilotMessage(role=role, content=f"msg-{i}"))
        assert mgr.message_count == 4
        assert mgr.summary_text != ""

    def test_get_recent_n(self) -> None:
        mgr = ConversationManager()
        for i in range(5):
            mgr.add_message(CopilotMessage(role=MessageRole.USER, content=f"m{i}"))
        recent = mgr.get_recent_messages(2)
        assert len(recent) == 2
        assert recent[0].content == "m3"
        assert recent[1].content == "m4"

    def test_context_string(self) -> None:
        mgr = ConversationManager()
        mgr.add_message(CopilotMessage(role=MessageRole.USER, content="organize files"))
        mgr.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content="Sure!"))
        ctx = mgr.get_context_string()
        assert "User: organize files" in ctx
        assert "Assistant: Sure!" in ctx

    def test_clear(self) -> None:
        mgr = ConversationManager()
        mgr.add_message(CopilotMessage(role=MessageRole.USER, content="test"))
        mgr.clear()
        assert mgr.message_count == 0
        assert mgr.summary_text == ""


# ---------------------------------------------------------------------------
# CommandExecutor
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCommandExecutor:
    def test_find_files(self, tmp_path: Path) -> None:
        (tmp_path / "report.pdf").write_text("content")
        (tmp_path / "notes.txt").write_text("content")

        executor = CommandExecutor(working_directory=str(tmp_path))
        intent = Intent(
            intent_type=IntentType.FIND,
            parameters={"query": "report", "paths": [str(tmp_path)]},
        )
        result = executor.execute(intent)
        assert result.success is True
        assert "report" in result.message.lower()

    def test_find_no_results(self, tmp_path: Path) -> None:
        executor = CommandExecutor(working_directory=str(tmp_path))
        intent = Intent(
            intent_type=IntentType.FIND,
            parameters={"query": "nonexistent-xyz"},
        )
        result = executor.execute(intent)
        assert result.success is True
        assert "No files" in result.message

    def test_move_missing_params(self) -> None:
        executor = CommandExecutor()
        intent = Intent(intent_type=IntentType.MOVE, parameters={})
        result = executor.execute(intent)
        assert result.success is False

    def test_rename_missing_params(self) -> None:
        executor = CommandExecutor()
        intent = Intent(intent_type=IntentType.RENAME, parameters={})
        result = executor.execute(intent)
        assert result.success is False

    def test_rename_file(self, tmp_path: Path) -> None:
        (tmp_path / "old.txt").write_text("content")
        executor = CommandExecutor(working_directory=str(tmp_path))
        intent = Intent(
            intent_type=IntentType.RENAME,
            parameters={"target": str(tmp_path / "old.txt"), "new_name": "new.txt"},
        )
        result = executor.execute(intent)
        assert result.success is True
        assert (tmp_path / "new.txt").exists()

    def test_unknown_intent(self) -> None:
        executor = CommandExecutor()
        intent = Intent(intent_type=IntentType.CHAT)
        result = executor.execute(intent)
        assert result.success is False

    def test_suggest_missing_paths(self) -> None:
        executor = CommandExecutor()
        intent = Intent(intent_type=IntentType.SUGGEST, parameters={})
        result = executor.execute(intent)
        assert result.success is False


# ---------------------------------------------------------------------------
# CopilotEngine
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCopilotEngine:
    def test_chat_help(self) -> None:
        engine = CopilotEngine()
        response = engine.chat("help")
        assert "organise" in response.lower() or "organize" in response.lower()

    def test_chat_unknown(self) -> None:
        engine = CopilotEngine()
        response = engine.chat("xyzzy garble")
        assert len(response) > 0

    def test_session_tracking(self) -> None:
        engine = CopilotEngine()
        engine.chat("hello")
        engine.chat("help")
        assert engine.session.turn_count == 2
        assert len(engine.session.messages) == 4  # 2 user + 2 assistant

    def test_reset(self) -> None:
        engine = CopilotEngine()
        engine.chat("hello")
        engine.reset()
        assert engine.session.turn_count == 0
        assert engine.conversation.message_count == 0

    def test_with_mock_model(self) -> None:
        mock_model = MagicMock()
        mock_model.generate.return_value = "Sure, I can help with that!"
        engine = CopilotEngine(text_model=mock_model)
        response = engine.chat("what can you do?")
        assert mock_model.generate.called or len(response) > 0

    def test_template_fallback_on_model_error(self) -> None:
        mock_model = MagicMock()
        mock_model.generate.side_effect = RuntimeError("Model crashed")
        engine = CopilotEngine(text_model=mock_model)
        response = engine.chat("what can you do?")
        # Should fallback to template
        assert len(response) > 0


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestCopilotModels:
    def test_message_is_user(self) -> None:
        msg = CopilotMessage(role=MessageRole.USER, content="hi")
        assert msg.is_user is True
        assert msg.is_assistant is False

    def test_intent_actionable(self) -> None:
        assert Intent(intent_type=IntentType.ORGANIZE).is_actionable is True
        assert Intent(intent_type=IntentType.MOVE).is_actionable is True
        assert Intent(intent_type=IntentType.CHAT).is_actionable is False
        assert Intent(intent_type=IntentType.HELP).is_actionable is False
        assert Intent(intent_type=IntentType.UNKNOWN).is_actionable is False

    def test_execution_result(self) -> None:
        r = ExecutionResult(success=True, message="Done", affected_files=["a.txt"])
        assert r.success is True
        assert len(r.affected_files) == 1

    def test_session_turn_count(self) -> None:
        session = CopilotSession()
        session.messages.append(CopilotMessage(role=MessageRole.USER, content="a"))
        session.messages.append(CopilotMessage(role=MessageRole.ASSISTANT, content="b"))
        session.messages.append(CopilotMessage(role=MessageRole.USER, content="c"))
        assert session.turn_count == 2
