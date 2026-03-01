"""Tests for file_organizer.services.copilot.rules.preview module.

Covers PreviewEngine, FileMatch, PreviewResult dataclass, and all
condition types including SIZE_GREATER, SIZE_LESS, CONTENT_CONTAINS,
MODIFIED_BEFORE, MODIFIED_AFTER, and PATH_MATCHES.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from file_organizer.services.copilot.rules.models import (
    ActionType,
    ConditionType,
    Rule,
    RuleAction,
    RuleCondition,
    RuleSet,
)
from file_organizer.services.copilot.rules.preview import (
    FileMatch,
    PreviewEngine,
    PreviewResult,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# FileMatch dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestFileMatch:
    """Test the FileMatch dataclass."""

    def test_defaults(self):
        fm = FileMatch(
            file_path="/a.txt",
            rule_name="r1",
            action_type="move",
            destination="/dest",
        )
        assert fm.confidence == 1.0
        assert fm.file_path == "/a.txt"

    def test_custom_confidence(self):
        fm = FileMatch(
            file_path="/b.txt",
            rule_name="r2",
            action_type="tag",
            destination="/x",
            confidence=0.5,
        )
        assert fm.confidence == 0.5


# ---------------------------------------------------------------------------
# PreviewResult dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreviewResult:
    """Test the PreviewResult dataclass."""

    def test_empty_result(self):
        r = PreviewResult()
        assert r.match_count == 0
        assert r.total_files == 0
        assert "0 matched" in r.summary

    def test_summary_with_data(self):
        r = PreviewResult(
            matches=[
                FileMatch("/a.txt", "r1", "move", "/dest"),
                FileMatch("/b.txt", "r2", "move", "/dest"),
            ],
            unmatched=["/c.txt"],
            errors=[("/d.txt", "oops")],
            total_files=4,
        )
        assert r.match_count == 2
        assert "2 matched" in r.summary
        assert "1 unmatched" in r.summary
        assert "1 errors" in r.summary
        assert "4 total" in r.summary


# ---------------------------------------------------------------------------
# PreviewEngine._evaluate_condition — SIZE_GREATER
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConditionSizeGreater:
    """Test SIZE_GREATER condition."""

    def test_size_greater_true(self, tmp_path):
        f = tmp_path / "big.bin"
        f.write_bytes(b"x" * 200)
        cond = RuleCondition(ConditionType.SIZE_GREATER, "100")
        assert PreviewEngine._evaluate_condition(f, cond) is True

    def test_size_greater_false(self, tmp_path):
        f = tmp_path / "small.bin"
        f.write_bytes(b"x" * 10)
        cond = RuleCondition(ConditionType.SIZE_GREATER, "100")
        assert PreviewEngine._evaluate_condition(f, cond) is False

    def test_size_greater_bad_value(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("hi")
        cond = RuleCondition(ConditionType.SIZE_GREATER, "notanumber")
        assert PreviewEngine._evaluate_condition(f, cond) is False

    def test_size_greater_missing_file(self, tmp_path):
        f = tmp_path / "missing.txt"
        cond = RuleCondition(ConditionType.SIZE_GREATER, "10")
        assert PreviewEngine._evaluate_condition(f, cond) is False


# ---------------------------------------------------------------------------
# PreviewEngine._evaluate_condition — SIZE_LESS
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConditionSizeLess:
    """Test SIZE_LESS condition."""

    def test_size_less_true(self, tmp_path):
        f = tmp_path / "small.bin"
        f.write_bytes(b"x" * 5)
        cond = RuleCondition(ConditionType.SIZE_LESS, "100")
        assert PreviewEngine._evaluate_condition(f, cond) is True

    def test_size_less_false(self, tmp_path):
        f = tmp_path / "big.bin"
        f.write_bytes(b"x" * 200)
        cond = RuleCondition(ConditionType.SIZE_LESS, "100")
        assert PreviewEngine._evaluate_condition(f, cond) is False


# ---------------------------------------------------------------------------
# PreviewEngine._evaluate_condition — CONTENT_CONTAINS
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConditionContentContains:
    """Test CONTENT_CONTAINS condition."""

    def test_content_found(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Hello World important info", encoding="utf-8")
        cond = RuleCondition(ConditionType.CONTENT_CONTAINS, "important")
        assert PreviewEngine._evaluate_condition(f, cond) is True

    def test_content_not_found(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Hello World", encoding="utf-8")
        cond = RuleCondition(ConditionType.CONTENT_CONTAINS, "missing")
        assert PreviewEngine._evaluate_condition(f, cond) is False

    def test_content_case_insensitive(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("IMPORTANT DATA", encoding="utf-8")
        cond = RuleCondition(ConditionType.CONTENT_CONTAINS, "important")
        assert PreviewEngine._evaluate_condition(f, cond) is True

    def test_content_missing_file(self, tmp_path):
        f = tmp_path / "nope.txt"
        cond = RuleCondition(ConditionType.CONTENT_CONTAINS, "hello")
        assert PreviewEngine._evaluate_condition(f, cond) is False


# ---------------------------------------------------------------------------
# PreviewEngine._evaluate_condition — MODIFIED_BEFORE / MODIFIED_AFTER
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConditionModifiedBefore:
    """Test MODIFIED_BEFORE condition."""

    def test_modified_before_true(self, tmp_path):
        f = tmp_path / "old.txt"
        f.write_text("old")
        # Set mod time to 2020
        old_ts = datetime(2020, 1, 1, tzinfo=UTC).timestamp()
        os.utime(f, (old_ts, old_ts))
        cond = RuleCondition(ConditionType.MODIFIED_BEFORE, "2023-01-01T00:00:00+00:00")
        assert PreviewEngine._evaluate_condition(f, cond) is True

    def test_modified_before_false(self, tmp_path):
        f = tmp_path / "new.txt"
        f.write_text("new")
        cond = RuleCondition(ConditionType.MODIFIED_BEFORE, "2000-01-01T00:00:00+00:00")
        assert PreviewEngine._evaluate_condition(f, cond) is False

    def test_modified_before_bad_value(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x")
        cond = RuleCondition(ConditionType.MODIFIED_BEFORE, "not-a-date")
        assert PreviewEngine._evaluate_condition(f, cond) is False


@pytest.mark.unit
class TestConditionModifiedAfter:
    """Test MODIFIED_AFTER condition."""

    def test_modified_after_true(self, tmp_path):
        f = tmp_path / "recent.txt"
        f.write_text("recent")
        cond = RuleCondition(ConditionType.MODIFIED_AFTER, "2000-01-01T00:00:00+00:00")
        assert PreviewEngine._evaluate_condition(f, cond) is True

    def test_modified_after_false(self, tmp_path):
        f = tmp_path / "old.txt"
        f.write_text("old")
        old_ts = datetime(1999, 6, 1, tzinfo=UTC).timestamp()
        os.utime(f, (old_ts, old_ts))
        cond = RuleCondition(ConditionType.MODIFIED_AFTER, "2000-01-01T00:00:00+00:00")
        assert PreviewEngine._evaluate_condition(f, cond) is False

    def test_modified_after_bad_value(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x")
        cond = RuleCondition(ConditionType.MODIFIED_AFTER, "bad-date")
        assert PreviewEngine._evaluate_condition(f, cond) is False


# ---------------------------------------------------------------------------
# PreviewEngine._evaluate_condition — PATH_MATCHES
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConditionPathMatches:
    """Test PATH_MATCHES condition."""

    def test_path_matches_true(self, tmp_path):
        f = tmp_path / "reports" / "q1.pdf"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"pdf")
        cond = RuleCondition(ConditionType.PATH_MATCHES, r"reports")
        assert PreviewEngine._evaluate_condition(f, cond) is True

    def test_path_matches_false(self, tmp_path):
        f = tmp_path / "downloads" / "a.txt"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
        cond = RuleCondition(ConditionType.PATH_MATCHES, r"reports")
        assert PreviewEngine._evaluate_condition(f, cond) is False


# ---------------------------------------------------------------------------
# PreviewEngine._evaluate_condition — unknown type fallback
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestConditionUnknownType:
    """Test that an unrecognized condition type returns False."""

    def test_unknown_returns_false(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x")
        cond = RuleCondition(ConditionType.PATH_MATCHES, r".*")
        # Monkey-patch condition_type to something unexpected
        cond.condition_type = "FAKE_TYPE"  # type: ignore[assignment]
        assert PreviewEngine._evaluate_condition(f, cond) is False


# ---------------------------------------------------------------------------
# PreviewEngine.preview — max_files, PermissionError, empty rules
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPreviewEngine:
    """Test PreviewEngine.preview high-level behaviour."""

    def test_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("hi")
        engine = PreviewEngine()
        result = engine.preview(RuleSet(rules=[]), f)
        assert len(result.errors) == 1
        assert "Not a directory" in result.errors[0][1]

    def test_no_enabled_rules(self, tmp_path):
        (tmp_path / "a.txt").write_text("hi")
        engine = PreviewEngine()
        rule = Rule(name="disabled", enabled=False)
        rs = RuleSet(rules=[rule])
        result = engine.preview(rs, tmp_path)
        assert result.match_count == 0

    def test_max_files_limit(self, tmp_path):
        for i in range(10):
            (tmp_path / f"f{i}.txt").write_text("x")
        engine = PreviewEngine()
        rule = Rule(
            name="catch-all",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".txt")],
            action=RuleAction(action_type=ActionType.MOVE, destination="/dest"),
        )
        rs = RuleSet(rules=[rule])
        result = engine.preview(rs, tmp_path, max_files=3)
        assert result.total_files == 3
        assert result.match_count == 3

    def test_permission_error(self, tmp_path):
        engine = PreviewEngine()
        rule = Rule(
            name="r",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".txt")],
        )
        rs = RuleSet(rules=[rule])
        with patch.object(Path, "rglob", side_effect=PermissionError("denied")):
            result = engine.preview(rs, tmp_path)
        assert len(result.errors) == 1
        assert "Permission denied" in result.errors[0][1]

    def test_unmatched_files(self, tmp_path):
        (tmp_path / "a.pdf").write_text("pdf")
        engine = PreviewEngine()
        rule = Rule(
            name="txt-only",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".txt")],
            action=RuleAction(action_type=ActionType.MOVE, destination="/dest"),
        )
        rs = RuleSet(rules=[rule])
        result = engine.preview(rs, tmp_path, recursive=False)
        assert len(result.unmatched) == 1


# ---------------------------------------------------------------------------
# PreviewEngine._resolve_destination
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestResolveDestination:
    """Test destination template resolution."""

    def test_no_destination(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x")
        rule = Rule(name="r", action=RuleAction(ActionType.MOVE, destination=""))
        result = PreviewEngine._resolve_destination(f, rule)
        assert result == str(f.parent)

    def test_template_variables(self, tmp_path):
        f = tmp_path / "report.pdf"
        f.write_bytes(b"pdf")
        rule = Rule(
            name="r",
            action=RuleAction(ActionType.MOVE, destination="/archive/{ext}/{stem}"),
        )
        result = PreviewEngine._resolve_destination(f, rule)
        assert result == "/archive/pdf/report"


# ---------------------------------------------------------------------------
# PreviewEngine._matches_rule — negation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMatchesRuleNegation:
    """Test negated conditions."""

    def test_negated_condition(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x")
        engine = PreviewEngine()
        rule = Rule(
            name="not-txt",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".pdf", negate=True)],
        )
        # a.txt does NOT have .pdf extension, negate=True means condition passes
        assert engine._matches_rule(f, rule) is True

    def test_negated_condition_blocks(self, tmp_path):
        f = tmp_path / "a.txt"
        f.write_text("x")
        engine = PreviewEngine()
        rule = Rule(
            name="not-txt",
            conditions=[RuleCondition(ConditionType.EXTENSION, ".txt", negate=True)],
        )
        # a.txt HAS .txt extension, negate=True means condition fails
        assert engine._matches_rule(f, rule) is False
