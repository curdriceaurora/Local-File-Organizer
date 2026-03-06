"""Tests for file_organizer.services.copilot.intent_parser.

Covers IntentParser.parse() keyword matching, confidence scoring,
parameter extraction for every intent type, and edge cases.
"""

from __future__ import annotations

import pytest

from file_organizer.services.copilot.intent_parser import IntentParser
from file_organizer.services.copilot.models import IntentType


@pytest.fixture()
def parser() -> IntentParser:
    return IntentParser()


# ------------------------------------------------------------------ #
# Empty / fallback
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestParseEdgeCases:
    """Edge cases for the parse method."""

    def test_empty_string_returns_unknown(self, parser: IntentParser) -> None:
        intent = parser.parse("")
        assert intent.intent_type == IntentType.UNKNOWN
        assert intent.confidence == 0.0

    def test_whitespace_only_returns_unknown(self, parser: IntentParser) -> None:
        intent = parser.parse("   ")
        assert intent.intent_type == IntentType.UNKNOWN
        assert intent.confidence == 0.0

    def test_no_keyword_match_returns_chat(self, parser: IntentParser) -> None:
        intent = parser.parse("the weather is nice today")
        assert intent.intent_type == IntentType.CHAT
        assert intent.confidence == pytest.approx(0.3)

    def test_raw_text_preserved(self, parser: IntentParser) -> None:
        text = "organize my files"
        intent = parser.parse(text)
        assert intent.raw_text == text

    def test_context_parameter_accepted(self, parser: IntentParser) -> None:
        """Context param is accepted even though unused by keyword parser."""
        intent = parser.parse("help", context="previous conversation")
        assert intent.intent_type == IntentType.HELP


# ------------------------------------------------------------------ #
# Undo / Redo (highest confidence)
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestUndoRedo:
    """Tests for undo/redo intent detection."""

    def test_undo_exact(self, parser: IntentParser) -> None:
        intent = parser.parse("undo")
        assert intent.intent_type == IntentType.UNDO
        assert intent.confidence == pytest.approx(0.95)

    def test_undo_in_sentence(self, parser: IntentParser) -> None:
        intent = parser.parse("please undo the last action")
        assert intent.intent_type == IntentType.UNDO

    def test_redo_exact(self, parser: IntentParser) -> None:
        intent = parser.parse("redo")
        assert intent.intent_type == IntentType.REDO
        assert intent.confidence == pytest.approx(0.95)

    def test_redo_in_sentence(self, parser: IntentParser) -> None:
        intent = parser.parse("can you redo that?")
        assert intent.intent_type == IntentType.REDO


# ------------------------------------------------------------------ #
# Organize
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestOrganize:
    """Tests for organize intent detection and parameter extraction."""

    @pytest.mark.parametrize(
        "text",
        [
            "organise my Downloads folder",
            "organize these files",
            "sort my files by type",
            "clean up the desktop",
            "tidy my documents",
            "categorize these",
        ],
    )
    def test_organize_keywords(self, parser: IntentParser, text: str) -> None:
        intent = parser.parse(text)
        assert intent.intent_type == IntentType.ORGANIZE
        assert intent.confidence == pytest.approx(0.85)

    def test_organize_with_path(self, parser: IntentParser) -> None:
        intent = parser.parse("organize ~/Downloads")
        assert intent.intent_type == IntentType.ORGANIZE
        assert intent.parameters.get("source") == "~/Downloads"
        assert intent.parameters.get("paths") == ["~/Downloads"]

    def test_organize_with_two_paths(self, parser: IntentParser) -> None:
        intent = parser.parse("organize ~/Downloads ~/Sorted")
        assert intent.parameters.get("source") == "~/Downloads"
        assert intent.parameters.get("destination") == "~/Sorted"

    def test_organize_dry_run_flag(self, parser: IntentParser) -> None:
        intent = parser.parse("organize ~/Downloads dry-run")
        assert intent.parameters.get("dry_run") is True

    def test_organize_preview_flag(self, parser: IntentParser) -> None:
        intent = parser.parse("organize ~/Downloads preview")
        assert intent.parameters.get("dry_run") is True


