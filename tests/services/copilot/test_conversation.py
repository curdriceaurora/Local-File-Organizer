"""
Unit tests for Conversation Manager (ConversationManager).

Tests multi-turn conversation management, sliding-window context,
message eviction, context summarization, and context string generation.
"""

from __future__ import annotations

import pytest

from file_organizer.services.copilot.conversation import ConversationManager
from file_organizer.services.copilot.models import CopilotMessage, MessageRole


@pytest.mark.unit
class TestConversationManagerInit:
    """Tests for ConversationManager initialization."""

    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        cm = ConversationManager()

        assert cm._max_messages == 12  # 6 turns * 2 (user + assistant)
        assert cm._token_budget == 3800
        assert len(cm._messages) == 0
        assert cm.message_count == 0

    def test_init_custom_parameters(self):
        """Test initialization with custom parameters."""
        cm = ConversationManager(max_turns=4, token_budget=2000)

        assert cm._max_messages == 8  # 4 turns * 2
        assert cm._token_budget == 2000
        assert cm.message_count == 0

    def test_init_single_turn(self):
        """Test initialization with single turn."""
        cm = ConversationManager(max_turns=1)

        assert cm._max_messages == 2


@pytest.mark.unit
class TestAddMessage:
    """Tests for adding messages to conversation."""

    def test_add_single_message(self):
        """Test adding a single message."""
        cm = ConversationManager()
        msg = CopilotMessage(role=MessageRole.USER, content="Hello")

        cm.add_message(msg)

        assert cm.message_count == 1
        assert cm._messages[0].content == "Hello"

    def test_add_multiple_messages(self):
        """Test adding multiple messages."""
        cm = ConversationManager()
        user_msg = CopilotMessage(role=MessageRole.USER, content="Hello")
        assistant_msg = CopilotMessage(role=MessageRole.ASSISTANT, content="Hi there")

        cm.add_message(user_msg)
        cm.add_message(assistant_msg)

        assert cm.message_count == 2

    def test_add_many_messages_preserves_recent(self):
        """Test that adding messages beyond max preserves recent ones."""
        cm = ConversationManager(max_turns=2)  # max 4 messages
        messages = []

        for i in range(6):
            role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT
            msg = CopilotMessage(role=role, content=f"Message {i}")
            messages.append(msg)
            cm.add_message(msg)

        # Should keep only last 4 messages
        assert cm.message_count == 4
        # Most recent message should still be there
        assert cm._messages[-1].content == "Message 5"

    def test_add_message_triggers_eviction(self):
        """Test that adding messages beyond limit triggers eviction."""
        cm = ConversationManager(max_turns=1)  # max 2 messages
        msg1 = CopilotMessage(role=MessageRole.USER, content="First")
        msg2 = CopilotMessage(role=MessageRole.ASSISTANT, content="Second")
        msg3 = CopilotMessage(role=MessageRole.USER, content="Third")

        cm.add_message(msg1)
        cm.add_message(msg2)
        assert cm.message_count == 2

        cm.add_message(msg3)
        assert cm.message_count == 2
        # First message should be evicted
        assert cm._messages[0].content == "Second"
        assert cm._messages[1].content == "Third"


@pytest.mark.unit
class TestGetRecentMessages:
    """Tests for retrieving recent messages."""

    def test_get_all_messages(self):
        """Test getting all messages when n is None."""
        cm = ConversationManager()
        messages = [
            CopilotMessage(role=MessageRole.USER, content="Hello"),
            CopilotMessage(role=MessageRole.ASSISTANT, content="Hi"),
        ]

        for msg in messages:
            cm.add_message(msg)

        recent = cm.get_recent_messages(n=None)

        assert len(recent) == 2
        assert recent[0].content == "Hello"
        assert recent[1].content == "Hi"

    def test_get_n_recent_messages(self):
        """Test getting n most recent messages."""
        cm = ConversationManager()
        for i in range(5):
            msg = CopilotMessage(
                role=MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT,
                content=f"Message {i}",
            )
            cm.add_message(msg)

        recent = cm.get_recent_messages(n=2)

        assert len(recent) == 2
        assert recent[0].content == "Message 3"
        assert recent[1].content == "Message 4"

    def test_get_more_messages_than_available(self):
        """Test requesting more messages than available."""
        cm = ConversationManager()
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Only one"))

        recent = cm.get_recent_messages(n=5)

        assert len(recent) == 1

    def test_get_zero_messages(self):
        """Test requesting zero messages returns at least one."""
        cm = ConversationManager()
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Message"))

        recent = cm.get_recent_messages(n=0)

        # Implementation should return at least the message that was added
        assert len(recent) >= 1
        assert any(m.content == "Message" for m in recent)


