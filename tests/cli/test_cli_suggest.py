"""Tests for file_organizer.cli.suggest module.

Tests the smart file-organisation suggestions CLI commands:
- files: Generate suggestions for files in a directory
- patterns: Analyze directory patterns
- apply: Apply suggestions
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.suggest import suggest_app

runner = CliRunner()

pytestmark = [pytest.mark.unit]


class TestSuggestFiles:
    """Tests for suggest files command."""

    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_suggest_files_basic(self, mock_analyzer_fn, mock_engine_fn, tmp_path):
        """Test generating suggestions for files in a directory."""
        # Create test files
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file1.txt").touch()
        (test_dir / "file2.pdf").touch()

        # Mock the engine and analyzer
        mock_engine = MagicMock()
        mock_analyzer = MagicMock()

        suggestion = MagicMock()
        suggestion.confidence = 95.0
        suggestion.destination = "Documents"
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer.analyze_directory.return_value = {}

        mock_engine_fn.return_value = mock_engine
        mock_analyzer_fn.return_value = mock_analyzer

        result = runner.invoke(suggest_app, ["files", str(test_dir)])

        assert result.exit_code == 0
        mock_engine.generate_suggestions.assert_called_once()

    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_suggest_files_with_confidence_threshold(
        self, mock_analyzer_fn, mock_engine_fn, tmp_path
    ):
        """Test suggestions with custom confidence threshold."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file.txt").touch()

        mock_engine = MagicMock()
        mock_analyzer = MagicMock()

        # High confidence suggestion
        high_conf = MagicMock()
        high_conf.confidence = 95.0

        # Low confidence suggestion
        low_conf = MagicMock()
        low_conf.confidence = 30.0

        mock_engine.generate_suggestions.return_value = [high_conf, low_conf]
        mock_analyzer.analyze_directory.return_value = {}

        mock_engine_fn.return_value = mock_engine
        mock_analyzer_fn.return_value = mock_analyzer

        result = runner.invoke(
            suggest_app, ["files", str(test_dir), "--min-confidence", "50"]
        )

        assert result.exit_code == 0

    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_suggest_files_max_results(
        self, mock_analyzer_fn, mock_engine_fn, tmp_path
    ):
        """Test limiting results with max-results option."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file.txt").touch()

        mock_engine = MagicMock()
        mock_analyzer = MagicMock()
        mock_engine.generate_suggestions.return_value = []
        mock_analyzer.analyze_directory.return_value = {}

        mock_engine_fn.return_value = mock_engine
        mock_analyzer_fn.return_value = mock_analyzer

        result = runner.invoke(
            suggest_app, ["files", str(test_dir), "--max-results", "10"]
        )

        assert result.exit_code == 0
        # Verify max_suggestions was passed
        call_kwargs = mock_engine.generate_suggestions.call_args[1]
        assert call_kwargs.get("max_suggestions") == 10

    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_suggest_files_json_output(
        self, mock_analyzer_fn, mock_engine_fn, tmp_path
    ):
        """Test JSON output format."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file.txt").touch()

        mock_engine = MagicMock()
        mock_analyzer = MagicMock()

        suggestion = MagicMock()
        suggestion.confidence = 95.0
        suggestion.destination = "Documents"
        suggestion.to_dict.return_value = {"destination": "Documents", "confidence": 95.0}

        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer.analyze_directory.return_value = {}

        mock_engine_fn.return_value = mock_engine
        mock_analyzer_fn.return_value = mock_analyzer

        result = runner.invoke(suggest_app, ["files", str(test_dir), "--json"])

        assert result.exit_code == 0

    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_suggest_files_dry_run(self, mock_analyzer_fn, mock_engine_fn, tmp_path):
        """Test dry-run/preview mode."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file.txt").touch()

        mock_engine = MagicMock()
        mock_analyzer = MagicMock()
        mock_engine.generate_suggestions.return_value = []
        mock_analyzer.analyze_directory.return_value = {}

        mock_engine_fn.return_value = mock_engine
        mock_analyzer_fn.return_value = mock_analyzer

        result = runner.invoke(suggest_app, ["files", str(test_dir), "--dry-run"])

        assert result.exit_code == 0

    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_suggest_files_empty_directory(
        self, mock_analyzer_fn, mock_engine_fn, tmp_path
    ):
        """Test handling empty directory."""
        test_dir = tmp_path / "empty"
        test_dir.mkdir()

        mock_engine_fn.return_value = MagicMock()
        mock_analyzer_fn.return_value = MagicMock()

        result = runner.invoke(suggest_app, ["files", str(test_dir)])

        assert result.exit_code == 0
        assert "No files found" in result.stdout

    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_suggest_files_no_suggestions_above_threshold(
        self, mock_analyzer_fn, mock_engine_fn, tmp_path
    ):
        """Test handling when no suggestions exceed confidence threshold."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file.txt").touch()

        mock_engine = MagicMock()
        mock_analyzer = MagicMock()

        # Only low confidence suggestions
        low_conf = MagicMock()
        low_conf.confidence = 20.0
        mock_engine.generate_suggestions.return_value = [low_conf]
        mock_analyzer.analyze_directory.return_value = {}

        mock_engine_fn.return_value = mock_engine
        mock_analyzer_fn.return_value = mock_analyzer

        result = runner.invoke(
            suggest_app, ["files", str(test_dir), "--min-confidence", "80"]
        )

        assert result.exit_code == 0
        assert "No suggestions above confidence threshold" in result.stdout

    def test_suggest_missing_directory(self):
        """Test suggest with missing directory argument."""
        result = runner.invoke(suggest_app, ["files"])

        assert result.exit_code != 0


class TestCollectFiles:
    """Tests for _collect_files helper."""

    @patch("file_organizer.cli.suggest._get_engine")
    @patch("file_organizer.cli.suggest._get_analyzer")
    def test_collect_files_recursive(
        self, mock_analyzer_fn, mock_engine_fn, tmp_path
    ):
        """Test that files are collected recursively."""
        test_dir = tmp_path / "test"
        test_dir.mkdir()
        (test_dir / "file1.txt").touch()
        subdir = test_dir / "subdir"
        subdir.mkdir()
        (subdir / "file2.txt").touch()

        mock_engine = MagicMock()
        mock_analyzer = MagicMock()

        suggestion = MagicMock()
        suggestion.confidence = 95.0
        mock_engine.generate_suggestions.return_value = [suggestion]
        mock_analyzer.analyze_directory.return_value = {}

        mock_engine_fn.return_value = mock_engine
        mock_analyzer_fn.return_value = mock_analyzer

        result = runner.invoke(suggest_app, ["files", str(test_dir)])

        assert result.exit_code == 0
        # Should collect both files
        call_args = mock_engine.generate_suggestions.call_args
        file_list = call_args[0][0]
        assert len(file_list) >= 2
