"""Integration tests for cli/suggest.py.

Covers:
- files command: table output, --json flag, empty directory, no suggestions above threshold
- apply command: dry-run mode, no files found path
- patterns command: table output, --json flag, no patterns, empty directory
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.suggest import suggest_app

pytestmark = [pytest.mark.integration, pytest.mark.ci]

runner = CliRunner()

# ---------------------------------------------------------------------------
# Suggestion model helpers
# ---------------------------------------------------------------------------


def _make_suggestion_type_mock(value: str) -> MagicMock:
    m = MagicMock()
    m.value = value
    return m


def _make_suggestion(
    *,
    sid: str = "s1",
    stype: str = "move",
    file_path: Path | None = None,
    target_path: Path | None = None,
    confidence: float = 85.0,
    reasoning: str = "Files of similar type grouped together",
    new_name: str | None = None,
) -> MagicMock:
    s = MagicMock()
    s.suggestion_id = sid
    s.suggestion_type = _make_suggestion_type_mock(stype)
    s.file_path = file_path or Path("/tmp/report.pdf")
    s.target_path = target_path
    s.confidence = confidence
    s.reasoning = reasoning
    s.new_name = new_name
    return s


def _make_naming_pattern(
    *,
    pattern: str = "date_prefix",
    count: int = 5,
    confidence: float = 80.0,
    description: str = "Files prefixed with a date",
    example_files: list[str] | None = None,
) -> MagicMock:
    p = MagicMock()
    p.pattern = pattern
    p.count = count
    p.confidence = confidence
    p.description = description
    p.example_files = example_files or ["2024-01-report.pdf", "2024-02-notes.txt"]
    return p


def _make_analysis(
    *,
    total_files: int = 10,
    naming_patterns: list[Any] | None = None,
    file_type_distribution: dict[str, int] | None = None,
) -> MagicMock:
    a = MagicMock()
    a.total_files = total_files
    a.naming_patterns = naming_patterns if naming_patterns is not None else []
    a.file_type_distribution = file_type_distribution or {".pdf": 4, ".txt": 6}
    return a


# ---------------------------------------------------------------------------
# files command
# ---------------------------------------------------------------------------


class TestFilesCommand:
    """Tests for the ``suggest files`` command."""

    def test_files_table_output(self, tmp_path: Path) -> None:
        """Normal path: shows Rich table with suggestions."""
        src = tmp_path / "docs"
        src.mkdir()
        (src / "report.pdf").write_bytes(b"pdf")

        suggestion = _make_suggestion(
            file_path=src / "report.pdf",
            target_path=tmp_path / "archive" / "report.pdf",
        )
        analysis = _make_analysis()
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(src)])

        assert result.exit_code == 0
        assert "Suggestions" in result.output
        assert "move" in result.output

    def test_files_json_output(self, tmp_path: Path) -> None:
        """--json flag produces valid JSON array."""
        import json

        src = tmp_path / "docs"
        src.mkdir()
        (src / "notes.txt").write_text("hello")

        suggestion = _make_suggestion(
            sid="abc123",
            stype="rename",
            file_path=src / "notes.txt",
            target_path=None,
            confidence=75.0,
            reasoning="Better naming convention detected",
        )
        analysis = _make_analysis()
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(src), "--json"])

        assert result.exit_code == 0
        # Parse first valid JSON array from output
        output = result.output
        start = output.find("[")
        parsed = json.loads(output[start:])
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["id"] == "abc123"
        assert parsed[0]["type"] == "rename"
        assert parsed[0]["confidence"] == 75.0

    def test_files_no_files_in_directory(self, tmp_path: Path) -> None:
        """Empty directory exits 0 with an informational message."""
        empty = tmp_path / "empty"
        empty.mkdir()

        mock_engine = MagicMock()
        mock_analyzer = MagicMock()

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(empty)])

        assert result.exit_code == 0
        assert "No files" in result.output

    def test_files_no_suggestions_above_threshold(self, tmp_path: Path) -> None:
        """When all suggestions are below min_confidence, shows 'no suggestions' message."""
        src = tmp_path / "docs"
        src.mkdir()
        (src / "doc.txt").write_text("content")

        low_confidence_suggestion = _make_suggestion(confidence=10.0)
        analysis = _make_analysis()
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [low_confidence_suggestion]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(src), "--min-confidence", "50"])

        assert result.exit_code == 0
        assert "No suggestions" in result.output

    def test_files_with_target_path_shown_in_table(self, tmp_path: Path) -> None:
        """Suggestions with target_path show the path in the table."""
        src = tmp_path / "docs"
        src.mkdir()
        (src / "invoice.pdf").write_bytes(b"pdf")

        target = tmp_path / "invoices" / "invoice.pdf"
        suggestion = _make_suggestion(
            file_path=src / "invoice.pdf",
            target_path=target,
            confidence=90.0,
        )
        analysis = _make_analysis()
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(src)])

        assert result.exit_code == 0
        assert "invoice" in result.output.lower() or "90" in result.output

    def test_files_dry_run_flag_accepted(self, tmp_path: Path) -> None:
        """--dry-run flag is accepted without error."""
        src = tmp_path / "docs"
        src.mkdir()
        (src / "file.txt").write_text("x")

        suggestion = _make_suggestion(confidence=70.0)
        analysis = _make_analysis()
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(src), "--dry-run"])

        assert result.exit_code == 0

    def test_files_json_no_target_path_is_null(self, tmp_path: Path) -> None:
        """target=None is serialized as null in JSON output."""
        import json

        src = tmp_path / "docs"
        src.mkdir()
        (src / "a.txt").write_text("x")

        suggestion = _make_suggestion(
            sid="no-target",
            stype="rename",
            file_path=src / "a.txt",
            target_path=None,
            confidence=60.0,
            reasoning="Rename suggested",
        )
        analysis = _make_analysis()
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(src), "--json"])

        assert result.exit_code == 0
        output = result.output
        start = output.find("[")
        parsed = json.loads(output[start:])
        assert parsed[0]["target"] is None


# ---------------------------------------------------------------------------
# apply command
# ---------------------------------------------------------------------------


class TestApplyCommand:
    """Tests for the ``suggest apply`` command."""

    def test_apply_dry_run_prints_would_apply(self, tmp_path: Path) -> None:
        """--dry-run prints 'Would apply' lines without making file changes."""
        src = tmp_path / "docs"
        src.mkdir()
        the_file = src / "report.txt"
        the_file.write_text("content")

        target = tmp_path / "archive" / "report.txt"
        suggestion = _make_suggestion(
            file_path=the_file,
            target_path=target,
            confidence=80.0,
        )
        analysis = _make_analysis()
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["apply", str(src), "--dry-run"])

        assert result.exit_code == 0
        assert "Would apply" in result.output or "Dry run" in result.output
        # File must not have been moved
        assert the_file.exists()

    def test_apply_no_files_exits_zero(self, tmp_path: Path) -> None:
        """Empty directory produces an informational message and exits 0."""
        empty = tmp_path / "empty"
        empty.mkdir()

        mock_engine = MagicMock()
        mock_analyzer = MagicMock()

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["apply", str(empty)])

        assert result.exit_code == 0
        assert "No files" in result.output

    def test_apply_no_suggestions_above_threshold(self, tmp_path: Path) -> None:
        """When all suggestions are below min_confidence, prints 'no suggestions to apply'."""
        src = tmp_path / "docs"
        src.mkdir()
        (src / "doc.txt").write_text("x")

        low_sug = _make_suggestion(confidence=30.0)
        analysis = _make_analysis()
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [low_sug]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["apply", str(src)])

        assert result.exit_code == 0
        assert "No suggestions" in result.output

    def test_apply_dry_run_shows_summary_line(self, tmp_path: Path) -> None:
        """Dry-run always ends with a 'Dry run — no changes' summary."""
        src = tmp_path / "docs"
        src.mkdir()
        (src / "x.pdf").write_bytes(b"pdf")

        suggestion = _make_suggestion(
            file_path=src / "x.pdf",
            target_path=tmp_path / "pdfs" / "x.pdf",
            confidence=75.0,
        )
        analysis = _make_analysis()
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["apply", str(src), "--dry-run"])

        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "dry run" in output_lower or "no changes" in output_lower


# ---------------------------------------------------------------------------
# patterns command
# ---------------------------------------------------------------------------


class TestPatternsCommand:
    """Tests for the ``suggest patterns`` command."""

    def test_patterns_table_output(self, tmp_path: Path) -> None:
        """Normal path: shows table with detected naming patterns."""
        src = tmp_path / "docs"
        src.mkdir()
        (src / "2024-01-report.pdf").write_bytes(b"pdf")

        pattern = _make_naming_pattern()
        analysis = _make_analysis(total_files=5, naming_patterns=[pattern])
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer):
            result = runner.invoke(suggest_app, ["patterns", str(src)])

        assert result.exit_code == 0
        # Should show the pattern analysis header or table
        output_lower = result.output.lower()
        assert "pattern" in output_lower or "5" in result.output

    def test_patterns_json_output(self, tmp_path: Path) -> None:
        """--json flag produces JSON with expected keys."""
        import json

        src = tmp_path / "docs"
        src.mkdir()
        (src / "file.txt").write_text("x")

        pattern = _make_naming_pattern(
            pattern="snake_case",
            count=3,
            confidence=72.0,
            description="Snake case naming",
            example_files=["my_doc.txt", "another_file.txt"],
        )
        analysis = _make_analysis(
            total_files=8,
            naming_patterns=[pattern],
            file_type_distribution={".txt": 5, ".pdf": 3},
        )
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer):
            result = runner.invoke(suggest_app, ["patterns", str(src), "--json"])

        assert result.exit_code == 0
        output = result.output
        start = output.find("{")
        parsed = json.loads(output[start:])
        assert parsed["total_files"] == 8
        assert len(parsed["naming_patterns"]) == 1
        assert parsed["naming_patterns"][0]["pattern"] == "snake_case"
        assert parsed["naming_patterns"][0]["count"] == 3
        assert parsed["file_type_distribution"][".txt"] == 5

    def test_patterns_no_naming_patterns_detected(self, tmp_path: Path) -> None:
        """When no naming patterns are found, shows 'No naming patterns' message."""
        src = tmp_path / "misc"
        src.mkdir()
        (src / "a.txt").write_text("x")

        analysis = _make_analysis(total_files=1, naming_patterns=[], file_type_distribution={})
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer):
            result = runner.invoke(suggest_app, ["patterns", str(src)])

        assert result.exit_code == 0
        assert "No naming patterns" in result.output

    def test_patterns_file_type_distribution_shown(self, tmp_path: Path) -> None:
        """File type distribution table is shown when distribution is non-empty."""
        src = tmp_path / "docs"
        src.mkdir()
        (src / "a.pdf").write_bytes(b"pdf")

        analysis = _make_analysis(
            total_files=4,
            naming_patterns=[],
            file_type_distribution={".pdf": 3, ".txt": 1},
        )
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer):
            result = runner.invoke(suggest_app, ["patterns", str(src)])

        assert result.exit_code == 0
        assert ".pdf" in result.output or "pdf" in result.output.lower()

    def test_patterns_json_empty_patterns(self, tmp_path: Path) -> None:
        """--json with no patterns produces JSON with empty naming_patterns list."""
        import json

        src = tmp_path / "docs"
        src.mkdir()
        (src / "only.txt").write_text("x")

        analysis = _make_analysis(
            total_files=1,
            naming_patterns=[],
            file_type_distribution={".txt": 1},
        )
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer):
            result = runner.invoke(suggest_app, ["patterns", str(src), "--json"])

        assert result.exit_code == 0
        output = result.output
        start = output.find("{")
        parsed = json.loads(output[start:])
        assert parsed["naming_patterns"] == []
        assert parsed["total_files"] == 1
