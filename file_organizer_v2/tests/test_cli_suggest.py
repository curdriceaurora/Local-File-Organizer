"""Tests for the suggest Typer sub-app."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

runner = CliRunner()


class _MockSuggestionType(Enum):
    MOVE = "move"
    RENAME = "rename"


@pytest.fixture
def mock_engine():
    """Return a mock SuggestionEngine that yields no suggestions."""
    engine = MagicMock()
    engine.generate_suggestions.return_value = []
    return engine


@pytest.fixture
def mock_engine_with_suggestions():
    """Return a mock SuggestionEngine with sample suggestions."""
    engine = MagicMock()

    suggestion = MagicMock()
    suggestion.suggestion_id = "s1"
    suggestion.suggestion_type = _MockSuggestionType.MOVE
    suggestion.file_path = Path("/tmp/doc.txt")
    suggestion.target_path = Path("/tmp/Documents/doc.txt")
    suggestion.confidence = 75.0
    suggestion.reasoning = "Matches document pattern"
    suggestion.new_name = None

    engine.generate_suggestions.return_value = [suggestion]
    return engine


@pytest.fixture
def mock_analyzer():
    """Return a mock PatternAnalyzer."""
    analyzer = MagicMock()
    analysis = MagicMock()
    analysis.total_files = 10
    analysis.naming_patterns = []
    analysis.file_type_distribution = {".txt": 5, ".py": 3, ".md": 2}
    analyzer.analyze_directory.return_value = analysis
    return analyzer


@pytest.fixture
def mock_analyzer_with_patterns():
    """Return a mock PatternAnalyzer with detected patterns."""
    analyzer = MagicMock()
    analysis = MagicMock()
    analysis.total_files = 20

    pattern = MagicMock()
    pattern.pattern = "DATE_PREFIX"
    pattern.count = 8
    pattern.confidence = 85.0
    pattern.description = "Files prefixed with date"
    pattern.example_files = ["2025-01-01_notes.txt", "2025-02-15_report.pdf"]

    analysis.naming_patterns = [pattern]
    analysis.file_type_distribution = {".txt": 10, ".pdf": 10}
    analyzer.analyze_directory.return_value = analysis
    return analyzer


class TestSuggestImports:
    """Test that the module imports correctly."""

    def test_import_suggest_app(self) -> None:
        from file_organizer.cli.suggest import suggest_app

        assert suggest_app is not None


class TestSuggestFiles:
    """Tests for the files command."""

    def test_files_no_results(
        self,
        tmp_path: Path,
        mock_engine: MagicMock,
        mock_analyzer: MagicMock,
    ) -> None:
        from file_organizer.cli.suggest import suggest_app

        # Create a file so the directory isn't empty
        (tmp_path / "test.txt").touch()

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(tmp_path)])
        assert result.exit_code == 0
        assert "no suggestions" in result.output.lower()

    def test_files_with_suggestions(
        self,
        tmp_path: Path,
        mock_engine_with_suggestions: MagicMock,
        mock_analyzer: MagicMock,
    ) -> None:
        from file_organizer.cli.suggest import suggest_app

        (tmp_path / "doc.txt").touch()

        with (
            patch(
                "file_organizer.cli.suggest._get_engine",
                return_value=mock_engine_with_suggestions,
            ),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(tmp_path)])
        assert result.exit_code == 0
        assert "move" in result.output.lower() or "Suggestions" in result.output

    def test_files_json_output(
        self,
        tmp_path: Path,
        mock_engine_with_suggestions: MagicMock,
        mock_analyzer: MagicMock,
    ) -> None:
        from file_organizer.cli.suggest import suggest_app

        (tmp_path / "doc.txt").touch()

        with (
            patch(
                "file_organizer.cli.suggest._get_engine",
                return_value=mock_engine_with_suggestions,
            ),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(tmp_path), "--json"])
        assert result.exit_code == 0
        assert "doc.txt" in result.output

    def test_files_empty_directory(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        result = runner.invoke(suggest_app, ["files", str(tmp_path)])
        assert result.exit_code == 0
        assert "no files" in result.output.lower()


class TestSuggestPatterns:
    """Tests for the patterns command."""

    def test_patterns_no_patterns(self, tmp_path: Path, mock_analyzer: MagicMock) -> None:
        from file_organizer.cli.suggest import suggest_app

        with patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer):
            result = runner.invoke(suggest_app, ["patterns", str(tmp_path)])
        assert result.exit_code == 0

    def test_patterns_with_results(
        self, tmp_path: Path, mock_analyzer_with_patterns: MagicMock
    ) -> None:
        from file_organizer.cli.suggest import suggest_app

        with patch(
            "file_organizer.cli.suggest._get_analyzer",
            return_value=mock_analyzer_with_patterns,
        ):
            result = runner.invoke(suggest_app, ["patterns", str(tmp_path)])
        assert result.exit_code == 0
        assert "DATE_PREFIX" in result.output

    def test_patterns_json(self, tmp_path: Path, mock_analyzer_with_patterns: MagicMock) -> None:
        from file_organizer.cli.suggest import suggest_app

        with patch(
            "file_organizer.cli.suggest._get_analyzer",
            return_value=mock_analyzer_with_patterns,
        ):
            result = runner.invoke(suggest_app, ["patterns", str(tmp_path), "--json"])
        assert result.exit_code == 0
        assert "DATE_PREFIX" in result.output


class TestSuggestApply:
    """Tests for the apply command."""

    def test_apply_no_suggestions(
        self,
        tmp_path: Path,
        mock_engine: MagicMock,
        mock_analyzer: MagicMock,
    ) -> None:
        from file_organizer.cli.suggest import suggest_app

        (tmp_path / "test.txt").touch()

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["apply", str(tmp_path)])
        assert result.exit_code == 0
        assert "no suggestions" in result.output.lower()

    def test_apply_dry_run(
        self,
        tmp_path: Path,
        mock_engine_with_suggestions: MagicMock,
        mock_analyzer: MagicMock,
    ) -> None:
        from file_organizer.cli.suggest import suggest_app

        (tmp_path / "doc.txt").touch()

        with (
            patch(
                "file_organizer.cli.suggest._get_engine",
                return_value=mock_engine_with_suggestions,
            ),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["apply", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in result.output.lower()
