"""Copilot rule management and preview system.

Provides CRUD operations for organisation rules, a preview engine for
dry-run evaluation, and YAML-based persistence.
"""

from __future__ import annotations

from file_organizer.services.copilot.rules.executor import ApplyResult, RuleExecutor
from file_organizer.services.copilot.rules.models import (
    Rule,
    RuleAction,
    RuleCondition,
    RuleSet,
)
from file_organizer.services.copilot.rules.preview import PreviewEngine, PreviewResult
from file_organizer.services.copilot.rules.rule_manager import RuleManager

__all__ = [
    "ApplyResult",
    "PreviewEngine",
    "PreviewResult",
    "Rule",
    "RuleAction",
    "RuleCondition",
    "RuleExecutor",
    "RuleManager",
    "RuleSet",
]
