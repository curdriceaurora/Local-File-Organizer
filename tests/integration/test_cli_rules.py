"""Integration tests for CLI rules sub-commands.

Covers: rules list (empty, with rules), rules sets (empty, with sets),
rules add (valid actions, invalid action), rules remove (found, not found),
rules toggle (found/enabled/disabled, not found), rules preview (empty rules,
with matches), rules import/export.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.integration]

runner = CliRunner()


class TestRulesList:
    def test_rules_list_empty_rule_set(self) -> None:
        mock_mgr = MagicMock()
        mock_rs = MagicMock()
        mock_rs.rules = []
        mock_mgr.load_rule_set.return_value = mock_rs
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "list"])
        assert result.exit_code == 0
        assert "no rules" in result.output.lower()

    def test_rules_list_shows_rules(self) -> None:
        from file_organizer.services.copilot.rules.models import (
            ActionType,
            ConditionType,
            Rule,
            RuleAction,
            RuleCondition,
        )

        rule = Rule(
            name="pdf-archive",
            conditions=[RuleCondition(condition_type=ConditionType.EXTENSION, value=".pdf")],
            action=RuleAction(action_type=ActionType.MOVE, destination="Archive/PDFs"),
            priority=10,
        )

        mock_mgr = MagicMock()
        mock_rs = MagicMock()
        mock_rs.rules = [rule]
        mock_mgr.load_rule_set.return_value = mock_rs
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "list"])
        assert result.exit_code == 0
        assert "pdf-archive" in result.output

    def test_rules_list_custom_set_name(self) -> None:
        mock_mgr = MagicMock()
        mock_rs = MagicMock()
        mock_rs.rules = []
        mock_mgr.load_rule_set.return_value = mock_rs
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "list", "--set", "work-rules"])
        assert result.exit_code == 0
        mock_mgr.load_rule_set.assert_called_once_with("work-rules")


class TestRulesSets:
    def test_rules_sets_empty(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.list_rule_sets.return_value = []
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "sets"])
        assert result.exit_code == 0
        assert "no rule sets" in result.output.lower() or "rules add" in result.output.lower()

    def test_rules_sets_shows_names(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.list_rule_sets.return_value = ["default", "archive", "work"]
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "sets"])
        assert result.exit_code == 0
        assert "default" in result.output
        assert "archive" in result.output
        assert "work" in result.output
        assert "3" in result.output  # count


_RULE_MGR_PATCHES = (
    "file_organizer.services.copilot.rules.RuleManager",
    "file_organizer.services.copilot.rules.rule_manager.RuleManager",
)


class TestRulesAdd:
    def test_rules_add_valid_move_action(self) -> None:
        mock_mgr = MagicMock()
        with (
            patch(_RULE_MGR_PATCHES[0], return_value=mock_mgr),
            patch(_RULE_MGR_PATCHES[1], return_value=mock_mgr),
        ):
            result = runner.invoke(
                app,
                ["rules", "add", "my-rule", "--action", "move", "--dest", "Archive/"],
            )
        assert result.exit_code == 0
        assert "added" in result.output.lower()
        mock_mgr.add_rule.assert_called_once()

    def test_rules_add_with_extension_filter(self) -> None:
        mock_mgr = MagicMock()
        with (
            patch(_RULE_MGR_PATCHES[0], return_value=mock_mgr),
            patch(_RULE_MGR_PATCHES[1], return_value=mock_mgr),
        ):
            result = runner.invoke(
                app,
                ["rules", "add", "pdf-rule", "--ext", ".pdf", "--action", "move"],
            )
        assert result.exit_code == 0

    def test_rules_add_with_pattern_filter(self) -> None:
        mock_mgr = MagicMock()
        with (
            patch(_RULE_MGR_PATCHES[0], return_value=mock_mgr),
            patch(_RULE_MGR_PATCHES[1], return_value=mock_mgr),
        ):
            result = runner.invoke(
                app,
                ["rules", "add", "report-rule", "--pattern", "report*", "--action", "move"],
            )
        assert result.exit_code == 0

    def test_rules_add_invalid_action_exits_1(self) -> None:
        result = runner.invoke(
            app,
            ["rules", "add", "bad-rule", "--action", "invalid_action"],
        )
        assert result.exit_code == 1
        assert "unknown action" in result.output.lower() or "invalid" in result.output.lower()

    def test_rules_add_all_valid_action_types(self) -> None:
        valid_actions = ["move", "rename", "tag", "categorize", "archive", "copy", "delete"]
        for action in valid_actions:
            mock_mgr = MagicMock()
            with (
                patch(_RULE_MGR_PATCHES[0], return_value=mock_mgr),
                patch(_RULE_MGR_PATCHES[1], return_value=mock_mgr),
            ):
                result = runner.invoke(
                    app,
                    ["rules", "add", f"{action}-rule", "--action", action],
                )
            assert result.exit_code == 0, f"Action '{action}' should be valid, got: {result.output}"

    def test_rules_add_with_priority(self) -> None:
        mock_mgr = MagicMock()
        with (
            patch(_RULE_MGR_PATCHES[0], return_value=mock_mgr),
            patch(_RULE_MGR_PATCHES[1], return_value=mock_mgr),
        ):
            result = runner.invoke(
                app,
                ["rules", "add", "priority-rule", "--priority", "100", "--action", "move"],
            )
        assert result.exit_code == 0

    def test_rules_add_to_custom_set(self) -> None:
        mock_mgr = MagicMock()
        with (
            patch(_RULE_MGR_PATCHES[0], return_value=mock_mgr),
            patch(_RULE_MGR_PATCHES[1], return_value=mock_mgr),
        ):
            result = runner.invoke(
                app,
                ["rules", "add", "my-rule", "--set", "work-rules", "--action", "move"],
            )
        assert result.exit_code == 0
        assert "work-rules" in result.output


class TestRulesRemove:
    def test_rules_remove_found(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.remove_rule.return_value = True
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "remove", "my-rule"])
        assert result.exit_code == 0
        assert "removed" in result.output.lower()
        mock_mgr.remove_rule.assert_called_once_with("default", "my-rule")

    def test_rules_remove_not_found(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.remove_rule.return_value = False
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "remove", "ghost"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestRulesToggle:
    def test_rules_toggle_to_enabled(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.toggle_rule.return_value = True
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "toggle", "my-rule"])
        assert result.exit_code == 0
        assert "enabled" in result.output.lower()

    def test_rules_toggle_to_disabled(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.toggle_rule.return_value = False
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "toggle", "my-rule"])
        assert result.exit_code == 0
        assert "disabled" in result.output.lower()

    def test_rules_toggle_not_found(self) -> None:
        mock_mgr = MagicMock()
        mock_mgr.toggle_rule.return_value = None
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "toggle", "ghost"])
        assert result.exit_code == 0
        assert "not found" in result.output.lower()


class TestRulesPreview:
    def test_rules_preview_no_enabled_rules(self, tmp_path: Path) -> None:
        mock_mgr = MagicMock()
        mock_rs = MagicMock()
        mock_rs.enabled_rules = []
        mock_mgr.load_rule_set.return_value = mock_rs
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "preview", str(tmp_path)])
        assert result.exit_code == 0
        assert "no enabled rules" in result.output.lower()

    def test_rules_preview_with_matches(self, tmp_path: Path) -> None:
        from file_organizer.services.copilot.rules.models import (
            ActionType,
            ConditionType,
            Rule,
            RuleAction,
            RuleCondition,
        )

        (tmp_path / "invoice.pdf").write_bytes(b"%PDF")

        rule = Rule(
            name="pdf-rule",
            conditions=[RuleCondition(condition_type=ConditionType.EXTENSION, value=".pdf")],
            action=RuleAction(action_type=ActionType.MOVE, destination="Archive"),
        )

        mock_mgr = MagicMock()
        mock_rs = MagicMock()
        mock_rs.enabled_rules = [rule]
        mock_mgr.load_rule_set.return_value = mock_rs

        mock_preview_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.summary = "1 file matched"
        mock_result.matches = []
        mock_result.errors = []
        mock_preview_engine.preview.return_value = mock_result

        with (
            patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr),
            patch(
                "file_organizer.services.copilot.rules.PreviewEngine",
                return_value=mock_preview_engine,
            ),
        ):
            result = runner.invoke(app, ["rules", "preview", str(tmp_path)])
        assert result.exit_code == 0
        assert "1 file matched" in result.output


class TestRulesExportImport:
    def test_rules_export_stdout(self) -> None:
        from file_organizer.services.copilot.rules.models import RuleSet

        mock_mgr = MagicMock()
        mock_rs = RuleSet(name="default", rules=[])
        mock_mgr.load_rule_set.return_value = mock_rs

        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "export"])
        assert result.exit_code == 0

    def test_rules_export_to_file(self, tmp_path: Path) -> None:
        from file_organizer.services.copilot.rules.models import RuleSet

        output_file = tmp_path / "rules.yaml"
        mock_mgr = MagicMock()
        mock_rs = RuleSet(name="default", rules=[])
        mock_mgr.load_rule_set.return_value = mock_rs

        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "export", "--output", str(output_file)])
        assert result.exit_code == 0
        assert output_file.exists()

    def test_rules_import_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["rules", "import", str(tmp_path / "nonexistent.yaml")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "file" in result.output.lower()

    def test_rules_import_valid_yaml(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "rules.yaml"
        yaml_file.write_text(
            "name: imported\nrules: []\n",
            encoding="utf-8",
        )
        mock_mgr = MagicMock()
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(app, ["rules", "import", str(yaml_file)])
        assert result.exit_code == 0
        assert "imported" in result.output.lower()
        mock_mgr.save_rule_set.assert_called_once()

    def test_rules_import_bad_yaml_exits_1(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("{{{{invalid yaml content", encoding="utf-8")
        result = runner.invoke(app, ["rules", "import", str(yaml_file)])
        assert result.exit_code == 1
        assert "yaml" in result.output.lower() or "failed" in result.output.lower()

    def test_rules_import_with_set_override(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "rules.yaml"
        yaml_file.write_text("name: original\nrules: []\n", encoding="utf-8")
        mock_mgr = MagicMock()
        with patch("file_organizer.services.copilot.rules.RuleManager", return_value=mock_mgr):
            result = runner.invoke(
                app,
                ["rules", "import", str(yaml_file), "--set", "overridden"],
            )
        assert result.exit_code == 0
        assert "overridden" in result.output
