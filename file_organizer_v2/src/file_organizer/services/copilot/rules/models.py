"""Data models for the copilot rule system.

Rules describe conditions and actions for automatic file organisation.
A ``RuleSet`` groups related rules with a shared scope and priority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ConditionType(Enum):
    """Types of conditions a rule can match on."""

    EXTENSION = "extension"
    NAME_PATTERN = "name_pattern"
    SIZE_GREATER = "size_greater"
    SIZE_LESS = "size_less"
    CONTENT_CONTAINS = "content_contains"
    MODIFIED_BEFORE = "modified_before"
    MODIFIED_AFTER = "modified_after"
    PATH_MATCHES = "path_matches"


class ActionType(Enum):
    """Types of actions a rule can perform."""

    MOVE = "move"
    RENAME = "rename"
    TAG = "tag"
    CATEGORIZE = "categorize"
    DELETE = "delete"
    ARCHIVE = "archive"
    COPY = "copy"


@dataclass
class RuleCondition:
    """A single condition that a file must satisfy.

    Args:
        condition_type: The type of check to perform.
        value: The comparison value (extension string, glob pattern, size in bytes, etc.).
        negate: If True, the condition is inverted (NOT match).
    """

    condition_type: ConditionType
    value: str
    negate: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for YAML output."""
        d: dict[str, Any] = {
            "type": self.condition_type.value,
            "value": self.value,
        }
        if self.negate:
            d["negate"] = True
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleCondition:
        """Deserialize from a dict."""
        return cls(
            condition_type=ConditionType(data["type"]),
            value=str(data["value"]),
            negate=bool(data.get("negate", False)),
        )


@dataclass
class RuleAction:
    """An action to execute when all conditions are met.

    Args:
        action_type: What to do with the matched file.
        destination: Target path or pattern (for move/copy/archive).
        parameters: Extra parameters specific to the action type.
    """

    action_type: ActionType
    destination: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for YAML output."""
        d: dict[str, Any] = {
            "type": self.action_type.value,
        }
        if self.destination:
            d["destination"] = self.destination
        if self.parameters:
            d["parameters"] = self.parameters
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleAction:
        """Deserialize from a dict."""
        return cls(
            action_type=ActionType(data["type"]),
            destination=data.get("destination", ""),
            parameters=data.get("parameters", {}),
        )


@dataclass
class Rule:
    """A single organisation rule with conditions and an action.

    All conditions must be satisfied (AND logic) for the action to fire.

    Args:
        name: Human-readable rule identifier.
        description: Optional explanation of the rule's purpose.
        conditions: List of conditions (all must match).
        action: The action to perform.
        enabled: Whether the rule is active.
        priority: Higher values execute first (default 0).
        created_at: When the rule was created.
    """

    name: str
    description: str = ""
    conditions: list[RuleCondition] = field(default_factory=list)
    action: RuleAction = field(default_factory=lambda: RuleAction(action_type=ActionType.MOVE))
    enabled: bool = True
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for YAML output."""
        return {
            "name": self.name,
            "description": self.description,
            "conditions": [c.to_dict() for c in self.conditions],
            "action": self.action.to_dict(),
            "enabled": self.enabled,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        """Deserialize from a dict."""
        conditions = [RuleCondition.from_dict(c) for c in data.get("conditions", [])]
        action_data = data.get("action", {"type": "move"})
        return cls(
            name=data.get("name", "unnamed"),
            description=data.get("description", ""),
            conditions=conditions,
            action=RuleAction.from_dict(action_data),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 0),
        )


@dataclass
class RuleSet:
    """A named collection of rules.

    Args:
        name: Identifier for this rule set.
        description: Purpose of this rule set.
        rules: The rules in evaluation order.
        version: Schema version for forward compatibility.
    """

    name: str = "default"
    description: str = ""
    rules: list[Rule] = field(default_factory=list)
    version: str = "1.0"

    @property
    def enabled_rules(self) -> list[Rule]:
        """Return only enabled rules sorted by priority (descending)."""
        return sorted(
            [r for r in self.rules if r.enabled],
            key=lambda r: r.priority,
            reverse=True,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict for YAML output."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "rules": [r.to_dict() for r in self.rules],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RuleSet:
        """Deserialize from a dict."""
        rules = [Rule.from_dict(r) for r in data.get("rules", [])]
        return cls(
            name=data.get("name", "default"),
            description=data.get("description", ""),
            rules=rules,
            version=data.get("version", "1.0"),
        )
