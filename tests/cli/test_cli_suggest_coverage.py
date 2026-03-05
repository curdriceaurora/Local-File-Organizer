"""Coverage tests for file_organizer.cli.suggest — uncovered lines 27-236."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

runner = CliRunner()


# Stub types
class _FakeSuggestionType(Enum):
    MOVE = "move"
    RENAME = "rename"


@dataclass
class _FakeSuggestion:
    suggestion_id: str = "s1"
    suggestion_type: _FakeSuggestionType = _FakeSuggestionType.MOVE
    file_path: Path = Path("/tmp/a.txt")
    target_path: Path | None = Path("/tmp/docs/a.txt")
    confidence: float = 75.0
    reasoning: str = "File matches docs pattern"
    new_name: str | None = None


@dataclass
class _FakeNamingPattern:
    pattern: str = "date_prefix"
    count: int = 5
    confidence: float = 80.0
    description: str = "Date-prefixed files"
    example_files: list[str] = field(default_factory=lambda: ["2024-report.pdf"])


@dataclass
class _FakeAnalysis:
    total_files: int = 10
    naming_patterns: list = field(default_factory=list)
    file_type_distribution: dict = field(default_factory=dict)


class TestSuggestFiles:
    """Covers files command."""

    def test_no_files(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        result = runner.invoke(suggest_app, ["files", str(tmp_path)])
        assert "No files found" in result.output

    def test_with_suggestions_table(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        (tmp_path / "a.txt").write_text("hello")

        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [
            _FakeSuggestion(confidence=75.0),
        ]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = _FakeAnalysis()

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(tmp_path)])

        assert result.exit_code == 0

    def test_with_json_output(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        (tmp_path / "a.txt").write_text("hello")

        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [
            _FakeSuggestion(confidence=75.0),
        ]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = _FakeAnalysis()

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(tmp_path), "--json"])

        assert result.exit_code == 0

    def test_no_suggestions_above_threshold(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        (tmp_path / "a.txt").write_text("hello")

        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [
            _FakeSuggestion(confidence=5.0),
        ]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = _FakeAnalysis()

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["files", str(tmp_path)])

        assert "No suggestions" in result.output


class TestSuggestApply:
    """Covers apply command."""

    def test_apply_no_files(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        result = runner.invoke(suggest_app, ["apply", str(tmp_path)])
        assert "No files found" in result.output

    def test_apply_dry_run(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        (tmp_path / "a.txt").write_text("hello")

        suggestion = _FakeSuggestion(
            confidence=75.0,
            target_path=tmp_path / "docs" / "a.txt",
        )
        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = _FakeAnalysis()

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["apply", str(tmp_path), "--dry-run"])

        assert "Dry run" in result.output

    def test_apply_no_suggestions(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        (tmp_path / "a.txt").write_text("hello")

        mock_engine = MagicMock()
        mock_engine.generate_suggestions.return_value = []
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = _FakeAnalysis()

        with (
            patch("file_organizer.cli.suggest._get_engine", return_value=mock_engine),
            patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer),
        ):
            result = runner.invoke(suggest_app, ["apply", str(tmp_path)])

        assert "No suggestions" in result.output


class TestSuggestPatterns:
    """Covers patterns command."""

    def test_patterns_json(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        analysis = _FakeAnalysis(
            naming_patterns=[_FakeNamingPattern()],
            file_type_distribution={".pdf": 3, ".txt": 7},
        )
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer):
            result = runner.invoke(suggest_app, ["patterns", str(tmp_path), "--json"])

        assert result.exit_code == 0

    def test_patterns_table(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        analysis = _FakeAnalysis(
            naming_patterns=[_FakeNamingPattern()],
            file_type_distribution={".pdf": 3},
        )
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer):
            result = runner.invoke(suggest_app, ["patterns", str(tmp_path)])

        assert result.exit_code == 0
        assert "Pattern Analysis" in result.output

    def test_patterns_no_patterns(self, tmp_path: Path) -> None:
        from file_organizer.cli.suggest import suggest_app

        analysis = _FakeAnalysis(naming_patterns=[], file_type_distribution={})
        mock_analyzer = MagicMock()
        mock_analyzer.analyze_directory.return_value = analysis

        with patch("file_organizer.cli.suggest._get_analyzer", return_value=mock_analyzer):
            result = runner.invoke(suggest_app, ["patterns", str(tmp_path)])

        assert result.exit_code == 0
        assert "No naming patterns" in result.output
