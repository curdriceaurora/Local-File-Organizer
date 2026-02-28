"""Data models for the copilot chat interface.

Defines message types, intents, and session state used across all copilot
components.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any


class MessageRole(Enum):
    """Role of a message in the conversation."""

    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class IntentType(Enum):
    """Types of user intents the copilot can recognise."""

    ORGANIZE = "organize"
    MOVE = "move"
    RENAME = "rename"
    FIND = "find"
    UNDO = "undo"
    REDO = "redo"
    PREVIEW = "preview"
    SUGGEST = "suggest"
    STATUS = "status"
    HELP = "help"
    CHAT = "chat"  # General conversation — no file action
    UNKNOWN = "unknown"


@dataclass
class CopilotMessage:
    """A single message in the copilot conversation."""

    role: MessageRole
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_user(self) -> bool:
        """True when message was sent by the user."""
        return self.role == MessageRole.USER

    @property
    def is_assistant(self) -> bool:
        """True when message was sent by the assistant."""
        return self.role == MessageRole.ASSISTANT


@dataclass
class Intent:
    """Parsed intent from a user message.

    Attributes:
        intent_type: The classified intent.
        confidence: 0.0 – 1.0 confidence score.
        parameters: Extracted parameters (paths, names, filters, …).
        raw_text: The original user text.
    """

    intent_type: IntentType
    confidence: float = 0.0
    parameters: dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""

    @property
    def is_actionable(self) -> bool:
        """True when this intent triggers a file-system action."""
        return self.intent_type not in (
            IntentType.CHAT,
            IntentType.HELP,
            IntentType.UNKNOWN,
            IntentType.STATUS,
        )


@dataclass
class ExecutionResult:
    """Result of executing an intent's command."""

    success: bool
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    affected_files: list[str] = field(default_factory=list)


@dataclass
class CopilotSession:
    """Persistent state for a copilot conversation session.

    Attributes:
        session_id: Unique identifier for the session.
        messages: Ordered list of messages exchanged.
        working_directory: Current directory context.
        created_at: Session creation time.
        last_active: Last interaction time.
    """

    session_id: str = ""
    messages: list[CopilotMessage] = field(default_factory=list)
    working_directory: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))
    last_active: datetime = field(default_factory=lambda: datetime.now(tz=UTC))

    @property
    def turn_count(self) -> int:
        """Number of user turns in the session."""
        return sum(1 for m in self.messages if m.is_user)