# ------------------------------------------------------------------ #
# Move
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestMove:
    """Tests for move intent detection and parameter extraction."""

    @pytest.mark.parametrize(
        "text",
        [
            "move this file",
            "relocate the document",
            "transfer the archive",
        ],
    )
    def test_move_keywords(self, parser: IntentParser, text: str) -> None:
        intent = parser.parse(text)
        assert intent.intent_type == IntentType.MOVE

    def test_move_with_paths(self, parser: IntentParser) -> None:
        intent = parser.parse("move ~/file.txt ~/archive/file.txt")
        assert intent.intent_type == IntentType.MOVE
        assert intent.parameters["source"] == "~/file.txt"
        assert intent.parameters["destination"] == "~/archive/file.txt"

    def test_move_single_path(self, parser: IntentParser) -> None:
        intent = parser.parse("move ~/file.txt somewhere")
        assert intent.parameters.get("source") == "~/file.txt"
        assert "destination" not in intent.parameters


# ------------------------------------------------------------------ #
# Rename
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestRename:
    """Tests for rename intent detection and parameter extraction."""

    def test_rename_keyword(self, parser: IntentParser) -> None:
        intent = parser.parse("rename the file")
        assert intent.intent_type == IntentType.RENAME

    def test_change_name_keyword(self, parser: IntentParser) -> None:
        intent = parser.parse("change the name of this document")
        assert intent.intent_type == IntentType.RENAME

    def test_rename_with_quoted_name(self, parser: IntentParser) -> None:
        intent = parser.parse('rename ~/doc.txt "new_name.txt"')
        assert intent.parameters.get("new_name") == "new_name.txt"
        assert intent.parameters.get("target") == "~/doc.txt"

    def test_rename_with_single_quoted_name(self, parser: IntentParser) -> None:
        intent = parser.parse("rename ~/doc.txt 'new_name.txt'")
        assert intent.parameters.get("new_name") == "new_name.txt"


# ------------------------------------------------------------------ #
# Find
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestFind:
    """Tests for find intent detection and parameter extraction."""

    @pytest.mark.parametrize(
        "text,expected_query",
        [
            ("find budget report", "budget report"),
            ("search for tax documents", "for tax documents"),
            (
                "where is my resume",
                None,
            ),  # "where is" matches, query extraction uses different keywords
            ("locate the contract", "the contract"),
            ("look for vacation photos", "vacation photos"),
        ],
    )
    def test_find_keywords_and_query(
        self,
        parser: IntentParser,
        text: str,
        expected_query: str | None,
    ) -> None:
        intent = parser.parse(text)
        assert intent.intent_type == IntentType.FIND
        if expected_query is not None:
            assert intent.parameters.get("query") == expected_query

    def test_find_with_path(self, parser: IntentParser) -> None:
        intent = parser.parse("find ~/Documents/report.pdf")
        assert intent.intent_type == IntentType.FIND
        assert "~/Documents/report.pdf" in intent.parameters.get("paths", [])


# ------------------------------------------------------------------ #
# Preview
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestPreview:
    """Tests for preview intent detection."""

    @pytest.mark.parametrize(
        "text",
        [
            "preview changes",
            "dry run the operation",
            "dry-run this",
        ],
    )
    def test_preview_keywords(self, parser: IntentParser, text: str) -> None:
        intent = parser.parse(text)
        assert intent.intent_type == IntentType.PREVIEW

    def test_what_would_with_organize_picks_organize(self, parser: IntentParser) -> None:
        """'organize' (0.85) beats 'what would' preview (0.80)."""
        intent = parser.parse("what would happen if I organize?")
        assert intent.intent_type == IntentType.ORGANIZE

    def test_simulate_with_move_picks_move(self, parser: IntentParser) -> None:
        """'move' (0.85) beats 'simulate' preview (0.80)."""
        intent = parser.parse("simulate the move")
        assert intent.intent_type == IntentType.MOVE

    def test_simulate_alone_picks_preview(self, parser: IntentParser) -> None:
        intent = parser.parse("simulate the operation")
        assert intent.intent_type == IntentType.PREVIEW

    def test_what_would_alone_picks_preview(self, parser: IntentParser) -> None:
        intent = parser.parse("what would happen?")
        assert intent.intent_type == IntentType.PREVIEW