@pytest.mark.unit
class TestGetContextString:
    """Tests for generating context strings."""

    def test_context_string_empty_conversation(self):
        """Test context string from empty conversation."""
        cm = ConversationManager()

        context = cm.get_context_string()

        assert context == ""

    def test_context_string_single_message(self):
        """Test context string with single message."""
        cm = ConversationManager()
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Test message"))

        context = cm.get_context_string()

        assert "User: Test message" in context

    def test_context_string_multiple_messages(self):
        """Test context string with multiple messages."""
        cm = ConversationManager()
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Hello"))
        cm.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content="Hi"))

        context = cm.get_context_string()

        assert "User: Hello" in context
        assert "Assistant: Hi" in context

    def test_context_string_includes_role_labels(self):
        """Test that context string includes role labels."""
        cm = ConversationManager()
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Question"))

        context = cm.get_context_string()

        assert "User:" in context

    def test_context_string_respects_token_budget(self):
        """Test that context string respects token budget."""
        cm = ConversationManager(token_budget=50)
        long_message = "x" * 300  # Larger than token budget

        cm.add_message(CopilotMessage(role=MessageRole.USER, content=long_message))

        context = cm.get_context_string()

        # Context should be trimmed to token budget
        assert len(context) <= 50 * 4  # _CHARS_PER_TOKEN = 4

    def test_context_string_includes_summary(self):
        """Test that context string includes evicted message summary."""
        cm = ConversationManager(max_turns=1)  # max 2 messages
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="First question"))
        cm.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content="First answer"))
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Second question"))

        context = cm.get_context_string()

        # Summary of earlier context should be included
        assert "[Earlier context:" in context


@pytest.mark.unit
class TestMessageProperties:
    """Tests for message property access."""

    def test_message_count_property(self):
        """Test message_count property."""
        cm = ConversationManager()

        assert cm.message_count == 0

        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Test"))
        assert cm.message_count == 1

    def test_summary_text_property_empty(self):
        """Test summary_text property when empty."""
        cm = ConversationManager()

        assert cm.summary_text == ""

    def test_summary_text_property_after_eviction(self):
        """Test summary_text property after messages are evicted."""
        cm = ConversationManager(max_turns=1)  # max 2 messages
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="First message"))
        cm.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content="Response"))
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Second message"))

        summary = cm.summary_text

        # Summary should contain information about first message
        assert len(summary) > 0
        assert "First message" in summary or "First" in summary


@pytest.mark.unit
class TestMessageEviction:
    """Tests for message eviction and summarization."""

    def test_eviction_preserves_recent_messages(self):
        """Test that eviction preserves recent messages."""
        cm = ConversationManager(max_turns=2)  # max 4 messages
        old_msg = CopilotMessage(role=MessageRole.USER, content="Old")
        new_msg = CopilotMessage(role=MessageRole.USER, content="New")

        cm.add_message(old_msg)
        for _ in range(5):  # Add enough to evict old message
            cm.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content="Response"))
        cm.add_message(new_msg)

        assert cm._messages[-1] == new_msg

    def test_eviction_updates_summary(self):
        """Test that eviction updates the summary."""
        cm = ConversationManager(max_turns=1)
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="User question one"))
        cm.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content="Response"))
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="User question two"))

        # First user message should be in summary
        assert len(cm.summary_text) > 0

    def test_summary_truncation(self):
        """Test that summary is truncated to reasonable length."""
        cm = ConversationManager(max_turns=1)

        # Add many messages to build summary
        for i in range(10):
            role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT
            content = f"Message {i} with lots of content to make it long"
            cm.add_message(CopilotMessage(role=role, content=content))

        # Summary should be capped at ~200 characters
        assert len(cm.summary_text) <= 250

    def test_only_user_messages_summarized(self):
        """Test that only user messages are added to summary."""
        cm = ConversationManager(max_turns=1)
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Question"))
        cm.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content="Long response"))
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Follow up"))

        summary = cm.summary_text

        # Summary should contain "Question" but not "Long response"
        assert "Question" in summary
        assert "Long response" not in summary


