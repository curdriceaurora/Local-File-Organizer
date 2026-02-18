"""Tests for the copilot rule management and preview system."""

from __future__ import annotations

from pathlib import Path

from file_organizer.services.copilot.rules.models import (
    ActionType,
    ConditionType,
    Rule,
    RuleAction,
    RuleCondition,
    RuleSet,
)
from file_organizer.services.copilot.rules.preview import PreviewEngine
from file_organizer.services.copilot.rules.rule_manager import RuleManager

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestRuleCondition:
    def test_extension_roundtrip(self) -> None:
        c = RuleCondition(condition_type=ConditionType.EXTENSION, value=".pdf,.docx")
        d = c.to_dict()
        c2 = RuleCondition.from_dict(d)
        assert c2.condition_type == ConditionType.EXTENSION
        assert c2.value == ".pdf,.docx"
        assert c2.negate is False

    def test_negate_roundtrip(self) -> None:
        c = RuleCondition(condition_type=ConditionType.NAME_PATTERN, value="*.tmp", negate=True)
        d = c.to_dict()
        assert d["negate"] is True
        c2 = RuleCondition.from_dict(d)
        assert c2.negate is True


class TestRuleAction:
    def test_move_roundtrip(self) -> None:
        a = RuleAction(action_type=ActionType.MOVE, destination="~/Documents/{ext}")
        d = a.to_dict()
        a2 = RuleAction.from_dict(d)
        assert a2.action_type == ActionType.MOVE
        assert a2.destination == "~/Documents/{ext}"

    def test_tag_with_parameters(self) -> None:
        a = RuleAction(action_type=ActionType.TAG, parameters={"tags": ["important"]})
        d = a.to_dict()
        assert d["parameters"]["tags"] == ["important"]


class TestRule:
    def test_full_roundtrip(self) -> None:
        rule = Rule(
            name="archive-old-pdfs",
            description="Move old PDFs to archive",
            conditions=[
                RuleCondition(condition_type=ConditionType.EXTENSION, value=".pdf"),
                RuleCondition(condition_type=ConditionType.SIZE_GREATER, value="1000000"),
            ],
            action=RuleAction(action_type=ActionType.ARCHIVE, destination="~/Archive"),
            priority=10,
        )
        d = rule.to_dict()
        r2 = Rule.from_dict(d)
        assert r2.name == "archive-old-pdfs"
        assert len(r2.conditions) == 2
        assert r2.action.action_type == ActionType.ARCHIVE
        assert r2.priority == 10

    def test_default_values(self) -> None:
        rule = Rule(name="test")
        assert rule.enabled is True
        assert rule.priority == 0
        assert rule.conditions == []


class TestRuleSet:
    def test_enabled_rules_sorted_by_priority(self) -> None:
        rs = RuleSet(
            name="test",
            rules=[
                Rule(name="low", priority=1),
                Rule(name="high", priority=10),
                Rule(name="disabled", priority=100, enabled=False),
            ],
        )
        enabled = rs.enabled_rules
        assert len(enabled) == 2
        assert enabled[0].name == "high"
        assert enabled[1].name == "low"

    def test_roundtrip(self) -> None:
        rs = RuleSet(
            name="my-rules",
            description="Test rules",
            rules=[Rule(name="r1"), Rule(name="r2")],
        )
        d = rs.to_dict()
        rs2 = RuleSet.from_dict(d)
        assert rs2.name == "my-rules"
        assert len(rs2.rules) == 2


# ---------------------------------------------------------------------------
# RuleManager tests
# ---------------------------------------------------------------------------


