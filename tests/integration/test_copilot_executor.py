"""Integration tests for copilot executor.

Covers:
  - services/copilot/executor.py — CommandExecutor, ExecutionResult, Intent, IntentType
"""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.services.copilot.executor import (
    CommandExecutor,
    ExecutionResult,
    Intent,
    IntentType,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# ExecutionResult
# ---------------------------------------------------------------------------


class TestExecutionResult:
    def test_success_result(self) -> None:
        r = ExecutionResult(success=True, message="Done")
        assert r.success is True
        assert r.message == "Done"

    def test_failure_result(self) -> None:
        r = ExecutionResult(success=False, message="Error")
        assert r.success is False

    def test_default_details_empty(self) -> None:
        r = ExecutionResult(success=True, message="ok")
        assert r.details == {}

    def test_default_affected_files_empty(self) -> None:
        r = ExecutionResult(success=True, message="ok")
        assert r.affected_files == []

    def test_custom_details(self) -> None:
        r = ExecutionResult(success=True, message="ok", details={"count": 5})
        assert r.details["count"] == 5

    def test_custom_affected_files(self) -> None:
        r = ExecutionResult(success=True, message="ok", affected_files=["a.txt", "b.txt"])
        assert len(r.affected_files) == 2


# ---------------------------------------------------------------------------
# Intent
# ---------------------------------------------------------------------------


class TestIntent:
    def test_intent_type_stored(self) -> None:
        intent = Intent(intent_type=IntentType.ORGANIZE)
        assert intent.intent_type == IntentType.ORGANIZE

    def test_default_confidence_zero(self) -> None:
        intent = Intent(intent_type=IntentType.FIND)
        assert intent.confidence == 0.0

    def test_custom_confidence(self) -> None:
        intent = Intent(intent_type=IntentType.MOVE, confidence=0.9)
        assert intent.confidence == 0.9

    def test_default_parameters_empty(self) -> None:
        intent = Intent(intent_type=IntentType.RENAME)
        assert intent.parameters == {}

    def test_custom_parameters(self) -> None:
        intent = Intent(
            intent_type=IntentType.MOVE,
            parameters={"source": "a.txt", "dest": "b.txt"},
        )
        assert "source" in intent.parameters

    def test_raw_text_stored(self) -> None:
        intent = Intent(intent_type=IntentType.CHAT, raw_text="hello")
        assert intent.raw_text == "hello"


# ---------------------------------------------------------------------------
# IntentType
# ---------------------------------------------------------------------------


class TestIntentType:
    def test_organize_value(self) -> None:
        assert IntentType.ORGANIZE.value == "organize"

    def test_move_value(self) -> None:
        assert IntentType.MOVE.value == "move"

    def test_rename_value(self) -> None:
        assert IntentType.RENAME.value == "rename"

    def test_find_value(self) -> None:
        assert IntentType.FIND.value == "find"

    def test_undo_value(self) -> None:
        assert IntentType.UNDO.value == "undo"

    def test_redo_value(self) -> None:
        assert IntentType.REDO.value == "redo"

    def test_preview_value(self) -> None:
        assert IntentType.PREVIEW.value == "preview"

    def test_suggest_value(self) -> None:
        assert IntentType.SUGGEST.value == "suggest"

    def test_status_value(self) -> None:
        assert IntentType.STATUS.value == "status"

    def test_help_value(self) -> None:
        assert IntentType.HELP.value == "help"

    def test_chat_value(self) -> None:
        assert IntentType.CHAT.value == "chat"

    def test_unknown_value(self) -> None:
        assert IntentType.UNKNOWN.value == "unknown"


# ---------------------------------------------------------------------------
# CommandExecutor — init
# ---------------------------------------------------------------------------


@pytest.fixture()
def executor(tmp_path: Path) -> CommandExecutor:
    return CommandExecutor(working_directory=str(tmp_path))


class TestCommandExecutorInit:
    def test_default_init(self) -> None:
        ex = CommandExecutor()
        assert ex is not None

    def test_working_directory_accepted(self, tmp_path: Path) -> None:
        ex = CommandExecutor(working_directory=str(tmp_path))
        assert ex is not None


# ---------------------------------------------------------------------------
# CommandExecutor — execute
# ---------------------------------------------------------------------------


class TestCommandExecutorExecute:
    def test_execute_help_intent(self, executor: CommandExecutor) -> None:
        intent = Intent(intent_type=IntentType.HELP, confidence=1.0)
        result = executor.execute(intent)
        assert isinstance(result, ExecutionResult)

    def test_execute_status_intent(self, executor: CommandExecutor) -> None:
        intent = Intent(intent_type=IntentType.STATUS, confidence=0.9)
        result = executor.execute(intent)
        assert isinstance(result, ExecutionResult)

    def test_execute_chat_intent(self, executor: CommandExecutor) -> None:
        intent = Intent(
            intent_type=IntentType.CHAT,
            confidence=0.8,
            raw_text="hello",
        )
        result = executor.execute(intent)
        assert isinstance(result, ExecutionResult)

    def test_execute_unknown_intent(self, executor: CommandExecutor) -> None:
        intent = Intent(intent_type=IntentType.UNKNOWN, confidence=0.0)
        result = executor.execute(intent)
        assert isinstance(result, ExecutionResult)

    def test_execute_suggest_intent(self, executor: CommandExecutor) -> None:
        intent = Intent(
            intent_type=IntentType.SUGGEST,
            confidence=0.7,
            parameters={"path": "/tmp"},
        )
        result = executor.execute(intent)
        assert isinstance(result, ExecutionResult)

    def test_execute_returns_success_bool(self, executor: CommandExecutor) -> None:
        intent = Intent(intent_type=IntentType.HELP)
        result = executor.execute(intent)
        assert result.success is False

    def test_execute_returns_message_str(self, executor: CommandExecutor) -> None:
        intent = Intent(intent_type=IntentType.HELP)
        result = executor.execute(intent)
        assert len(result.message) > 0

    def test_execute_undo_intent_no_history(self, executor: CommandExecutor) -> None:
        intent = Intent(intent_type=IntentType.UNDO, confidence=0.9)
        result = executor.execute(intent)
        assert isinstance(result, ExecutionResult)

    def test_execute_redo_intent_no_history(self, executor: CommandExecutor) -> None:
        intent = Intent(intent_type=IntentType.REDO, confidence=0.9)
        result = executor.execute(intent)
        assert isinstance(result, ExecutionResult)

    def test_execute_preview_intent(self, executor: CommandExecutor, tmp_path: Path) -> None:
        intent = Intent(
            intent_type=IntentType.PREVIEW,
            confidence=0.8,
            parameters={"path": str(tmp_path)},
        )
        result = executor.execute(intent)
        assert isinstance(result, ExecutionResult)

    def test_execute_find_intent(self, executor: CommandExecutor, tmp_path: Path) -> None:
        intent = Intent(
            intent_type=IntentType.FIND,
            confidence=0.9,
            parameters={"query": "*.txt", "path": str(tmp_path)},
        )
        result = executor.execute(intent)
        assert isinstance(result, ExecutionResult)