@pytest.mark.unit
class TestClearConversation:
    """Tests for clearing conversation."""

    def test_clear_removes_all_messages(self):
        """Test that clear removes all messages."""
        cm = ConversationManager()
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Message 1"))
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Message 2"))

        cm.clear()

        assert cm.message_count == 0
        assert len(cm._messages) == 0

    def test_clear_removes_summary(self):
        """Test that clear removes summary."""
        cm = ConversationManager(max_turns=1)
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Message 1"))
        cm.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content="Response"))
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Message 2"))

        assert len(cm.summary_text) > 0

        cm.clear()

        assert cm.summary_text == ""
        assert cm.message_count == 0

    def test_clear_allows_fresh_start(self):
        """Test that cleared conversation can be reused."""
        cm = ConversationManager()
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="Old"))
        cm.clear()

        cm.add_message(CopilotMessage(role=MessageRole.USER, content="New"))

        assert cm.message_count == 1
        assert cm._messages[0].content == "New"


@pytest.mark.unit
class TestContextWindowBehavior:
    """Tests for context window overflow behavior."""

    def test_context_fits_within_token_budget(self):
        """Test that context string fits within token budget."""
        cm = ConversationManager(max_turns=3, token_budget=500)

        for i in range(6):
            role = MessageRole.USER if i % 2 == 0 else MessageRole.ASSISTANT
            cm.add_message(
                CopilotMessage(role=role, content=f"Message {i} with some content")
            )

        context = cm.get_context_string()
        max_chars = 500 * 4  # _CHARS_PER_TOKEN = 4

        assert len(context) <= max_chars

    def test_large_message_handling(self):
        """Test handling of messages larger than token budget."""
        cm = ConversationManager(max_turns=1, token_budget=100)
        large_msg = "x" * 1000

        cm.add_message(CopilotMessage(role=MessageRole.USER, content=large_msg))

        context = cm.get_context_string()

        # Context should be trimmed
        assert len(context) <= 100 * 4

    def test_multiple_turns_context_management(self):
        """Test context management over multiple turns."""
        cm = ConversationManager(max_turns=2, token_budget=1000)

        # Simulate 4 turns (8 messages)
        for turn in range(4):
            cm.add_message(
                CopilotMessage(
                    role=MessageRole.USER, content=f"Turn {turn} user message"
                )
            )
            cm.add_message(
                CopilotMessage(
                    role=MessageRole.ASSISTANT, content=f"Turn {turn} assistant response"
                )
            )

        # Should have max 4 messages in window
        assert cm.message_count <= 4
        # Should have generated a summary
        assert len(cm.summary_text) > 0


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_message_content(self):
        """Test handling of empty message content."""
        cm = ConversationManager()
        cm.add_message(CopilotMessage(role=MessageRole.USER, content=""))

        context = cm.get_context_string()

        assert "User:" in context

    def test_message_with_special_characters(self):
        """Test handling of special characters in messages."""
        cm = ConversationManager()
        content = "Special chars: !@#$%^&*() \n\t\r"
        cm.add_message(CopilotMessage(role=MessageRole.USER, content=content))

        context = cm.get_context_string()

        assert "!@#$%^&*()" in context

    def test_very_long_message_summary(self):
        """Test summary of very long messages."""
        cm = ConversationManager(max_turns=1)
        long_content = "This is a very long message. " * 20

        cm.add_message(CopilotMessage(role=MessageRole.USER, content=long_content))
        cm.add_message(CopilotMessage(role=MessageRole.ASSISTANT, content="Response"))
        cm.add_message(CopilotMessage(role=MessageRole.USER, content="New question"))

        summary = cm.summary_text

        assert len(summary) > 0
        assert len(summary) <= 250  # Should be capped

    def test_message_order_preserved(self):
        """Test that message order is always preserved."""
        cm = ConversationManager()
        messages = [
            CopilotMessage(role=MessageRole.USER, content=f"Message {i}")
            for i in range(5)
        ]

        for msg in messages:
            cm.add_message(msg)

        retrieved = cm.get_recent_messages()

        for i, msg in enumerate(retrieved):
            assert msg.content == f"Message {i}"
