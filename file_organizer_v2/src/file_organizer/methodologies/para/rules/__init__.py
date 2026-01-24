"""
PARA Rule Engine Module

This module provides the rule-based categorization engine for the PARA methodology.
It includes rule parsing, condition evaluation, action execution, and conflict resolution.
"""

from .engine import (
    ActionExecutor,
    CategoryScorer,
    ConditionEvaluator,
    ConflictResolver,
    EvaluationContext,
    Rule,
    RuleAction,
    RuleCondition,
    RuleEngine,
    RuleMatchResult,
    RuleParser,
)

__all__ = [
    "RuleEngine",
    "RuleParser",
    "ConditionEvaluator",
    "ActionExecutor",
    "ConflictResolver",
    "CategoryScorer",
    "Rule",
    "RuleCondition",
    "RuleAction",
    "EvaluationContext",
    "RuleMatchResult",
]

__version__ = "1.0.0"
