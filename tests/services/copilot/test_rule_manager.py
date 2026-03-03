"""Tests for file_organizer.services.copilot.rules.rule_manager.

Covers RuleManager CRUD operations for rule sets and individual rules,
including file I/O, error handling, and edge cases.
"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from file_organizer.services.copilot.rules.models import (
    ActionType,
    ConditionType,
    Rule,
    RuleAction,
    RuleCondition,
    RuleSet,
)
from file_organizer.services.copilot.rules.rule_manager import RuleManager


@pytest.fixture()
def temp_rules_dir() -> TemporaryDirectory:
    """Create a temporary directory for rules."""
    return TemporaryDirectory()


@pytest.fixture()
def manager(temp_rules_dir: TemporaryDirectory) -> RuleManager:
    """Create a RuleManager with a temporary rules directory."""
    return RuleManager(temp_rules_dir.name)


@pytest.fixture()
def sample_rule() -> Rule:
    """Create a sample rule for testing."""
    condition = RuleCondition(
        condition_type=ConditionType.EXTENSION,
        value=".pdf"
    )
    action = RuleAction(
        action_type=ActionType.MOVE,
        destination="Documents"
    )
    return Rule(
        name="pdf_rule",
        conditions=[condition],
        action=action,
        enabled=True
    )


# ================================================================ #
# Rule Set CRUD
# ================================================================ #

@pytest.mark.unit
class TestListRuleSets:
    """Tests for listing rule sets."""

    def test_empty_directory_returns_empty_list(self, manager: RuleManager) -> None:
        """Non-existent directory returns empty list."""
        result = manager.list_rule_sets()
        assert result == []

    def test_lists_existing_rule_sets(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Lists available rule set names."""
        # Create a rule set
        rule_set = RuleSet(name="test_set", rules=[sample_rule])
        manager.save_rule_set(rule_set)

        # Verify it appears in the list
        result = manager.list_rule_sets()
        assert "test_set" in result

    def test_lists_multiple_rule_sets(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Lists multiple rule sets in sorted order."""
        # Create multiple rule sets
        for name in ["zebra_set", "alpha_set", "beta_set"]:
            rule_set = RuleSet(name=name, rules=[sample_rule])
            manager.save_rule_set(rule_set)

        # Verify sorted order
        result = manager.list_rule_sets()
        assert result == ["alpha_set", "beta_set", "zebra_set"]

    def test_ignores_non_yaml_files(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Only .yaml files are listed."""
        # Create a rule set
        rule_set = RuleSet(name="valid_set", rules=[sample_rule])
        manager.save_rule_set(rule_set)

        # Create a non-YAML file
        (Path(manager.rules_dir) / "not_a_rule.txt").write_text("ignored")

        # Verify only YAML is listed
        result = manager.list_rule_sets()
        assert result == ["valid_set"]


@pytest.mark.unit
class TestLoadRuleSet:
    """Tests for loading rule sets."""

    def test_load_nonexistent_returns_empty(self, manager: RuleManager) -> None:
        """Loading non-existent rule set returns empty RuleSet."""
        result = manager.load_rule_set("nonexistent")
        assert result.name == "nonexistent"
        assert result.rules == []

    def test_load_existing_rule_set(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Load a previously saved rule set."""
        # Save a rule set
        original = RuleSet(name="my_rules", rules=[sample_rule])
        manager.save_rule_set(original)

        # Load it back
        loaded = manager.load_rule_set("my_rules")
        assert loaded.name == "my_rules"
        assert len(loaded.rules) == 1
        assert loaded.rules[0].name == "pdf_rule"

    def test_load_invalid_yaml_returns_empty(self, manager: RuleManager) -> None:
        """Loading malformed YAML returns empty RuleSet."""
        # Create an invalid YAML file
        Path(manager.rules_dir).mkdir(parents=True, exist_ok=True)
        (Path(manager.rules_dir) / "broken.yaml").write_text("invalid: yaml: content:")

        # Load should handle the error
        result = manager.load_rule_set("broken")
        assert result.name == "broken"
        assert result.rules == []

    def test_load_non_dict_yaml_returns_empty(self, manager: RuleManager) -> None:
        """Loading YAML that's not a dict returns empty RuleSet."""
        # Create YAML with list instead of dict
        Path(manager.rules_dir).mkdir(parents=True, exist_ok=True)
        (Path(manager.rules_dir) / "list.yaml").write_text("- item1\n- item2\n")

        # Load should handle this
        result = manager.load_rule_set("list")
        assert result.name == "list"
        assert result.rules == []


@pytest.mark.unit
class TestSaveRuleSet:
    """Tests for saving rule sets."""

    def test_save_creates_directory(self, temp_rules_dir: TemporaryDirectory) -> None:
        """Save creates rules directory if needed."""
        # Use a non-existent subdirectory
        manager = RuleManager(Path(temp_rules_dir.name) / "new" / "rules")
        rule_set = RuleSet(name="test", rules=[])

        # Should not raise
        result = manager.save_rule_set(rule_set)
        assert result.exists()

    def test_save_creates_yaml_file(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Save creates a YAML file."""
        rule_set = RuleSet(name="output", rules=[sample_rule])
        result = manager.save_rule_set(rule_set)

        # Verify file exists and is readable
        assert result.exists()
        assert result.suffix == ".yaml"
        loaded = manager.load_rule_set("output")
        assert loaded.name == "output"

    def test_save_overwrites_existing(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Saving with same name overwrites."""
        # Save first version
        rule_set1 = RuleSet(name="test", rules=[sample_rule])
        manager.save_rule_set(rule_set1)

        # Save second version
        rule_set2 = RuleSet(name="test", rules=[])
        manager.save_rule_set(rule_set2)

        # Verify overwritten
        loaded = manager.load_rule_set("test")
        assert loaded.rules == []

    def test_save_preserves_content(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Save and load preserve rule content."""
        # Create a complex rule set
        cond1 = RuleCondition(condition_type=ConditionType.EXTENSION, value=".pdf")
        cond2 = RuleCondition(condition_type=ConditionType.SIZE_GREATER, value="1024")
        action = RuleAction(action_type=ActionType.MOVE, destination="Archive")
        rule = Rule(
            name="complex_rule",
            conditions=[cond1, cond2],
            action=action,
            enabled=False,
        )
        rule_set = RuleSet(name="complex", rules=[rule])

        # Save and load
        manager.save_rule_set(rule_set)
        loaded = manager.load_rule_set("complex")

        # Verify all content preserved
        assert len(loaded.rules) == 1
        loaded_rule = loaded.rules[0]
        assert loaded_rule.name == "complex_rule"
        assert len(loaded_rule.conditions) == 2
        assert loaded_rule.action.destination == "Archive"
        assert loaded_rule.enabled is False


@pytest.mark.unit
class TestDeleteRuleSet:
    """Tests for deleting rule sets."""

    def test_delete_nonexistent_returns_false(self, manager: RuleManager) -> None:
        """Deleting non-existent rule set returns False."""
        result = manager.delete_rule_set("nonexistent")
        assert result is False

    def test_delete_existing_returns_true(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Delete removes existing rule set."""
        # Create and save
        rule_set = RuleSet(name="to_delete", rules=[sample_rule])
        manager.save_rule_set(rule_set)

        # Delete
        result = manager.delete_rule_set("to_delete")
        assert result is True

        # Verify gone
        assert "to_delete" not in manager.list_rule_sets()

    def test_delete_removes_file(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Delete actually removes the file."""
        # Create and save
        rule_set = RuleSet(name="removal_test", rules=[sample_rule])
        path = manager.save_rule_set(rule_set)

        # Verify file exists
        assert path.exists()

        # Delete
        manager.delete_rule_set("removal_test")

        # Verify file gone
        assert not path.exists()


# ================================================================ #
# Individual Rule CRUD
# ================================================================ #

@pytest.mark.unit
class TestAddRule:
    """Tests for adding rules to rule sets."""

    def test_add_to_new_rule_set(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Add rule to non-existent rule set creates it."""
        result = manager.add_rule("new_set", sample_rule)
        assert result.name == "new_set"
        assert len(result.rules) == 1
        assert result.rules[0].name == "pdf_rule"

    def test_add_multiple_rules(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Add multiple rules to same set."""
        rule2 = Rule(
            name="image_rule",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".jpg")],
            action=RuleAction(action_type=ActionType.MOVE, destination="Images"),
        )

        manager.add_rule("multi", sample_rule)
        result = manager.add_rule("multi", rule2)

        assert len(result.rules) == 2
        names = {r.name for r in result.rules}
        assert names == {"pdf_rule", "image_rule"}

    def test_add_prevents_duplicates_by_name(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Adding rule with same name replaces previous."""
        # Add original
        manager.add_rule("test", sample_rule)

        # Add modified version with same name
        modified = Rule(
            name="pdf_rule",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".doc")],
            action=RuleAction(action_type=ActionType.MOVE, destination="Documents"),
        )
        result = manager.add_rule("test", modified)

        # Should have only one rule with that name
        assert len(result.rules) == 1
        assert result.rules[0].conditions[0].value == ".doc"

    def test_add_persists_to_disk(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Added rule is saved to disk."""
        manager.add_rule("persist", sample_rule)

        # Load fresh from disk
        loaded = manager.load_rule_set("persist")
        assert len(loaded.rules) == 1
        assert loaded.rules[0].name == "pdf_rule"


@pytest.mark.unit
class TestRemoveRule:
    """Tests for removing rules from rule sets."""

    def test_remove_nonexistent_rule_set_returns_false(
        self,
        manager: RuleManager,
    ) -> None:
        """Removing from non-existent set returns False."""
        result = manager.remove_rule("nonexistent", "any_rule")
        assert result is False

    def test_remove_nonexistent_rule_returns_false(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Removing non-existent rule returns False."""
        manager.add_rule("test", sample_rule)
        result = manager.remove_rule("test", "nonexistent")
        assert result is False

    def test_remove_existing_rule_returns_true(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Removing existing rule returns True."""
        manager.add_rule("test", sample_rule)
        result = manager.remove_rule("test", "pdf_rule")
        assert result is True

    def test_remove_actually_deletes(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Remove actually deletes the rule."""
        manager.add_rule("test", sample_rule)
        manager.remove_rule("test", "pdf_rule")

        # Verify gone
        loaded = manager.load_rule_set("test")
        assert len(loaded.rules) == 0

    def test_remove_persists_to_disk(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Removal is saved to disk."""
        manager.add_rule("test", sample_rule)
        manager.remove_rule("test", "pdf_rule")

        # Load fresh from disk
        loaded = manager.load_rule_set("test")
        assert len(loaded.rules) == 0


@pytest.mark.unit
class TestGetRule:
    """Tests for getting individual rules."""

    def test_get_nonexistent_rule_set_returns_none(
        self,
        manager: RuleManager,
    ) -> None:
        """Getting from non-existent set returns None."""
        result = manager.get_rule("nonexistent", "any_rule")
        assert result is None

    def test_get_nonexistent_rule_returns_none(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Getting non-existent rule returns None."""
        manager.add_rule("test", sample_rule)
        result = manager.get_rule("test", "nonexistent")
        assert result is None

    def test_get_existing_rule(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Get returns the rule."""
        manager.add_rule("test", sample_rule)
        result = manager.get_rule("test", "pdf_rule")

        assert result is not None
        assert result.name == "pdf_rule"
        assert result.conditions[0].value == ".pdf"

    def test_get_finds_correct_rule_by_name(
        self,
        manager: RuleManager,
    ) -> None:
        """Get returns correct rule when multiple exist."""
        rule1 = Rule(
            name="rule_a",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".txt")],
            action=RuleAction(action_type=ActionType.MOVE, destination="Text"),
        )
        rule2 = Rule(
            name="rule_b",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".bin")],
            action=RuleAction(action_type=ActionType.MOVE, destination="Binary"),
        )

        manager.add_rule("test", rule1)
        manager.add_rule("test", rule2)

        result = manager.get_rule("test", "rule_b")
        assert result.conditions[0].value == ".bin"


@pytest.mark.unit
class TestUpdateRule:
    """Tests for updating existing rules."""

    def test_update_nonexistent_rule_set_returns_false(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Updating in non-existent set returns False."""
        result = manager.update_rule("nonexistent", sample_rule)
        assert result is False

    def test_update_nonexistent_rule_returns_false(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Updating non-existent rule returns False."""
        manager.add_rule("test", sample_rule)

        modified = Rule(
            name="nonexistent",
            conditions=[],
            action=RuleAction(action_type=ActionType.MOVE, destination=""),
        )
        result = manager.update_rule("test", modified)
        assert result is False

    def test_update_existing_rule_returns_true(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Update returns True on success."""
        manager.add_rule("test", sample_rule)

        modified = Rule(
            name="pdf_rule",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".docx")],
            action=RuleAction(action_type=ActionType.MOVE, destination="Office"),
        )
        result = manager.update_rule("test", modified)
        assert result is True

    def test_update_modifies_rule(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Update actually changes the rule."""
        manager.add_rule("test", sample_rule)

        modified = Rule(
            name="pdf_rule",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".xlsx")],
            action=RuleAction(action_type=ActionType.TAG, destination="spreadsheet"),
            enabled=False,
        )
        manager.update_rule("test", modified)

        # Verify changes
        updated = manager.get_rule("test", "pdf_rule")
        assert updated.conditions[0].value == ".xlsx"
        assert updated.action.destination == "spreadsheet"
        assert updated.enabled is False

    def test_update_persists_to_disk(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Update is saved to disk."""
        manager.add_rule("test", sample_rule)

        modified = Rule(
            name="pdf_rule",
            conditions=[RuleCondition(ConditionType.SIZE_LESS, "500")],
            action=RuleAction(action_type=ActionType.DELETE, destination=""),
        )
        manager.update_rule("test", modified)

        # Load fresh from disk
        loaded = manager.load_rule_set("test")
        assert loaded.rules[0].conditions[0].value == "500"


@pytest.mark.unit
class TestToggleRule:
    """Tests for toggling rule enabled state."""

    def test_toggle_nonexistent_rule_set_returns_none(
        self,
        manager: RuleManager,
    ) -> None:
        """Toggling in non-existent set returns None."""
        result = manager.toggle_rule("nonexistent", "any_rule")
        assert result is None

    def test_toggle_nonexistent_rule_returns_none(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Toggling non-existent rule returns None."""
        manager.add_rule("test", sample_rule)
        result = manager.toggle_rule("test", "nonexistent")
        assert result is None

    def test_toggle_enabled_to_disabled(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Toggle changes enabled to disabled."""
        manager.add_rule("test", sample_rule)

        # Original is enabled=True
        result = manager.toggle_rule("test", "pdf_rule")
        assert result is False

        # Verify persisted
        rule = manager.get_rule("test", "pdf_rule")
        assert rule.enabled is False

    def test_toggle_disabled_to_enabled(
        self,
        manager: RuleManager,
    ) -> None:
        """Toggle changes disabled to enabled."""
        disabled_rule = Rule(
            name="test_rule",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".tmp")],
            action=RuleAction(action_type=ActionType.DELETE, destination=""),
            enabled=False,
        )
        manager.add_rule("test", disabled_rule)

        result = manager.toggle_rule("test", "test_rule")
        assert result is True

        # Verify persisted
        rule = manager.get_rule("test", "test_rule")
        assert rule.enabled is True

    def test_toggle_returns_new_state(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Toggle returns the new enabled state."""
        manager.add_rule("test", sample_rule)

        # First toggle: True -> False
        state1 = manager.toggle_rule("test", "pdf_rule")
        assert state1 is False

        # Second toggle: False -> True
        state2 = manager.toggle_rule("test", "pdf_rule")
        assert state2 is True

    def test_toggle_multiple_times(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Multiple toggles work correctly."""
        manager.add_rule("test", sample_rule)

        for expected_state in [False, True, False, True, False]:
            result = manager.toggle_rule("test", "pdf_rule")
            assert result == expected_state


@pytest.mark.unit
class TestRuleManagerIntegration:
    """Integration tests for RuleManager."""

    def test_complex_workflow(
        self,
        manager: RuleManager,
    ) -> None:
        """Test a realistic workflow with multiple operations."""
        # Create rules
        pdf_rule = Rule(
            name="pdf_organizer",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".pdf")],
            action=RuleAction(action_type=ActionType.MOVE, destination="Documents/PDFs"),
            enabled=True,
        )
        image_rule = Rule(
            name="image_organizer",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".jpg")],
            action=RuleAction(action_type=ActionType.MOVE, destination="Pictures"),
            enabled=True,
        )

        # Add to rule set
        manager.add_rule("personal", pdf_rule)
        manager.add_rule("personal", image_rule)

        # List and verify
        rules_list = manager.list_rule_sets()
        assert "personal" in rules_list

        # Get and modify
        rule_set = manager.load_rule_set("personal")
        assert len(rule_set.rules) == 2

        # Update one
        pdf_rule.enabled = False
        manager.update_rule("personal", pdf_rule)

        # Verify update
        updated = manager.get_rule("personal", "pdf_organizer")
        assert updated.enabled is False

        # Remove one
        manager.remove_rule("personal", "image_organizer")

        # Verify removal
        final_set = manager.load_rule_set("personal")
        assert len(final_set.rules) == 1

    def test_multiple_rule_sets(
        self,
        manager: RuleManager,
        sample_rule: Rule,
    ) -> None:
        """Manage multiple independent rule sets."""
        # Create sets
        for set_name in ["work", "personal", "archive"]:
            manager.add_rule(set_name, sample_rule)

        # Verify all exist
        rule_sets = manager.list_rule_sets()
        assert len(rule_sets) == 3

        # Modify one without affecting others
        manager.toggle_rule("work", "pdf_rule")
        work_rule = manager.get_rule("work", "pdf_rule")
        assert work_rule.enabled is False

        personal_rule = manager.get_rule("personal", "pdf_rule")
        assert personal_rule.enabled is True

        archive_rule = manager.get_rule("archive", "pdf_rule")
        assert archive_rule.enabled is True
