"""Copilot chat interface for AI-assisted file organization.

Provides natural-language interaction with the file organizer, including
intent parsing, multi-turn conversation management, and command execution.
"""

from __future__ import annotations

from file_organizer.services.copilot.conversation import ConversationManager
from file_organizer.services.copilot.engine import CopilotEngine
from file_organizer.services.copilot.executor import CommandExecutor
from file_organizer.services.copilot.intent_parser import IntentParser
from file_organizer.services.copilot.models import (
    CopilotMessage,
    CopilotSession,
    Intent,
    IntentType,
    MessageRole,
)

__all__ = [
    "CommandExecutor",
    "ConversationManager",
    "CopilotEngine",
    "CopilotMessage",
    "CopilotSession",
    "Intent",
    "IntentParser",
    "IntentType",
    "MessageRole",
]