class TestRuleManager:
    def test_list_empty(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        assert mgr.list_rule_sets() == []

    def test_save_and_load(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        rs = RuleSet(name="test", rules=[Rule(name="r1")])
        mgr.save_rule_set(rs)
        loaded = mgr.load_rule_set("test")
        assert loaded.name == "test"
        assert len(loaded.rules) == 1

    def test_list_after_save(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        mgr.save_rule_set(RuleSet(name="alpha"))
        mgr.save_rule_set(RuleSet(name="beta"))
        assert mgr.list_rule_sets() == ["alpha", "beta"]

    def test_delete(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        mgr.save_rule_set(RuleSet(name="doomed"))
        assert mgr.delete_rule_set("doomed") is True
        assert mgr.delete_rule_set("doomed") is False

    def test_add_rule(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        rule = Rule(name="new-rule")
        mgr.add_rule("default", rule)
        loaded = mgr.load_rule_set("default")
        assert len(loaded.rules) == 1
        assert loaded.rules[0].name == "new-rule"

    def test_add_rule_replaces_duplicate(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        mgr.add_rule("default", Rule(name="dup", priority=1))
        mgr.add_rule("default", Rule(name="dup", priority=99))
        loaded = mgr.load_rule_set("default")
        assert len(loaded.rules) == 1
        assert loaded.rules[0].priority == 99

    def test_remove_rule(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        mgr.add_rule("default", Rule(name="keep"))
        mgr.add_rule("default", Rule(name="remove"))
        assert mgr.remove_rule("default", "remove") is True
        assert mgr.remove_rule("default", "remove") is False
        loaded = mgr.load_rule_set("default")
        assert len(loaded.rules) == 1

    def test_get_rule(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        mgr.add_rule("default", Rule(name="find-me", priority=42))
        found = mgr.get_rule("default", "find-me")
        assert found is not None
        assert found.priority == 42
        assert mgr.get_rule("default", "nope") is None

    def test_toggle_rule(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        mgr.add_rule("default", Rule(name="toggle-me", enabled=True))
        assert mgr.toggle_rule("default", "toggle-me") is False
        assert mgr.toggle_rule("default", "toggle-me") is True
        assert mgr.toggle_rule("default", "nope") is None

    def test_update_rule(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        mgr.add_rule("default", Rule(name="update-me", priority=1))
        updated = Rule(name="update-me", priority=99)
        assert mgr.update_rule("default", updated) is True
        loaded = mgr.get_rule("default", "update-me")
        assert loaded is not None
        assert loaded.priority == 99

    def test_load_nonexistent(self, tmp_path: Path) -> None:
        mgr = RuleManager(rules_dir=tmp_path / "rules")
        rs = mgr.load_rule_set("nonexistent")
        assert rs.name == "nonexistent"
        assert len(rs.rules) == 0


# ---------------------------------------------------------------------------
# PreviewEngine tests
# ---------------------------------------------------------------------------


class TestPreviewEngine:
    def test_preview_empty_rules(self, tmp_path: Path) -> None:
        engine = PreviewEngine()
        rs = RuleSet(name="empty")
        result = engine.preview(rs, tmp_path)
        assert result.match_count == 0
        assert result.total_files == 0

    def test_preview_extension_match(self, tmp_path: Path) -> None:
        (tmp_path / "doc.pdf").write_text("content")
        (tmp_path / "pic.jpg").write_bytes(b"\xff\xd8")
        (tmp_path / "readme.txt").write_text("hello")

        rs = RuleSet(
            name="test",
            rules=[
                Rule(
                    name="pdf-rule",
                    conditions=[
                        RuleCondition(condition_type=ConditionType.EXTENSION, value=".pdf")
                    ],
                    action=RuleAction(action_type=ActionType.MOVE, destination="~/PDFs"),
                ),
            ],
        )
        engine = PreviewEngine()
        result = engine.preview(rs, tmp_path)
        assert result.total_files == 3
        assert result.match_count == 1
        assert result.matches[0].rule_name == "pdf-rule"

    def test_preview_name_pattern(self, tmp_path: Path) -> None:
        (tmp_path / "report_2025.xlsx").write_text("data")
        (tmp_path / "notes.txt").write_text("notes")

        rs = RuleSet(
            name="test",
            rules=[
                Rule(
                    name="report-rule",
                    conditions=[
                        RuleCondition(condition_type=ConditionType.NAME_PATTERN, value="report_*")
                    ],
                    action=RuleAction(action_type=ActionType.MOVE, destination="~/Reports"),
                ),
            ],
        )
        engine = PreviewEngine()
        result = engine.preview(rs, tmp_path)
        assert result.match_count == 1

    def test_preview_negate_condition(self, tmp_path: Path) -> None:
        (tmp_path / "keep.txt").write_text("keep")
        (tmp_path / "temp.tmp").write_text("temp")

        rs = RuleSet(
            name="test",
            rules=[
                Rule(
                    name="not-tmp",
                    conditions=[
                        RuleCondition(
                            condition_type=ConditionType.EXTENSION, value=".tmp", negate=True
                        ),
                    ],
                    action=RuleAction(action_type=ActionType.MOVE, destination="~/Keep"),
                ),
            ],
        )
        engine = PreviewEngine()
        result = engine.preview(rs, tmp_path)
        assert result.match_count == 1
        assert "keep.txt" in result.matches[0].file_path

    def test_preview_nonexistent_dir(self) -> None:
        engine = PreviewEngine()
        rs = RuleSet(name="test", rules=[Rule(name="r")])
        result = engine.preview(rs, "/nonexistent/path")
        assert len(result.errors) == 1

    def test_preview_destination_template(self, tmp_path: Path) -> None:
        (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8")

        rs = RuleSet(
            name="test",
            rules=[
                Rule(
                    name="photo-rule",
                    conditions=[
                        RuleCondition(condition_type=ConditionType.EXTENSION, value=".jpg")
                    ],
                    action=RuleAction(
                        action_type=ActionType.MOVE, destination="~/Photos/{ext}/{stem}"
                    ),
                ),
            ],
        )
        engine = PreviewEngine()
        result = engine.preview(rs, tmp_path)
        assert result.match_count == 1
        assert "jpg/photo" in result.matches[0].destination

    def test_preview_summary(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("a")
        rs = RuleSet(name="test")
        engine = PreviewEngine()
        result = engine.preview(rs, tmp_path)
        assert "0 matched" in result.summary


# ---------------------------------------------------------------------------
# CLI tests
# ---------------------------------------------------------------------------


class TestRulesCLI:
    def test_rules_help(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["rules", "--help"])
        assert result.exit_code == 0
        assert "rules" in result.output.lower()

    def test_rules_list_help(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["rules", "list", "--help"])
        assert result.exit_code == 0

    def test_rules_preview_help(self) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        runner = CliRunner()
        result = runner.invoke(app, ["rules", "preview", "--help"])
        assert result.exit_code == 0
