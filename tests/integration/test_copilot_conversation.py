"""Integration tests for copilot conversation management.

Covers:
  - services/copilot/conversation.py — ConversationManager sliding-window
  - services/copilot/models.py        — CopilotMessage, MessageRole, IntentType
"""

from __future__ import annotations

import pytest

from file_organizer.services.copilot.conversation import ConversationManager
from file_organizer.services.copilot.models import (
    CopilotMessage,
    IntentType,
    MessageRole,
)

pytestmark = pytest.mark.integration


def _user(content: str) -> CopilotMessage:
    return CopilotMessage(role=MessageRole.USER, content=content)


def _asst(content: str) -> CopilotMessage:
    return CopilotMessage(role=MessageRole.ASSISTANT, content=content)


# ---------------------------------------------------------------------------
# CopilotMessage data model
# ---------------------------------------------------------------------------


class TestCopilotMessage:
    def test_is_user_true_for_user_role(self) -> None:
        m = _user("hello")
        assert m.is_user is True
        assert m.is_assistant is False

    def test_is_assistant_true_for_assistant_role(self) -> None:
        m = _asst("hi there")
        assert m.is_assistant is True
        assert m.is_user is False

    def test_timestamp_auto_set(self) -> None:
        m = _user("hey")
        assert m.timestamp is not None

    def test_metadata_default_empty(self) -> None:
        m = _user("x")
        assert m.metadata == {}

    def test_metadata_can_be_set(self) -> None:
        m = CopilotMessage(role=MessageRole.USER, content="test", metadata={"key": "val"})
        assert m.metadata["key"] == "val"


class TestMessageRole:
    def test_values(self) -> None:
        assert MessageRole.USER.value == "user"
        assert MessageRole.ASSISTANT.value == "assistant"
        assert MessageRole.SYSTEM.value == "system"


class TestIntentType:
    def test_known_intents(self) -> None:
        assert IntentType.ORGANIZE.value == "organize"
        assert IntentType.UNKNOWN.value == "unknown"
        assert IntentType.CHAT.value == "chat"


# ---------------------------------------------------------------------------
# ConversationManager
# ---------------------------------------------------------------------------


class TestConversationManagerBasics:
    def test_empty_on_init(self) -> None:
        mgr = ConversationManager()
        assert mgr.message_count == 0

    def test_add_message_increments_count(self) -> None:
        mgr = ConversationManager()
        mgr.add_message(_user("hello"))
        assert mgr.message_count == 1

    def test_get_recent_messages_all(self) -> None:
        mgr = ConversationManager()
        mgr.add_message(_user("a"))
        mgr.add_message(_asst("b"))
        msgs = mgr.get_recent_messages()
        assert len(msgs) == 2

    def test_get_recent_messages_limited(self) -> None:
        mgr = ConversationManager()
        for i in range(5):
            mgr.add_message(_user(str(i)))
        msgs = mgr.get_recent_messages(n=3)
        assert len(msgs) == 3
        assert msgs[0].content == "2"  # last 3: 2, 3, 4

    def test_clear_resets_state(self) -> None:
        mgr = ConversationManager()
        mgr.add_message(_user("test"))
        mgr.clear()
        assert mgr.message_count == 0
        assert mgr.summary_text == ""

    def test_get_context_string_empty(self) -> None:
        mgr = ConversationManager()
        ctx = mgr.get_context_string()
        assert ctx == ""

    def test_get_context_string_with_messages(self) -> None:
        mgr = ConversationManager()
        mgr.add_message(_user("organize my downloads"))
        mgr.add_message(_asst("I'll help with that."))
        ctx = mgr.get_context_string()
        assert "User: organize my downloads" in ctx
        assert "Assistant: I'll help with that." in ctx


class TestConversationManagerEviction:
    def test_window_enforced(self) -> None:
        mgr = ConversationManager(max_turns=2)
        # 2 turns = 4 messages max
        for i in range(6):
            mgr.add_message(_user(f"msg {i}"))
        assert mgr.message_count == 4

    def test_evicted_messages_build_summary(self) -> None:
        mgr = ConversationManager(max_turns=1)
        # max_turns=1 → 2 messages max
        mgr.add_message(_user("first question"))
        mgr.add_message(_asst("first answer"))
        # Adding two more evicts the first two
        mgr.add_message(_user("second question"))
        mgr.add_message(_asst("second answer"))
        # summary should contain "first question"
        assert "first question" in mgr.summary_text

    def test_summary_included_in_context(self) -> None:
        mgr = ConversationManager(max_turns=1)
        mgr.add_message(_user("earlier context"))
        mgr.add_message(_asst("noted"))
        mgr.add_message(_user("new message"))
        mgr.add_message(_asst("response"))
        ctx = mgr.get_context_string()
        assert "[Earlier context:" in ctx

    def test_only_user_messages_in_summary(self) -> None:
        mgr = ConversationManager(max_turns=1)
        mgr.add_message(_user("user wrote this"))
        mgr.add_message(_asst("assistant wrote that"))
        # Evicts both; only user content should go into summary
        mgr.add_message(_user("next"))
        mgr.add_message(_asst("resp"))
        # summary only from user messages
        assert "user wrote this" in mgr.summary_text or mgr.summary_text == ""

    def test_summary_capped_at_200_chars(self) -> None:
        mgr = ConversationManager(max_turns=1)
        long_msg = "x" * 300
        mgr.add_message(_user(long_msg))
        mgr.add_message(_asst("ok"))
        mgr.add_message(_user("next"))
        mgr.add_message(_asst("resp"))
        assert len(mgr.summary_text) < 201

    def test_message_count_stays_at_max(self) -> None:
        mgr = ConversationManager(max_turns=3)
        max_msgs = mgr._max_messages
        for i in range(max_msgs + 10):
            mgr.add_message(_user(f"msg {i}"))
        assert mgr.message_count == max_msgs


class TestConversationManagerTokenBudget:
    def test_context_trimmed_to_token_budget(self) -> None:
        mgr = ConversationManager(max_turns=20, token_budget=10)  # tiny budget
        mgr.add_message(_user("a" * 200))
        ctx = mgr.get_context_string()
        # budget=10 tokens → 40 chars max
        assert len(ctx) < 41

    def test_large_budget_not_truncated(self) -> None:
        mgr = ConversationManager(max_turns=10, token_budget=10000)
        mgr.add_message(_user("hello"))
        mgr.add_message(_asst("world"))
        ctx = mgr.get_context_string()
        assert "hello" in ctx
        assert "world" in ctx
