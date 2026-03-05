"""Tests for the suggest CLI sub-app (suggest.py).

Tests ``suggest files``, ``suggest apply``, and ``suggest patterns`` commands.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit]

runner = CliRunner()


def _make_suggestion(
    suggestion_id: str = "s1",
    suggestion_type: str = "move",
    file_path: Path | None = None,
    target_path: Path | None = None,
    confidence: float = 80.0,
    reasoning: str = "Better organisation",
    new_name: str | None = None,
) -> MagicMock:
    """Create a mock suggestion object."""
    s = MagicMock()
    s.suggestion_id = suggestion_id
    s.suggestion_type.value = suggestion_type
    s.file_path = file_path or Path("test.txt")
    s.target_path = target_path
    s.confidence = confidence
    s.reasoning = reasoning
    s.new_name = new_name
    return s


def _make_analysis(
    total_files: int = 5,
    naming_patterns: list | None = None,
    file_type_distribution: dict | None = None,
) -> MagicMock:
    """Create a mock pattern analysis result."""
    analysis = MagicMock()
    analysis.total_files = total_files
    analysis.naming_patterns = naming_patterns or []
    analysis.file_type_distribution = file_type_distribution or {}
    return analysis


def _make_pattern(
    pattern: str = "date_prefix",
    count: int = 10,
    confidence: float = 90.0,
    description: str = "Files with date prefix",
    example_files: list | None = None,
) -> MagicMock:
    """Create a mock naming pattern."""
    p = MagicMock()
    p.pattern = pattern
    p.count = count
    p.confidence = confidence
    p.description = description
    p.example_files = example_files or ["2025-01-report.pdf"]
    return p


# ---------------------------------------------------------------------------
# suggest files
# ---------------------------------------------------------------------------


class TestSuggestFiles:
    """Tests for ``suggest files``."""

    @patch("file_organizer.cli.suggest._get_analyzer")
    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._collect_files")
    def test_files_no_files(
        self,
        mock_collect: MagicMock,
        mock_engine: MagicMock,
        mock_analyzer: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_collect.return_value = []

        result = runner.invoke(app, ["suggest", "files", str(tmp_path)])
        assert result.exit_code == 0
        assert "No files found" in result.output

    @patch("file_organizer.cli.suggest._get_analyzer")
    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._collect_files")
    def test_files_with_suggestions(
        self,
        mock_collect: MagicMock,
        mock_get_engine: MagicMock,
        mock_get_analyzer: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_collect.return_value = [tmp_path / "a.txt"]

        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine

        mock_analyzer = MagicMock()
        mock_get_analyzer.return_value = mock_analyzer
        mock_analyzer.analyze_directory.return_value = _make_analysis()

        suggestion = _make_suggestion(
            file_path=tmp_path / "a.txt",
            target_path=tmp_path / "docs" / "a.txt",
        )
        mock_engine.generate_suggestions.return_value = [suggestion]

        result = runner.invoke(app, ["suggest", "files", str(tmp_path)])
        assert result.exit_code == 0
        assert "a.txt" in result.output

    @patch("file_organizer.cli.suggest._get_analyzer")
    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._collect_files")
    def test_files_below_threshold(
        self,
        mock_collect: MagicMock,
        mock_get_engine: MagicMock,
        mock_get_analyzer: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_collect.return_value = [tmp_path / "a.txt"]

        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_analyzer = MagicMock()
        mock_get_analyzer.return_value = mock_analyzer
        mock_analyzer.analyze_directory.return_value = _make_analysis()

        # Suggestion with low confidence
        suggestion = _make_suggestion(confidence=10.0)
        mock_engine.generate_suggestions.return_value = [suggestion]

        result = runner.invoke(app, ["suggest", "files", str(tmp_path)])
        assert result.exit_code == 0
        assert "No suggestions above confidence" in result.output


# ---------------------------------------------------------------------------
# suggest apply
# ---------------------------------------------------------------------------


class TestSuggestApply:
    """Tests for ``suggest apply``."""

    @patch("file_organizer.cli.suggest._get_analyzer")
    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._collect_files")
    def test_apply_no_files(
        self,
        mock_collect: MagicMock,
        mock_engine: MagicMock,
        mock_analyzer: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_collect.return_value = []

        result = runner.invoke(app, ["suggest", "apply", str(tmp_path)])
        assert result.exit_code == 0
        assert "No files found" in result.output

    @patch("file_organizer.cli.suggest._get_analyzer")
    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._collect_files")
    def test_apply_dry_run(
        self,
        mock_collect: MagicMock,
        mock_get_engine: MagicMock,
        mock_get_analyzer: MagicMock,
        tmp_path: Path,
    ) -> None:
        mock_collect.return_value = [tmp_path / "a.txt"]

        mock_engine = MagicMock()
        mock_get_engine.return_value = mock_engine
        mock_analyzer = MagicMock()
        mock_get_analyzer.return_value = mock_analyzer
        mock_analyzer.analyze_directory.return_value = _make_analysis()

        suggestion = _make_suggestion(
            file_path=tmp_path / "a.txt",
            target_path=tmp_path / "docs" / "a.txt",
            confidence=90.0,
        )
        mock_engine.generate_suggestions.return_value = [suggestion]

        result = runner.invoke(app, ["suggest", "apply", str(tmp_path), "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in result.output.lower() or "Dry run" in result.output


# ---------------------------------------------------------------------------
# suggest patterns
# ---------------------------------------------------------------------------


class TestSuggestPatterns:
    """Tests for ``suggest patterns``."""

    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_patterns_empty(self, mock_get_analyzer: MagicMock, tmp_path: Path) -> None:
        mock_analyzer = MagicMock()
        mock_get_analyzer.return_value = mock_analyzer
        mock_analyzer.analyze_directory.return_value = _make_analysis(
            naming_patterns=[], file_type_distribution={}
        )

        result = runner.invoke(app, ["suggest", "patterns", str(tmp_path)])
        assert result.exit_code == 0
        assert "No naming patterns" in result.output

    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_patterns_with_data(self, mock_get_analyzer: MagicMock, tmp_path: Path) -> None:
        mock_analyzer = MagicMock()
        mock_get_analyzer.return_value = mock_analyzer

        pattern = _make_pattern()
        mock_analyzer.analyze_directory.return_value = _make_analysis(
            naming_patterns=[pattern],
            file_type_distribution={".pdf": 10, ".txt": 5},
        )

        result = runner.invoke(app, ["suggest", "patterns", str(tmp_path)])
        assert result.exit_code == 0
        assert "date_prefix" in result.output
        assert ".pdf" in result.output

    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_patterns_json(self, mock_get_analyzer: MagicMock, tmp_path: Path) -> None:
        mock_analyzer = MagicMock()
        mock_get_analyzer.return_value = mock_analyzer

        pattern = _make_pattern()
        mock_analyzer.analyze_directory.return_value = _make_analysis(
            total_files=20,
            naming_patterns=[pattern],
            file_type_distribution={".pdf": 10},
        )

        result = runner.invoke(app, ["suggest", "patterns", str(tmp_path), "--json"])
        assert result.exit_code == 0
        assert "20" in result.output
        assert "date_prefix" in result.output
