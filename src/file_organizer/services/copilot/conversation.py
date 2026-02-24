"""Multi-turn conversation management with sliding-window context.

Maintains a bounded message history so that the overall prompt fits inside
the target LLM's context window (default: 4 096 tokens for Qwen 2.5 3B).
Older messages are summarised into a compact context string when the window
overflows.
"""

from __future__ import annotations

from dataclasses import dataclass

from file_organizer.services.copilot.models import CopilotMessage, MessageRole

# Rough token estimate: ~4 characters per token for English text
_CHARS_PER_TOKEN = 4


@dataclass
class _ContextSummary:
    """Compact summary of messages that have been evicted from the window."""

    summary: str = ""
    evicted_count: int = 0


class ConversationManager:
    """Sliding-window conversation context for copilot interactions.

    Keeps the most recent *max_turns* messages in full fidelity.  When
    messages are evicted they are compressed into a one-paragraph summary
    so the LLM still has prior context.

    Args:
        max_turns: Maximum number of turns (user+assistant pairs) to keep.
        token_budget: Approximate token budget for the full context string.
    """

    def __init__(
        self,
        *,
        max_turns: int = 6,
        token_budget: int = 3800,
    ) -> None:
        """Initialize ConversationManager."""
        self._max_messages = max_turns * 2  # user + assistant per turn
        self._token_budget = token_budget
        self._messages: list[CopilotMessage] = []
        self._summary = _ContextSummary()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_message(self, message: CopilotMessage) -> None:
        """Append a message and evict old ones if necessary.

        Args:
            message: The message to record.
        """
        self._messages.append(message)
        self._maybe_evict()

    def get_recent_messages(self, n: int | None = None) -> list[CopilotMessage]:
        """Return the *n* most recent messages (or all if *n* is None).

        Args:
            n: Maximum number of messages to return.

        Returns:
            List of messages, oldest first.
        """
        if n is None:
            return list(self._messages)
        return list(self._messages[-n:])

    def get_context_string(self) -> str:
        """Build a context string suitable for inclusion in an LLM prompt.

        Includes the summary of older messages (if any) followed by the
        full text of recent messages, trimmed to fit the token budget.

        Returns:
            A single string with the conversation context.
        """
        parts: list[str] = []

        if self._summary.summary:
            parts.append(f"[Earlier context: {self._summary.summary}]")

        for msg in self._messages:
            role = "User" if msg.is_user else "Assistant"
            parts.append(f"{role}: {msg.content}")

        context = "\n".join(parts)

        # Rough token-based trim
        max_chars = self._token_budget * _CHARS_PER_TOKEN
        if len(context) > max_chars:
            context = context[-max_chars:]

        return context

    @property
    def message_count(self) -> int:
        """Number of messages currently in the window."""
        return len(self._messages)

    @property
    def summary_text(self) -> str:
        """The summary of evicted messages (may be empty)."""
        return self._summary.summary

    def clear(self) -> None:
        """Reset the conversation completely."""
        self._messages.clear()
        self._summary = _ContextSummary()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _maybe_evict(self) -> None:
        """Evict the oldest messages when the window overflows."""
        while len(self._messages) > self._max_messages:
            evicted = self._messages.pop(0)
            self._update_summary(evicted)

    def _update_summary(self, evicted: CopilotMessage) -> None:
        """Fold an evicted message into the running summary.

        Uses a simple heuristic: keep only the user messages' first
        sentence to maintain topic awareness without blowing up the
        summary size.

        Args:
            evicted: Message being evicted from the window.
        """
        self._summary.evicted_count += 1

        if evicted.role != MessageRole.USER:
            return

        # Take first sentence of the user message
        first_sentence = evicted.content.split(".")[0].strip()
        if not first_sentence:
            return

        if self._summary.summary:
            self._summary.summary += f" | {first_sentence}"
        else:
            self._summary.summary = first_sentence

        # Keep summary compact: cap at ~200 characters
        if len(self._summary.summary) > 200:
            self._summary.summary = self._summary.summary[-200:]