# ------------------------------------------------------------------ #
# Suggest
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestSuggest:
    """Tests for suggest intent detection."""

    @pytest.mark.parametrize(
        "text",
        [
            "suggest a location",
            "recommend where to put this",
            "where should I save this?",
            "is there a better location?",
        ],
    )
    def test_suggest_keywords(self, parser: IntentParser, text: str) -> None:
        intent = parser.parse(text)
        assert intent.intent_type == IntentType.SUGGEST


# ------------------------------------------------------------------ #
# Status
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestStatus:
    """Tests for status intent detection."""

    @pytest.mark.parametrize(
        "text",
        [
            "status",
            "how many files are left?",
            "show me the statistics",
            "what are the stats?",
        ],
    )
    def test_status_keywords(self, parser: IntentParser, text: str) -> None:
        intent = parser.parse(text)
        assert intent.intent_type == IntentType.STATUS


# ------------------------------------------------------------------ #
# Help
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestHelp:
    """Tests for help intent detection."""

    @pytest.mark.parametrize(
        "text",
        [
            "help",
            "what can you do?",
            "show me available commands",
            "what are your capabilities?",
        ],
    )
    def test_help_keywords(self, parser: IntentParser, text: str) -> None:
        intent = parser.parse(text)
        assert intent.intent_type == IntentType.HELP


# ------------------------------------------------------------------ #
# Parameter extraction helpers
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestParameterExtraction:
    """Tests for _extract_parameters static method and quoted args."""

    def test_double_quoted_args(self, parser: IntentParser) -> None:
        intent = parser.parse('find "my report" in ~/Documents')
        assert "my report" in intent.parameters.get("quoted_args", [])

    def test_single_quoted_args(self, parser: IntentParser) -> None:
        intent = parser.parse("find 'my report'")
        assert "my report" in intent.parameters.get("quoted_args", [])

    def test_windows_path_extraction(self, parser: IntentParser) -> None:
        intent = parser.parse(r"move C:\Users\test\file.txt somewhere")
        paths = intent.parameters.get("paths", [])
        assert any("C:\\" in p for p in paths)

    def test_no_params_for_simple_text(self, parser: IntentParser) -> None:
        intent = parser.parse("hello there")
        assert intent.parameters.get("paths") is None
        assert intent.parameters.get("quoted_args") is None

    def test_multiple_paths(self, parser: IntentParser) -> None:
        intent = parser.parse("organize ~/src ~/dest ~/extra")
        paths = intent.parameters.get("paths", [])
        assert len(paths) == 3


# ------------------------------------------------------------------ #
# Confidence precedence
# ------------------------------------------------------------------ #


@pytest.mark.unit
class TestConfidencePrecedence:
    """Verify that higher-confidence intents win over lower ones."""

    def test_undo_beats_help(self, parser: IntentParser) -> None:
        """undo (0.95) should beat help (0.70) when both present."""
        intent = parser.parse("undo help")
        assert intent.intent_type == IntentType.UNDO

    def test_organize_beats_status(self, parser: IntentParser) -> None:
        """organize (0.85) should beat status (0.70)."""
        intent = parser.parse("organize status report files")
        assert intent.intent_type == IntentType.ORGANIZE

    def test_case_insensitive(self, parser: IntentParser) -> None:
        intent = parser.parse("ORGANIZE MY FILES")
        assert intent.intent_type == IntentType.ORGANIZE
