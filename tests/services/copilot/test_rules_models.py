"""Tests for file_organizer.services.copilot.rules.models.

Covers ConditionType, ActionType, RuleCondition, RuleAction, Rule, and
RuleSet including serialization/deserialization round-trips and edge cases.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from file_organizer.services.copilot.rules.models import (
    ActionType,
    ConditionType,
    Rule,
    RuleAction,
    RuleCondition,
    RuleSet,
)

# ------------------------------------------------------------------ #
# Enum coverage
# ------------------------------------------------------------------ #

class TestConditionType:
    """Tests for the ConditionType enum."""

    def test_all_members(self) -> None:
        expected = {
            "extension", "name_pattern", "size_greater", "size_less",
            "content_contains", "modified_before", "modified_after",
            "path_matches",
        }
        assert {ct.value for ct in ConditionType} == expected

    def test_from_value(self) -> None:
        assert ConditionType("extension") is ConditionType.EXTENSION


class TestActionType:
    """Tests for the ActionType enum."""

    def test_all_members(self) -> None:
        expected = {
            "move", "rename", "tag", "categorize",
            "delete", "archive", "copy",
        }
        assert {at.value for at in ActionType} == expected

    def test_from_value(self) -> None:
        assert ActionType("move") is ActionType.MOVE


# ------------------------------------------------------------------ #
# RuleCondition
# ------------------------------------------------------------------ #

class TestRuleCondition:
    """Tests for RuleCondition dataclass."""

    def test_basic_creation(self) -> None:
        cond = RuleCondition(
            condition_type=ConditionType.EXTENSION, value=".pdf"
        )
        assert cond.condition_type == ConditionType.EXTENSION
        assert cond.value == ".pdf"
        assert cond.negate is False

    def test_negate_flag(self) -> None:
        cond = RuleCondition(
            condition_type=ConditionType.EXTENSION, value=".tmp", negate=True
        )
        assert cond.negate is True

    def test_to_dict_without_negate(self) -> None:
        cond = RuleCondition(
            condition_type=ConditionType.NAME_PATTERN, value="*.log"
        )
        d = cond.to_dict()
        assert d == {"type": "name_pattern", "value": "*.log"}
        assert "negate" not in d

    def test_to_dict_with_negate(self) -> None:
        cond = RuleCondition(
            condition_type=ConditionType.SIZE_GREATER, value="1024", negate=True
        )
        d = cond.to_dict()
        assert d["negate"] is True
        assert d["type"] == "size_greater"
        assert d["value"] == "1024"

    def test_from_dict_minimal(self) -> None:
        cond = RuleCondition.from_dict({"type": "extension", "value": ".py"})
        assert cond.condition_type == ConditionType.EXTENSION
        assert cond.value == ".py"
        assert cond.negate is False

    def test_from_dict_with_negate(self) -> None:
        cond = RuleCondition.from_dict(
            {"type": "path_matches", "value": "/tmp/*", "negate": True}
        )
        assert cond.negate is True
        assert cond.condition_type == ConditionType.PATH_MATCHES

    def test_from_dict_value_coerced_to_str(self) -> None:
        cond = RuleCondition.from_dict({"type": "size_less", "value": 2048})
        assert cond.value == "2048"
        assert isinstance(cond.value, str)

    def test_roundtrip(self) -> None:
        original = RuleCondition(
            condition_type=ConditionType.CONTENT_CONTAINS,
            value="TODO",
            negate=True,
        )
        restored = RuleCondition.from_dict(original.to_dict())
        assert restored.condition_type == original.condition_type
        assert restored.value == original.value
        assert restored.negate == original.negate


# ------------------------------------------------------------------ #
# RuleAction
# ------------------------------------------------------------------ #

class TestRuleAction:
    """Tests for RuleAction dataclass."""

    def test_basic_creation(self) -> None:
        action = RuleAction(action_type=ActionType.MOVE)
        assert action.action_type == ActionType.MOVE
        assert action.destination == ""
        assert action.parameters == {}

    def test_with_destination(self) -> None:
        action = RuleAction(
            action_type=ActionType.COPY, destination="/backup"
        )
        assert action.destination == "/backup"

    def test_with_parameters(self) -> None:
        action = RuleAction(
            action_type=ActionType.TAG,
            parameters={"tags": ["important", "work"]},
        )
        assert action.parameters["tags"] == ["important", "work"]

    def test_to_dict_minimal(self) -> None:
        action = RuleAction(action_type=ActionType.DELETE)
        d = action.to_dict()
        assert d == {"type": "delete"}
        assert "destination" not in d
        assert "parameters" not in d

    def test_to_dict_with_destination(self) -> None:
        action = RuleAction(
            action_type=ActionType.ARCHIVE, destination="/archive"
        )
        d = action.to_dict()
        assert d["destination"] == "/archive"

    def test_to_dict_with_parameters(self) -> None:
        action = RuleAction(
            action_type=ActionType.CATEGORIZE,
            parameters={"category": "work"},
        )
        d = action.to_dict()
        assert d["parameters"] == {"category": "work"}

    def test_to_dict_full(self) -> None:
        action = RuleAction(
            action_type=ActionType.MOVE,
            destination="/sorted",
            parameters={"overwrite": True},
        )
        d = action.to_dict()
        assert d == {
            "type": "move",
            "destination": "/sorted",
            "parameters": {"overwrite": True},
        }

    def test_from_dict_minimal(self) -> None:
        action = RuleAction.from_dict({"type": "rename"})
        assert action.action_type == ActionType.RENAME
        assert action.destination == ""
        assert action.parameters == {}

    def test_from_dict_full(self) -> None:
        action = RuleAction.from_dict({
            "type": "copy",
            "destination": "/backup",
            "parameters": {"preserve_metadata": True},
        })
        assert action.action_type == ActionType.COPY
        assert action.destination == "/backup"
        assert action.parameters["preserve_metadata"] is True

    def test_roundtrip(self) -> None:
        original = RuleAction(
            action_type=ActionType.ARCHIVE,
            destination="/cold-storage",
            parameters={"compress": True},
        )
        restored = RuleAction.from_dict(original.to_dict())
        assert restored.action_type == original.action_type
        assert restored.destination == original.destination
        assert restored.parameters == original.parameters

    def test_parameters_independent(self) -> None:
        a1 = RuleAction(action_type=ActionType.TAG)
        a2 = RuleAction(action_type=ActionType.TAG)
        a1.parameters["x"] = 1
        assert "x" not in a2.parameters


# ------------------------------------------------------------------ #
# Rule
# ------------------------------------------------------------------ #

class TestRule:
    """Tests for Rule dataclass."""

    def test_basic_creation(self) -> None:
        rule = Rule(name="test-rule")
        assert rule.name == "test-rule"
        assert rule.description == ""
        assert rule.conditions == []
        assert rule.action.action_type == ActionType.MOVE
        assert rule.enabled is True
        assert rule.priority == 0
        assert isinstance(rule.created_at, datetime)

    def test_full_creation(self) -> None:
        cond = RuleCondition(
            condition_type=ConditionType.EXTENSION, value=".pdf"
        )
        action = RuleAction(
            action_type=ActionType.MOVE, destination="/docs"
        )
        rule = Rule(
            name="pdf-rule",
            description="Move PDFs to docs",
            conditions=[cond],
            action=action,
            enabled=True,
            priority=10,
        )
        assert rule.priority == 10
        assert len(rule.conditions) == 1
        assert rule.action.destination == "/docs"

    def test_to_dict(self) -> None:
        cond = RuleCondition(
            condition_type=ConditionType.EXTENSION, value=".log"
        )
        action = RuleAction(
            action_type=ActionType.DELETE
        )
        rule = Rule(
            name="cleanup",
            description="Remove logs",
            conditions=[cond],
            action=action,
            enabled=False,
            priority=5,
        )
        d = rule.to_dict()
        assert d["name"] == "cleanup"
        assert d["description"] == "Remove logs"
        assert d["enabled"] is False
        assert d["priority"] == 5
        assert len(d["conditions"]) == 1
        assert d["action"]["type"] == "delete"

    def test_from_dict_minimal(self) -> None:
        rule = Rule.from_dict({})
        assert rule.name == "unnamed"
        assert rule.description == ""
        assert rule.conditions == []
        assert rule.action.action_type == ActionType.MOVE
        assert rule.enabled is True
        assert rule.priority == 0

    def test_from_dict_full(self) -> None:
        data: dict[str, Any] = {
            "name": "images-rule",
            "description": "Sort images",
            "conditions": [
                {"type": "extension", "value": ".jpg"},
                {"type": "size_greater", "value": "0", "negate": False},
            ],
            "action": {"type": "move", "destination": "/photos"},
            "enabled": True,
            "priority": 3,
        }
        rule = Rule.from_dict(data)
        assert rule.name == "images-rule"
        assert len(rule.conditions) == 2
        assert rule.conditions[0].value == ".jpg"
        assert rule.action.destination == "/photos"
        assert rule.priority == 3

    def test_from_dict_missing_action(self) -> None:
        """When action key is missing, default action type is move."""
        rule = Rule.from_dict({"name": "no-action"})
        assert rule.action.action_type == ActionType.MOVE

    def test_roundtrip(self) -> None:
        cond = RuleCondition(
            condition_type=ConditionType.MODIFIED_AFTER,
            value="2024-01-01",
        )
        action = RuleAction(
            action_type=ActionType.ARCHIVE,
            destination="/archive",
            parameters={"compress": True},
        )
        original = Rule(
            name="archive-old",
            description="Archive files modified after date",
            conditions=[cond],
            action=action,
            enabled=True,
            priority=7,
        )
        restored = Rule.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.priority == original.priority
        assert restored.enabled == original.enabled
        assert len(restored.conditions) == len(original.conditions)
        assert restored.conditions[0].value == cond.value
        assert restored.action.destination == action.destination

    def test_disabled_rule(self) -> None:
        rule = Rule(name="disabled", enabled=False)
        assert rule.enabled is False


# ------------------------------------------------------------------ #
# RuleSet
# ------------------------------------------------------------------ #

class TestRuleSet:
    """Tests for RuleSet dataclass."""

    def test_empty_ruleset(self) -> None:
        rs = RuleSet()
        assert rs.name == "default"
        assert rs.description == ""
        assert rs.rules == []
        assert rs.version == "1.0"

    def test_enabled_rules_filters_disabled(self) -> None:
        rules = [
            Rule(name="a", enabled=True, priority=1),
            Rule(name="b", enabled=False, priority=10),
            Rule(name="c", enabled=True, priority=5),
        ]
        rs = RuleSet(rules=rules)
        enabled = rs.enabled_rules
        assert len(enabled) == 2
        assert all(r.enabled for r in enabled)

    def test_enabled_rules_sorted_by_priority_desc(self) -> None:
        rules = [
            Rule(name="low", enabled=True, priority=1),
            Rule(name="high", enabled=True, priority=10),
            Rule(name="mid", enabled=True, priority=5),
        ]
        rs = RuleSet(rules=rules)
        enabled = rs.enabled_rules
        assert [r.name for r in enabled] == ["high", "mid", "low"]

    def test_enabled_rules_empty_when_all_disabled(self) -> None:
        rules = [
            Rule(name="a", enabled=False),
            Rule(name="b", enabled=False),
        ]
        rs = RuleSet(rules=rules)
        assert rs.enabled_rules == []

    def test_enabled_rules_empty_when_no_rules(self) -> None:
        rs = RuleSet()
        assert rs.enabled_rules == []

    def test_to_dict(self) -> None:
        rule = Rule(name="test")
        rs = RuleSet(
            name="my-set",
            description="A test set",
            rules=[rule],
            version="2.0",
        )
        d = rs.to_dict()
        assert d["name"] == "my-set"
        assert d["description"] == "A test set"
        assert d["version"] == "2.0"
        assert len(d["rules"]) == 1

    def test_from_dict_minimal(self) -> None:
        rs = RuleSet.from_dict({})
        assert rs.name == "default"
        assert rs.description == ""
        assert rs.rules == []
        assert rs.version == "1.0"

    def test_from_dict_with_rules(self) -> None:
        data: dict[str, Any] = {
            "name": "production",
            "description": "Production rules",
            "version": "1.1",
            "rules": [
                {
                    "name": "pdf-move",
                    "conditions": [{"type": "extension", "value": ".pdf"}],
                    "action": {"type": "move", "destination": "/docs"},
                },
                {
                    "name": "log-delete",
                    "conditions": [{"type": "extension", "value": ".log"}],
                    "action": {"type": "delete"},
                    "enabled": False,
                },
            ],
        }
        rs = RuleSet.from_dict(data)
        assert rs.name == "production"
        assert rs.version == "1.1"
        assert len(rs.rules) == 2
        assert rs.rules[0].name == "pdf-move"
        assert rs.rules[1].enabled is False

    def test_roundtrip(self) -> None:
        cond = RuleCondition(
            condition_type=ConditionType.EXTENSION, value=".txt"
        )
        action = RuleAction(
            action_type=ActionType.CATEGORIZE,
            parameters={"category": "text"},
        )
        rule = Rule(
            name="txt-categorize",
            conditions=[cond],
            action=action,
            priority=2,
        )
        original = RuleSet(
            name="roundtrip-test",
            description="For testing",
            rules=[rule],
            version="3.0",
        )
        restored = RuleSet.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.description == original.description
        assert restored.version == original.version
        assert len(restored.rules) == 1
        assert restored.rules[0].name == "txt-categorize"

    def test_rules_list_independent(self) -> None:
        rs1 = RuleSet()
        rs2 = RuleSet()
        rs1.rules.append(Rule(name="x"))
        assert len(rs2.rules) == 0

    def test_multiple_conditions_in_rule_roundtrip(self) -> None:
        """Verify a rule with multiple conditions survives serialization."""
        data: dict[str, Any] = {
            "name": "complex-rule",
            "conditions": [
                {"type": "extension", "value": ".pdf"},
                {"type": "size_greater", "value": "10000"},
                {"type": "path_matches", "value": "/inbox/*", "negate": True},
            ],
            "action": {"type": "move", "destination": "/large-pdfs"},
            "priority": 99,
        }
        rule = Rule.from_dict(data)
        assert len(rule.conditions) == 3
        assert rule.conditions[2].negate is True

        restored = Rule.from_dict(rule.to_dict())
        assert len(restored.conditions) == 3
        assert restored.conditions[2].negate is True
        assert restored.priority == 99
