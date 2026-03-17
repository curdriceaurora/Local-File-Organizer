"""Copilot engine — LLM interaction layer.

Constructs copilot-specific prompts, calls the underlying TextModel, and
parses responses into structured output.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from loguru import logger

from file_organizer.services.copilot.conversation import ConversationManager
from file_organizer.services.copilot.executor import CommandExecutor
from file_organizer.services.copilot.intent_parser import IntentParser
from file_organizer.services.copilot.models import (
    CopilotMessage,
    CopilotSession,
    ExecutionResult,
    Intent,
    MessageRole,
)

if TYPE_CHECKING:
    from file_organizer.interfaces.search import RetrieverProtocol

# Default system prompt that describes the copilot's capabilities.
_SYSTEM_PROMPT = """\
You are File Organizer Copilot, an AI assistant that helps users organise \
their local files.  You can:
- Organise files in a directory by content and type
- Move or rename individual files
- Find files matching a description
- Undo / redo previous operations
- Preview what an organisation pass would do
- Suggest better locations for misplaced files
- Report current status and statistics

When the user asks you to perform an action, respond with a short \
confirmation of what you will do.  Be concise and helpful.  If the request \
is ambiguous, ask a clarifying question.  Never fabricate file paths — only \
reference real paths the user provides or that you discover.
"""

# Token budget: Qwen 2.5 3B has a 4 096-token context window.
_MAX_CONTEXT_TOKENS = 3800  # leave room for generation
_MAX_HISTORY_TURNS = 6


class CopilotEngine:
    """High-level copilot engine.

    Ties together conversation, intent parsing, and command execution.

    Usage::

        engine = CopilotEngine()
        response = engine.chat("Organise my Downloads folder")
    """

    def __init__(
        self,
        *,
        text_model: Any | None = None,
        working_directory: str | None = None,
        system_prompt: str | None = None,
        max_history_turns: int = _MAX_HISTORY_TURNS,
        retriever: RetrieverProtocol | None = None,
    ) -> None:
        """Initialize CopilotEngine.

        Args:
            text_model: Optional LLM for natural-language response generation.
            working_directory: Default directory context for file operations.
            system_prompt: Override the built-in system prompt.
            max_history_turns: Number of conversation turns to retain.
            retriever: Optional :class:`RetrieverProtocol` for semantic FIND
                context gathering.  When supplied and initialised, FIND intents
                use hybrid BM25+vector retrieval instead of filename scanning.
        """
        self._system_prompt = system_prompt or _SYSTEM_PROMPT
        self._max_history_turns = max_history_turns

        self._conversation = ConversationManager(
            max_turns=max_history_turns,
            token_budget=_MAX_CONTEXT_TOKENS,
        )
        self._intent_parser = IntentParser()
        self._executor = CommandExecutor(
            working_directory=working_directory,
            retriever=retriever,
        )

        self._text_model = text_model
        self._session = CopilotSession(working_directory=working_directory)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chat(self, user_input: str) -> str:
        """Process a single user turn and return the assistant response.

        Steps:
            1. Add the user message to conversation history.
            2. Parse the intent from the message + context.
            3. If actionable, execute the intent via ``CommandExecutor``.
            4. Generate a natural-language response.
            5. Return the response text.

        Args:
            user_input: Raw text typed by the user.

        Returns:
            The assistant's reply.
        """
        # 1. Record user message
        user_msg = CopilotMessage(role=MessageRole.USER, content=user_input)
        self._conversation.add_message(user_msg)
        self._session.messages.append(user_msg)

        # 2. Parse intent
        context = self._conversation.get_context_string()
        intent = self._intent_parser.parse(user_input, context=context)
        logger.debug("Parsed intent: {} (conf={:.2f})", intent.intent_type.value, intent.confidence)

        # 3. Execute if actionable
        exec_result: ExecutionResult | None = None
        if intent.is_actionable:
            exec_result = self._executor.execute(intent)
            logger.debug("Execution result: success={}", exec_result.success)

        # 4. Generate response
        response_text = self._generate_response(intent, exec_result)

        # 5. Record assistant message
        assistant_msg = CopilotMessage(
            role=MessageRole.ASSISTANT,
            content=response_text,
            metadata={"intent": intent.intent_type.value},
        )
        self._conversation.add_message(assistant_msg)
        self._session.messages.append(assistant_msg)

        return response_text

    @property
    def session(self) -> CopilotSession:
        """The current copilot session."""
        return self._session

    @property
    def conversation(self) -> ConversationManager:
        """The conversation manager for this engine."""
        return self._conversation

    def reset(self) -> None:
        """Clear conversation history and start a fresh session."""
        self._conversation.clear()
        self._session = CopilotSession(
            working_directory=self._session.working_directory,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _generate_response(
        self,
        intent: Intent,
        exec_result: ExecutionResult | None,
    ) -> str:
        """Generate an assistant response.

        If a ``text_model`` is configured **and** initialised, the LLM is
        called.  Otherwise a deterministic template response is returned so
        the copilot still works without Ollama running.

        Args:
            intent: Parsed intent.
            exec_result: Optional result of command execution.

        Returns:
            Assistant text.
        """
        # Try LLM generation first
        if self._text_model is not None:
            try:
                return self._generate_with_llm(intent, exec_result)
            except Exception as exc:
                logger.warning("LLM generation failed, falling back to template: {}", exc)

        # Template fallback
        return self._generate_template_response(intent, exec_result)

    def _generate_with_llm(
        self,
        intent: Intent,
        exec_result: ExecutionResult | None,
    ) -> str:
        """Call the text model to produce a response.

        Args:
            intent: Parsed intent.
            exec_result: Execution result (may be None).

        Returns:
            LLM-generated text.
        """
        prompt_parts: list[str] = [self._system_prompt, ""]

        # Add recent conversation context
        for msg in self._conversation.get_recent_messages(self._max_history_turns):
            role_label = "User" if msg.is_user else "Assistant"
            prompt_parts.append(f"{role_label}: {msg.content}")

        # Add execution context if available
        if exec_result is not None:
            status = "succeeded" if exec_result.success else "failed"
            prompt_parts.append(
                f"\n[System note: The {intent.intent_type.value} command {status}. "
                f"Result: {exec_result.message}]"
            )

        prompt_parts.append("\nAssistant:")

        prompt = "\n".join(prompt_parts)
        assert self._text_model is not None, "Text model not initialised"
        response: str = self._text_model.generate(prompt, max_tokens=300)
        return response.strip()

    @staticmethod
    def _generate_template_response(
        intent: Intent,
        exec_result: ExecutionResult | None,
    ) -> str:
        """Produce a deterministic template response (no LLM needed).

        Args:
            intent: Parsed intent.
            exec_result: Execution result (may be None).

        Returns:
            Template text.
        """
        if exec_result is not None:
            if exec_result.success:
                return exec_result.message
            return f"Sorry, the operation failed: {exec_result.message}"

        # Non-actionable intents
        templates: dict[str, str] = {
            "help": (
                "I can help you organise files, move or rename them, find "
                "files by description, undo/redo operations, and preview "
                "changes.  Just tell me what you'd like to do!"
            ),
            "status": "Everything is ready. Ask me to organise a folder or find files.",
            "chat": "I'm your file-organisation assistant. How can I help?",
            "unknown": "I'm not sure what you mean. Could you rephrase that?",
        }
        return templates.get(intent.intent_type.value, templates["chat"])
