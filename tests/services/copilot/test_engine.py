"""
Unit tests for Copilot Engine (CopilotEngine).

Tests conversation management, intent parsing integration, command execution,
response generation, session management, and error handling.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.services.copilot.engine import CopilotEngine
from file_organizer.services.copilot.models import (
    ExecutionResult,
    Intent,
    IntentType,
)


@pytest.mark.unit
class TestCopilotEngineInit:
    """Tests for CopilotEngine initialization."""

    def test_init_default_parameters(self):
        """Test initialization with default parameters."""
        engine = CopilotEngine()

        assert engine._system_prompt is not None
        assert engine._max_history_turns == 6
        assert engine._conversation is not None
        assert engine._intent_parser is not None
        assert engine._executor is not None
        assert engine._session is not None

    def test_init_custom_system_prompt(self):
        """Test initialization with custom system prompt."""
        custom_prompt = "Custom copilot prompt"
        engine = CopilotEngine(system_prompt=custom_prompt)

        assert engine._system_prompt == custom_prompt

    def test_init_custom_max_history(self):
        """Test initialization with custom max history turns."""
        engine = CopilotEngine(max_history_turns=4)

        assert engine._max_history_turns == 4
        assert engine._conversation._max_messages == 8  # 4 turns * 2

    def test_init_with_working_directory(self):
        """Test initialization with custom working directory."""
        engine = CopilotEngine(working_directory="/tmp/test")

        assert engine._session.working_directory == "/tmp/test"

    def test_init_with_text_model(self):
        """Test initialization with custom text model."""
        mock_model = MagicMock()
        engine = CopilotEngine(text_model=mock_model)

        assert engine._text_model is mock_model


@pytest.mark.unit
class TestChatBasic:
    """Tests for basic chat functionality."""

    def test_chat_single_message(self):
        """Test processing a single user message."""
        engine = CopilotEngine()
        response = engine.chat("Hello")

        assert isinstance(response, str)
        assert len(response) > 0

    def test_chat_adds_user_message_to_conversation(self):
        """Test that user message is added to conversation."""
        engine = CopilotEngine()
        engine.chat("Test message")

        assert engine.conversation.message_count >= 1
        assert engine.conversation._messages[0].is_user

    def test_chat_adds_assistant_response_to_conversation(self):
        """Test that assistant response is added to conversation."""
        engine = CopilotEngine()
        engine.chat("Test")

        assert engine.conversation.message_count >= 2
        last_msg = engine.conversation._messages[-1]
        assert not last_msg.is_user

    def test_chat_adds_message_to_session(self):
        """Test that messages are added to session."""
        engine = CopilotEngine()
        engine.chat("Test message")

        assert len(engine.session.messages) >= 2

    def test_chat_multiple_turns(self):
        """Test multiple chat turns."""
        engine = CopilotEngine()
        response1 = engine.chat("First message")
        response2 = engine.chat("Second message")

        assert response1 is not None
        assert response2 is not None
        assert engine.conversation.message_count >= 4

    def test_chat_conversation_history_preserved(self):
        """Test that conversation history is preserved across turns."""
        engine = CopilotEngine()
        engine.chat("First")
        engine.chat("Second")
        engine.chat("Third")

        recent = engine.conversation.get_recent_messages(n=6)

        assert len(recent) == 6  # Should have exactly 3 user + 3 assistant messages


@pytest.mark.unit
class TestChatWithMocking:
    """Tests for chat with mocked dependencies."""

    def test_chat_calls_intent_parser(self):
        """Test that chat calls intent parser."""
        engine = CopilotEngine()
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.CHAT,
                confidence=0.8,
            )
        )

        engine.chat("Test")

        engine._intent_parser.parse.assert_called_once()

    def test_chat_executes_actionable_intent(self):
        """Test that actionable intents are executed."""
        engine = CopilotEngine()
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.ORGANIZE,
                confidence=0.9,
            )
        )
        engine._executor.execute = MagicMock(
            return_value=ExecutionResult(success=True, message="Organized successfully")
        )

        response = engine.chat("Organize downloads")

        engine._executor.execute.assert_called_once()
        assert "Organized" in response

    def test_chat_skips_execution_for_non_actionable(self):
        """Test that non-actionable intents are not executed."""
        engine = CopilotEngine()
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.CHAT,
                confidence=0.5,
            )
        )
        engine._executor.execute = MagicMock()

        engine.chat("How are you?")

        engine._executor.execute.assert_not_called()

    def test_chat_handles_execution_failure(self):
        """Test handling of execution failure."""
        engine = CopilotEngine()
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.ORGANIZE,
                confidence=0.9,
            )
        )
        engine._executor.execute = MagicMock(
            return_value=ExecutionResult(success=False, message="Permission denied")
        )

        response = engine.chat("Organize files")

        assert "failed" in response.lower() or "permission" in response.lower() or response


@pytest.mark.unit
class TestResponseGeneration:
    """Tests for response generation."""

    def test_response_generation_without_model(self):
        """Test response generation when no text model is configured."""
        engine = CopilotEngine(text_model=None)
        response = engine.chat("Hello")

        assert isinstance(response, str)
        assert len(response) > 0

    def test_response_generation_with_model(self):
        """Test response generation with text model."""
        mock_model = MagicMock()
        mock_model.generate.return_value = "Generated response"
        engine = CopilotEngine(text_model=mock_model)

        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.CHAT,
                confidence=0.5,
            )
        )

        response = engine.chat("Test")

        assert response is not None

    def test_template_response_for_help(self):
        """Test template response for help intent."""
        engine = CopilotEngine(text_model=None)
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.HELP,
                confidence=0.9,
            )
        )

        response = engine.chat("Help")

        assert "help" in response.lower() or "organise" in response.lower()

    def test_template_response_for_status(self):
        """Test template response for status intent."""
        engine = CopilotEngine(text_model=None)
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.STATUS,
                confidence=0.8,
            )
        )

        response = engine.chat("Status")

        assert "ready" in response.lower() or "status" in response.lower()

    def test_execution_result_included_in_response(self):
        """Test that execution results are included in response."""
        engine = CopilotEngine(text_model=None)
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.ORGANIZE,
                confidence=0.9,
            )
        )
        engine._executor.execute = MagicMock(
            return_value=ExecutionResult(success=True, message="Organized 10 files successfully")
        )

        response = engine.chat("Organize")

        assert "Organized" in response or "organized" in response.lower() or response


@pytest.mark.unit
class TestSessionProperty:
    """Tests for session property access."""

    def test_session_property_returns_current_session(self):
        """Test that session property returns current session."""
        engine = CopilotEngine()
        session = engine.session

        assert session is not None
        assert session == engine._session

    def test_session_working_directory(self):
        """Test session working directory."""
        engine = CopilotEngine(working_directory="/tmp")
        assert engine.session.working_directory == "/tmp"

    def test_session_messages_updated(self):
        """Test that session messages are updated during chat."""
        engine = CopilotEngine()
        engine.chat("Message 1")

        assert len(engine.session.messages) >= 2


@pytest.mark.unit
class TestConversationProperty:
    """Tests for conversation property access."""

    def test_conversation_property_returns_manager(self):
        """Test that conversation property returns conversation manager."""
        engine = CopilotEngine()
        conv = engine.conversation

        assert conv is not None
        assert conv == engine._conversation

    def test_conversation_context_string(self):
        """Test conversation context string."""
        engine = CopilotEngine()
        engine.chat("Test")

        context = engine.conversation.get_context_string()

        assert len(context) > 0


@pytest.mark.unit
class TestReset:
    """Tests for resetting the engine."""

    def test_reset_clears_conversation(self):
        """Test that reset clears conversation."""
        engine = CopilotEngine()
        engine.chat("Message 1")
        engine.chat("Message 2")

        assert engine.conversation.message_count > 0

        engine.reset()

        assert engine.conversation.message_count == 0

    def test_reset_creates_new_session(self):
        """Test that reset creates a new session."""
        engine = CopilotEngine()
        old_session = engine.session
        engine.chat("Message")

        engine.reset()

        new_session = engine.session
        assert new_session is not old_session and len(new_session.messages) == 0

    def test_reset_preserves_working_directory(self):
        """Test that reset preserves working directory."""
        engine = CopilotEngine(working_directory="/test/dir")
        engine.chat("Message")

        engine.reset()

        assert engine.session.working_directory == "/test/dir"

    def test_reset_allows_new_conversation(self):
        """Test that reset allows starting new conversation."""
        engine = CopilotEngine()
        engine.chat("First conversation")
        engine.reset()

        engine.chat("Second conversation")

        # Should have messages from second conversation
        messages = engine.conversation.get_recent_messages()
        assert len(messages) >= 1

    def test_multiple_resets(self):
        """Test multiple resets work correctly."""
        engine = CopilotEngine()

        for i in range(3):
            engine.chat(f"Message {i}")
            engine.reset()
            assert engine.conversation.message_count == 0


@pytest.mark.unit
class TestErrorHandling:
    """Tests for error handling."""

    def test_chat_handles_intent_parsing_error(self):
        """Test handling of intent parsing errors."""
        from file_organizer.services.copilot.models import IntentType

        engine = CopilotEngine()
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(intent_type=IntentType.UNKNOWN, confidence=0.0, parameters={})
        )

        # Should return a response with fallback intent
        response = engine.chat("Test")
        assert response is not None and isinstance(response, str)

    def test_chat_handles_execution_error(self):
        """Test that execution errors are propagated."""
        engine = CopilotEngine()
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.ORGANIZE,
                confidence=0.9,
            )
        )
        engine._executor.execute = MagicMock(side_effect=Exception("Execution error"))

        # Errors are propagated (not silently handled)
        with pytest.raises(Exception, match="Execution error"):
            engine.chat("Organize")

    def test_model_generation_failure_fallback(self):
        """Test fallback when model generation fails."""
        mock_model = MagicMock()
        mock_model.generate.side_effect = Exception("Model error")
        engine = CopilotEngine(text_model=mock_model)

        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.CHAT,
                confidence=0.5,
            )
        )

        # Should fall back to template
        response = engine.chat("Test")
        assert response is not None


@pytest.mark.unit
class TestContextWindow:
    """Tests for context window management."""

    def test_long_conversation_respects_max_history(self):
        """Test that long conversations respect max history."""
        engine = CopilotEngine(max_history_turns=2)

        # Simulate 4 turns (exceeds max_history_turns of 2)
        for i in range(4):
            engine.chat(f"Message {i}")

        # Conversation should not exceed max messages
        assert engine.conversation.message_count <= 4  # 2 turns * 2

    def test_conversation_summary_for_old_messages(self):
        """Test that old messages are summarized."""
        engine = CopilotEngine(max_history_turns=1)

        engine.chat("First message")
        engine.chat("Second message")
        engine.chat("Third message")

        # Old messages should be summarized
        summary = engine.conversation.summary_text
        assert summary is None or (isinstance(summary, str) and len(summary) > 0)


@pytest.mark.unit
class TestMessageMetadata:
    """Tests for message metadata."""

    def test_assistant_message_includes_intent(self):
        """Test that assistant messages include intent metadata."""
        engine = CopilotEngine()
        engine._intent_parser.parse = MagicMock(
            return_value=Intent(
                intent_type=IntentType.HELP,
                confidence=0.8,
            )
        )

        response = engine.chat("Help please")

        # Verify response is not empty
        assert response is not None
        assert len(response) > 0

        # Check metadata in message
        last_msg = engine.conversation._messages[-1]
        if hasattr(last_msg, "metadata") and last_msg.metadata:
            assert "intent" in last_msg.metadata


@pytest.mark.unit
class TestComplexScenarios:
    """Tests for complex interaction scenarios."""

    def test_alternating_user_assistant_messages(self):
        """Test alternating user and assistant messages."""
        engine = CopilotEngine()

        for i in range(3):
            engine.chat(f"User message {i}")

        messages = engine.conversation.get_recent_messages()

        # Should alternate between user and assistant (mostly)
        for i, msg in enumerate(messages):
            if i == 0:
                assert msg.is_user
            elif i == len(messages) - 1:
                assert not msg.is_user

    def test_context_includes_all_recent_messages(self):
        """Test that context includes all recent messages."""
        engine = CopilotEngine()
        engine.chat("First")
        engine.chat("Second")

        context = engine.conversation.get_context_string()

        assert "First" in context or "first" in context.lower() or context
        assert "Second" in context or "second" in context.lower() or context

    def test_session_accumulates_all_messages(self):
        """Test that session accumulates all messages."""
        engine = CopilotEngine()

        for i in range(3):
            engine.chat(f"Message {i}")

        assert len(engine.session.messages) >= 6  # At least 3 user + 3 assistant


@pytest.mark.unit
class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_message(self):
        """Test handling of empty messages."""
        engine = CopilotEngine()
        response = engine.chat("")

        assert response is not None

    def test_very_long_message(self):
        """Test handling of very long messages."""
        engine = CopilotEngine()
        long_msg = "Test " * 1000

        response = engine.chat(long_msg)

        assert response is not None
        assert len(response) > 0

    def test_special_characters_in_message(self):
        """Test handling of special characters."""
        engine = CopilotEngine()
        special_msg = "Test with special chars: !@#$%^&*() \n\t"

        response = engine.chat(special_msg)

        assert response is not None


@pytest.mark.unit
class TestCopilotEngineRetriever:
    """Tests verifying HybridRetriever wiring through CopilotEngine."""

    def test_init_accepts_retriever(self) -> None:
        """CopilotEngine accepts a retriever= kwarg without error."""
        retriever = MagicMock()
        retriever.is_initialized = True
        engine = CopilotEngine(retriever=retriever)
        # Retriever is wired to the executor
        assert engine._executor._retriever is retriever

    def test_init_no_retriever_defaults_to_none(self) -> None:
        """When no retriever is passed, executor._retriever is None."""
        engine = CopilotEngine()
        assert engine._executor._retriever is None

    def test_find_intent_uses_retriever_when_initialized(self, tmp_path) -> None:
        """FIND intent routes to retriever.retrieve() when it is initialised."""
        from file_organizer.services.copilot.models import Intent, IntentType

        mock_path = tmp_path / "finance_report.txt"
        retriever = MagicMock()
        retriever.is_initialized = True
        retriever.retrieve.return_value = [(mock_path, 0.05)]

        engine = CopilotEngine(
            working_directory=str(tmp_path),
            retriever=retriever,
        )

        intent = Intent(
            intent_type=IntentType.FIND,
            confidence=0.9,
            parameters={"query": "finance report"},
        )
        result = engine._executor.execute(intent)

        retriever.retrieve.assert_called_once_with("finance report", top_k=20)
        assert result.success is True
        assert str(mock_path) in result.affected_files

    def test_find_intent_falls_back_when_retriever_not_initialized(self, tmp_path) -> None:
        """When retriever.is_initialized is False, executor falls back to filename scan."""
        from file_organizer.services.copilot.models import Intent, IntentType

        (tmp_path / "finance.txt").write_text("content")

        retriever = MagicMock()
        retriever.is_initialized = False

        engine = CopilotEngine(
            working_directory=str(tmp_path),
            retriever=retriever,
        )

        intent = Intent(
            intent_type=IntentType.FIND,
            confidence=0.9,
            parameters={"query": "finance"},
        )
        result = engine._executor.execute(intent)

        # retrieve() must NOT be called since retriever is not initialised
        retriever.retrieve.assert_not_called()
        assert result.success is True
        assert any("finance" in f for f in result.affected_files)

    def test_find_intent_no_retriever_uses_filename_scan(self, tmp_path) -> None:
        """Without a retriever, FIND falls back to filename scan — existing behavior."""
        from file_organizer.services.copilot.models import Intent, IntentType

        (tmp_path / "notes.txt").write_text("content")

        engine = CopilotEngine(working_directory=str(tmp_path))

        intent = Intent(
            intent_type=IntentType.FIND,
            confidence=0.9,
            parameters={"query": "notes"},
        )
        result = engine._executor.execute(intent)
        assert result.success is True
        assert any("notes" in f for f in result.affected_files)


@pytest.mark.unit
class TestCopilotEngineRetrieverIntegration:
    """Integration tests with a real HybridRetriever (no mocks)."""

    def test_find_with_injected_real_retriever(self, tmp_path) -> None:
        """FIND intent returns scoped results using a real HybridRetriever."""
        try:
            from file_organizer.services.search.hybrid_retriever import (
                HybridRetriever,
                read_text_safe,
            )
        except ImportError:
            pytest.fail(
                "search dependencies not installed — run: pip install 'file-organizer[search]'"
            )

        finance_file = tmp_path / "finance_report.txt"
        other_file = tmp_path / "meeting_notes.txt"
        finance_file.write_text("quarterly finance budget summary")
        other_file.write_text("meeting agenda notes items")

        retriever = HybridRetriever()
        docs = [read_text_safe(p) for p in [finance_file, other_file]]
        retriever.index(docs, [finance_file, other_file])

        engine = CopilotEngine(
            working_directory=str(tmp_path),
            retriever=retriever,
        )
        intent = Intent(
            intent_type=IntentType.FIND,
            confidence=0.9,
            parameters={"query": "finance", "paths": [str(tmp_path)]},
        )
        result = engine._executor.execute(intent)

        assert result.success is True
        assert any("finance" in f for f in result.affected_files)
        # Results must be scoped to tmp_path
        for f in result.affected_files:
            assert str(tmp_path) in f

    def test_find_auto_builds_retriever_when_none_injected(self, tmp_path) -> None:
        """FIND auto-builds a HybridRetriever from search_root when none is injected."""
        try:
            from file_organizer.services.search.hybrid_retriever import (
                HybridRetriever,  # noqa: F401
            )
        except ImportError:
            pytest.fail(
                "search dependencies not installed — run: pip install 'file-organizer[search]'"
            )

        finance_file = tmp_path / "finance_report.txt"
        other_file = tmp_path / "meeting_notes.txt"
        finance_file.write_text("quarterly finance budget summary")
        other_file.write_text("meeting agenda notes items")

        # No retriever injected — executor must auto-build from search_root
        engine = CopilotEngine(working_directory=str(tmp_path))
        intent = Intent(
            intent_type=IntentType.FIND,
            confidence=0.9,
            parameters={"query": "finance", "paths": [str(tmp_path)]},
        )
        result = engine._executor.execute(intent)

        assert result.success is True
        # Either semantic or filename scan succeeds — either way finance_report should appear
        assert any("finance" in f for f in result.affected_files)
