"""Tests for file_organizer.services.copilot.models.

Covers MessageRole, IntentType, CopilotMessage, Intent, ExecutionResult,
and CopilotSession dataclasses including all properties and edge cases.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from file_organizer.services.copilot.models import (
    CopilotMessage,
    CopilotSession,
    ExecutionResult,
    Intent,
    IntentType,
    MessageRole,
)

# ------------------------------------------------------------------ #
# MessageRole enum
# ------------------------------------------------------------------ #

@pytest.mark.unit
class TestMessageRole:
    """Tests for the MessageRole enum."""

    def test_user_value(self) -> None:
        assert MessageRole.USER.value == "user"

    def test_assistant_value(self) -> None:
        assert MessageRole.ASSISTANT.value == "assistant"

    def test_system_value(self) -> None:
        assert MessageRole.SYSTEM.value == "system"

    def test_all_members(self) -> None:
        assert set(MessageRole) == {
            MessageRole.USER,
            MessageRole.ASSISTANT,
            MessageRole.SYSTEM,
        }

    def test_from_value(self) -> None:
        assert MessageRole("user") is MessageRole.USER


# ------------------------------------------------------------------ #
# IntentType enum
# ------------------------------------------------------------------ #

@pytest.mark.unit
class TestIntentType:
    """Tests for the IntentType enum."""

    def test_all_members_present(self) -> None:
        expected = {
            "organize", "move", "rename", "find", "undo", "redo",
            "preview", "suggest", "status", "help", "chat", "unknown",
        }
        assert {it.value for it in IntentType} == expected

    @pytest.mark.parametrize(
        "value",
        ["organize", "move", "rename", "find", "undo", "redo",
         "preview", "suggest", "status", "help", "chat", "unknown"],
    )
    def test_from_value_roundtrip(self, value: str) -> None:
        assert IntentType(value).value == value


# ------------------------------------------------------------------ #
# CopilotMessage
# ------------------------------------------------------------------ #

@pytest.mark.unit
class TestCopilotMessage:
    """Tests for CopilotMessage dataclass."""

    def test_basic_creation(self) -> None:
        msg = CopilotMessage(role=MessageRole.USER, content="hello")
        assert msg.role == MessageRole.USER
        assert msg.content == "hello"
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}

    def test_is_user_true(self) -> None:
        msg = CopilotMessage(role=MessageRole.USER, content="hi")
        assert msg.is_user is True
        assert msg.is_assistant is False

    def test_is_assistant_true(self) -> None:
        msg = CopilotMessage(role=MessageRole.ASSISTANT, content="hi")
        assert msg.is_assistant is True
        assert msg.is_user is False

    def test_system_message_is_neither(self) -> None:
        msg = CopilotMessage(role=MessageRole.SYSTEM, content="sys")
        assert msg.is_user is False
        assert msg.is_assistant is False

    def test_custom_timestamp(self) -> None:
        ts = datetime(2025, 1, 1, 12, 0, 0)
        msg = CopilotMessage(role=MessageRole.USER, content="x", timestamp=ts)
        assert msg.timestamp == ts

    def test_metadata_preserved(self) -> None:
        meta = {"key": "value", "num": 42}
        msg = CopilotMessage(role=MessageRole.USER, content="x", metadata=meta)
        assert msg.metadata == meta

    def test_empty_content(self) -> None:
        msg = CopilotMessage(role=MessageRole.USER, content="")
        assert msg.content == ""

    def test_default_metadata_is_independent(self) -> None:
        """Each instance gets its own metadata dict."""
        m1 = CopilotMessage(role=MessageRole.USER, content="a")
        m2 = CopilotMessage(role=MessageRole.USER, content="b")
        m1.metadata["test"] = True
        assert "test" not in m2.metadata


# ------------------------------------------------------------------ #
# Intent
# ------------------------------------------------------------------ #

@pytest.mark.unit
class TestIntent:
    """Tests for Intent dataclass."""

    def test_defaults(self) -> None:
        intent = Intent(intent_type=IntentType.ORGANIZE)
        assert intent.confidence == 0.0
        assert intent.parameters == {}
        assert intent.raw_text == ""

    def test_is_actionable_for_file_actions(self) -> None:
        for it in (IntentType.ORGANIZE, IntentType.MOVE, IntentType.RENAME,
                    IntentType.FIND, IntentType.UNDO, IntentType.REDO,
                    IntentType.PREVIEW, IntentType.SUGGEST):
            intent = Intent(intent_type=it)
            assert intent.is_actionable is True, f"{it} should be actionable"

    def test_is_not_actionable_for_non_file_actions(self) -> None:
        for it in (IntentType.CHAT, IntentType.HELP,
                    IntentType.UNKNOWN, IntentType.STATUS):
            intent = Intent(intent_type=it)
            assert intent.is_actionable is False, f"{it} should NOT be actionable"

    def test_parameters_independent(self) -> None:
        i1 = Intent(intent_type=IntentType.FIND)
        i2 = Intent(intent_type=IntentType.FIND)
        i1.parameters["path"] = "/tmp"
        assert "path" not in i2.parameters

    def test_full_construction(self) -> None:
        intent = Intent(
            intent_type=IntentType.MOVE,
            confidence=0.9,
            parameters={"source": "/a", "destination": "/b"},
            raw_text="move /a to /b",
        )
        assert intent.intent_type == IntentType.MOVE
        assert intent.confidence == 0.9
        assert intent.parameters["source"] == "/a"
        assert intent.raw_text == "move /a to /b"


# ------------------------------------------------------------------ #
# ExecutionResult
# ------------------------------------------------------------------ #

@pytest.mark.unit
class TestExecutionResult:
    """Tests for ExecutionResult dataclass."""

    def test_success_result(self) -> None:
        result = ExecutionResult(success=True, message="Done")
        assert result.success is True
        assert result.message == "Done"
        assert result.details == {}
        assert result.affected_files == []

    def test_failure_result_with_details(self) -> None:
        result = ExecutionResult(
            success=False,
            message="Failed",
            details={"error_code": 42},
            affected_files=["/tmp/a.txt"],
        )
        assert result.success is False
        assert result.details["error_code"] == 42
        assert result.affected_files == ["/tmp/a.txt"]

    def test_defaults_are_independent(self) -> None:
        r1 = ExecutionResult(success=True, message="ok")
        r2 = ExecutionResult(success=True, message="ok")
        r1.affected_files.append("f")
        assert r2.affected_files == []


# ------------------------------------------------------------------ #
# CopilotSession
# ------------------------------------------------------------------ #

@pytest.mark.unit
class TestCopilotSession:
    """Tests for CopilotSession dataclass."""

    def test_empty_session(self) -> None:
        session = CopilotSession()
        assert session.session_id == ""
        assert session.messages == []
        assert session.working_directory is None
        assert isinstance(session.created_at, datetime)
        assert isinstance(session.last_active, datetime)

    def test_turn_count_empty(self) -> None:
        session = CopilotSession()
        assert session.turn_count == 0

    def test_turn_count_with_messages(self) -> None:
        session = CopilotSession(
            messages=[
                CopilotMessage(role=MessageRole.USER, content="hi"),
                CopilotMessage(role=MessageRole.ASSISTANT, content="hello"),
                CopilotMessage(role=MessageRole.USER, content="bye"),
                CopilotMessage(role=MessageRole.SYSTEM, content="sys"),
            ]
        )
        assert session.turn_count == 2

    def test_working_directory(self) -> None:
        session = CopilotSession(working_directory="/home/user")
        assert session.working_directory == "/home/user"

    def test_session_id(self) -> None:
        session = CopilotSession(session_id="abc-123")
        assert session.session_id == "abc-123"

    def test_messages_independent(self) -> None:
        s1 = CopilotSession()
        s2 = CopilotSession()
        s1.messages.append(CopilotMessage(role=MessageRole.USER, content="x"))
        assert len(s2.messages) == 0
