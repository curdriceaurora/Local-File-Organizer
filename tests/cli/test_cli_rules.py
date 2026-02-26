"""Tests for file_organizer.cli.rules module.

Tests the Typer-based rules management CLI commands including:
- rules list, sets, add, remove, toggle
- rules preview, export, import
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.rules import rules_app
from file_organizer.services.copilot.rules.models import (
    ActionType,
    ConditionType,
    Rule,
    RuleAction,
    RuleCondition,
    RuleSet,
)

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# Patch paths — rules.py uses *lazy imports* inside each command function.
# We must patch at the source-module level so the runtime import picks up
# our mocks.
# ---------------------------------------------------------------------------
_RULES_PKG = "file_organizer.services.copilot.rules"
_RULE_MGR_PATH = f"{_RULES_PKG}.RuleManager"
_RULE_MGR_ADD_PATH = f"{_RULES_PKG}.rule_manager.RuleManager"
_PREVIEW_ENGINE_PATH = f"{_RULES_PKG}.PreviewEngine"
_RULE_SET_PATH = f"{_RULES_PKG}.RuleSet"


@pytest.fixture
def runner():
    """Create a Typer CLI test runner."""
    return CliRunner()


@pytest.fixture
def sample_rule():
    """Create a sample Rule object."""
    return Rule(
        name="move-pdfs",
        conditions=[
            RuleCondition(condition_type=ConditionType.EXTENSION, value=".pdf"),
        ],
        action=RuleAction(action_type=ActionType.MOVE, destination="/docs/pdfs"),
        priority=10,
        enabled=True,
    )


@pytest.fixture
def sample_rule_set(sample_rule):
    """Create a sample RuleSet."""
    return RuleSet(
        name="default",
        description="Default rules",
        rules=[sample_rule],
    )


@pytest.fixture
def mock_rule_manager(sample_rule_set):
    """Create a mock RuleManager."""
    mgr = MagicMock()
    mgr.load_rule_set.return_value = sample_rule_set
    mgr.list_rule_sets.return_value = ["default", "custom"]
    mgr.remove_rule.return_value = True
    mgr.toggle_rule.return_value = True
    return mgr


# ============================================================================
# List Tests
# ============================================================================


class TestRulesList:
    """Tests for the 'list' subcommand."""

    def test_list_rules(self, runner, mock_rule_manager):
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["list"])
        assert result.exit_code == 0
        assert "move-pdfs" in result.output

    def test_list_rules_custom_set(self, runner, mock_rule_manager):
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["list", "--set", "custom"])
        assert result.exit_code == 0
        mock_rule_manager.load_rule_set.assert_called_with("custom")

    def test_list_rules_empty(self, runner, mock_rule_manager):
        mock_rule_manager.load_rule_set.return_value = RuleSet(name="empty", rules=[])
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["list"])
        assert result.exit_code == 0
        assert "No rules" in result.output


# ============================================================================
# Sets Tests
# ============================================================================


class TestRulesSets:
    """Tests for the 'sets' subcommand."""

    def test_list_sets(self, runner, mock_rule_manager):
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["sets"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "custom" in result.output
        assert "2 rule set(s)" in result.output

    def test_no_sets(self, runner, mock_rule_manager):
        mock_rule_manager.list_rule_sets.return_value = []
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["sets"])
        assert result.exit_code == 0
        assert "No rule sets found" in result.output


# ============================================================================
# Add Tests
# ============================================================================


class TestRulesAdd:
    """Tests for the 'add' subcommand."""

    def test_add_rule_with_extension(self, runner):
        mock_mgr = MagicMock()
        with patch(_RULE_MGR_ADD_PATH, return_value=mock_mgr):
            result = runner.invoke(
                rules_app,
                ["add", "move-images", "--ext", ".jpg,.png", "--action", "move", "--dest", "/images"],
            )
        assert result.exit_code == 0
        assert "Added rule" in result.output
        mock_mgr.add_rule.assert_called_once()

    def test_add_rule_with_pattern(self, runner):
        mock_mgr = MagicMock()
        with patch(_RULE_MGR_ADD_PATH, return_value=mock_mgr):
            result = runner.invoke(
                rules_app,
                ["add", "archive-logs", "--pattern", "*.log", "--action", "archive"],
            )
        assert result.exit_code == 0
        assert "Added rule" in result.output

    def test_add_rule_invalid_action(self, runner):
        mock_mgr = MagicMock()
        with patch(_RULE_MGR_ADD_PATH, return_value=mock_mgr):
            result = runner.invoke(
                rules_app,
                ["add", "bad-rule", "--action", "invalid_action"],
            )
        assert result.exit_code == 1
        assert "Unknown action" in result.output

    def test_add_rule_with_priority(self, runner):
        mock_mgr = MagicMock()
        with patch(_RULE_MGR_ADD_PATH, return_value=mock_mgr):
            result = runner.invoke(
                rules_app,
                ["add", "high-pri", "--action", "move", "--priority", "100"],
            )
        assert result.exit_code == 0
        # Verify the rule passed to add_rule has the right priority
        call_args = mock_mgr.add_rule.call_args
        rule = call_args[0][1]
        assert rule.priority == 100

    def test_add_rule_to_custom_set(self, runner):
        mock_mgr = MagicMock()
        with patch(_RULE_MGR_ADD_PATH, return_value=mock_mgr):
            result = runner.invoke(
                rules_app,
                ["add", "my-rule", "--action", "tag", "--set", "my-set"],
            )
        assert result.exit_code == 0
        call_args = mock_mgr.add_rule.call_args
        assert call_args[0][0] == "my-set"


# ============================================================================
# Remove Tests
# ============================================================================


class TestRulesRemove:
    """Tests for the 'remove' subcommand."""

    def test_remove_rule_success(self, runner, mock_rule_manager):
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["remove", "move-pdfs"])
        assert result.exit_code == 0
        assert "Removed rule" in result.output

    def test_remove_rule_not_found(self, runner, mock_rule_manager):
        mock_rule_manager.remove_rule.return_value = False
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["remove", "nonexistent"])
        assert result.exit_code == 0
        assert "not found" in result.output


# ============================================================================
# Toggle Tests
# ============================================================================


class TestRulesToggle:
    """Tests for the 'toggle' subcommand."""

    def test_toggle_enable(self, runner, mock_rule_manager):
        mock_rule_manager.toggle_rule.return_value = True
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["toggle", "move-pdfs"])
        assert result.exit_code == 0
        assert "enabled" in result.output

    def test_toggle_disable(self, runner, mock_rule_manager):
        mock_rule_manager.toggle_rule.return_value = False
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["toggle", "move-pdfs"])
        assert result.exit_code == 0
        assert "disabled" in result.output

    def test_toggle_not_found(self, runner, mock_rule_manager):
        mock_rule_manager.toggle_rule.return_value = None
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["toggle", "nonexistent"])
        assert result.exit_code == 0
        assert "not found" in result.output


# ============================================================================
# Preview Tests
# ============================================================================


class TestRulesPreview:
    """Tests for the 'preview' subcommand."""

    def test_preview_with_matches(self, runner, sample_rule_set, tmp_path):
        mock_mgr = MagicMock()
        mock_mgr.load_rule_set.return_value = sample_rule_set

        mock_result = MagicMock()
        mock_result.summary = "5 files matched"
        match1 = MagicMock()
        match1.file_path = str(tmp_path / "doc.pdf")
        match1.rule_name = "move-pdfs"
        match1.action_type = "move"
        match1.destination = "/docs/pdfs"
        mock_result.matches = [match1]
        mock_result.errors = []

        mock_engine = MagicMock()
        mock_engine.preview.return_value = mock_result

        with (
            patch(_RULE_MGR_PATH, return_value=mock_mgr),
            patch(_PREVIEW_ENGINE_PATH, return_value=mock_engine),
        ):
            result = runner.invoke(rules_app, ["preview", str(tmp_path)])
        assert result.exit_code == 0
        assert "5 files matched" in result.output

    def test_preview_no_enabled_rules(self, runner):
        mock_mgr = MagicMock()
        rs = RuleSet(name="empty", rules=[])
        mock_mgr.load_rule_set.return_value = rs

        with patch(_RULE_MGR_PATH, return_value=mock_mgr):
            result = runner.invoke(rules_app, ["preview", "/tmp"])
        assert result.exit_code == 0
        assert "No enabled rules" in result.output

    def test_preview_with_errors(self, runner, sample_rule_set, tmp_path):
        mock_mgr = MagicMock()
        mock_mgr.load_rule_set.return_value = sample_rule_set

        mock_result = MagicMock()
        mock_result.summary = "0 files matched"
        mock_result.matches = []
        mock_result.errors = [("/bad/path", "Permission denied")]

        mock_engine = MagicMock()
        mock_engine.preview.return_value = mock_result

        with (
            patch(_RULE_MGR_PATH, return_value=mock_mgr),
            patch(_PREVIEW_ENGINE_PATH, return_value=mock_engine),
        ):
            result = runner.invoke(rules_app, ["preview", str(tmp_path)])
        assert result.exit_code == 0
        assert "Permission denied" in result.output


# ============================================================================
# Export Tests
# ============================================================================


class TestRulesExport:
    """Tests for the 'export' subcommand."""

    def test_export_to_stdout(self, runner, mock_rule_manager):
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["export"])
        assert result.exit_code == 0

    def test_export_to_file(self, runner, mock_rule_manager, tmp_path):
        output_file = tmp_path / "rules.yaml"
        with patch(_RULE_MGR_PATH, return_value=mock_rule_manager):
            result = runner.invoke(rules_app, ["export", "-o", str(output_file)])
        assert result.exit_code == 0
        assert "Exported" in result.output


# ============================================================================
# Import Tests
# ============================================================================


class TestRulesImport:
    """Tests for the 'import' subcommand."""

    def test_import_success(self, runner, tmp_path):
        yaml_file = tmp_path / "rules.yaml"
        yaml_file.write_text("name: imported\nrules: []\nversion: '1.0'\ndescription: ''")

        mock_mgr = MagicMock()
        mock_rs = MagicMock()
        mock_rs.name = "imported"
        mock_rs.rules = []

        with (
            patch(_RULE_MGR_PATH, return_value=mock_mgr),
            patch(_RULE_SET_PATH) as mock_rule_set_cls,
        ):
            mock_rule_set_cls.from_dict.return_value = mock_rs
            result = runner.invoke(rules_app, ["import", str(yaml_file)])
        assert result.exit_code == 0
        assert "Imported" in result.output

    def test_import_file_not_found(self, runner, tmp_path):
        result = runner.invoke(rules_app, ["import", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_import_invalid_yaml(self, runner, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("::invalid:yaml::")

        # yaml is imported lazily inside the function, but it's a real stdlib
        # import.  The function reads the file and calls yaml.safe_load.
        # We let yaml import normally but make it raise via bad content.
        # Actually safe_load won't raise on that string — it'll parse it.
        # Patch yaml.safe_load via the module that the function will import:
        with patch("yaml.safe_load", side_effect=Exception("parse error")):
            result = runner.invoke(rules_app, ["import", str(bad_yaml)])
        assert result.exit_code == 1
        assert "Failed to parse" in result.output

    def test_import_with_set_override(self, runner, tmp_path):
        yaml_file = tmp_path / "rules.yaml"
        yaml_file.write_text("name: original\nrules: []")

        mock_mgr = MagicMock()
        mock_rs = MagicMock()
        mock_rs.name = "original"
        mock_rs.rules = []

        with (
            patch(_RULE_MGR_PATH, return_value=mock_mgr),
            patch(_RULE_SET_PATH) as mock_rule_set_cls,
        ):
            mock_rule_set_cls.from_dict.return_value = mock_rs
            result = runner.invoke(
                rules_app, ["import", str(yaml_file), "--set", "overridden"]
            )
        assert result.exit_code == 0
        assert mock_rs.name == "overridden"
