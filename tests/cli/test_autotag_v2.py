"""Tests for modern Typer-based auto-tagging CLI sub-app."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


def _make_suggestion(tag: str, confidence: float, source: str, reasoning: str) -> MagicMock:
    """Create a mock TagSuggestion."""
    s = MagicMock()
    s.tag = tag
    s.confidence = confidence
    s.source = source
    s.reasoning = reasoning
    return s


def _make_recommendation(file_path: Path, suggestions: list) -> MagicMock:
    """Create a mock TagRecommendation."""
    rec = MagicMock()
    rec.file_path = file_path
    rec.suggestions = suggestions
    return rec


# -----------------------------------------------------------------------
# Tests
# -----------------------------------------------------------------------


def test_autotag_help():
    """The autotag group shows help listing subcommands."""
    result = runner.invoke(app, ["autotag", "--help"])
    assert result.exit_code == 0
    assert "suggest" in result.stdout
    assert "apply" in result.stdout
    assert "popular" in result.stdout
    assert "recent" in result.stdout
    assert "batch" in result.stdout


def test_autotag_suggest_help():
    """The suggest subcommand shows its own help."""
    result = runner.invoke(app, ["autotag", "suggest", "--help"])
    assert result.exit_code == 0
    assert "directory" in result.stdout.lower() or "DIRECTORY" in result.stdout


@patch("file_organizer.services.auto_tagging.AutoTaggingService")
def test_autotag_suggest_files(mock_service_cls, tmp_path):
    """suggest scans a directory and displays tag suggestions."""
    # Create files in tmp dir
    (tmp_path / "readme.md").write_text("# Hello")
    (tmp_path / "notes.txt").write_text("Some notes")

    mock_service = MagicMock()
    mock_service_cls.return_value = mock_service

    suggestions = [
        _make_suggestion("python", 85.0, "content", "Detected Python keywords"),
        _make_suggestion("docs", 60.0, "content", "Documentation file"),
    ]
    mock_service.suggest_tags.return_value = _make_recommendation(
        tmp_path / "readme.md", suggestions
    )

    result = runner.invoke(app, ["autotag", "suggest", str(tmp_path)])
    assert result.exit_code == 0
    assert "python" in result.stdout
    assert "docs" in result.stdout


@patch("file_organizer.services.auto_tagging.AutoTaggingService")
def test_autotag_apply_tags(mock_service_cls, tmp_path):
    """apply records tags for a file."""
    test_file = tmp_path / "report.pdf"
    test_file.write_bytes(b"%PDF-1.4 fake")

    mock_service = MagicMock()
    mock_service_cls.return_value = mock_service

    result = runner.invoke(app, ["autotag", "apply", str(test_file), "tag1", "tag2"])
    assert result.exit_code == 0
    assert "tag1" in result.stdout
    assert "tag2" in result.stdout
    mock_service.record_tag_usage.assert_called_once()
    call_args = mock_service.record_tag_usage.call_args
    assert call_args[0][1] == ["tag1", "tag2"]


@patch("file_organizer.services.auto_tagging.AutoTaggingService")
def test_autotag_popular_tags(mock_service_cls):
    """popular shows most-used tags."""
    mock_service = MagicMock()
    mock_service_cls.return_value = mock_service
    mock_service.get_popular_tags.return_value = [("python", 10), ("docs", 5)]

    result = runner.invoke(app, ["autotag", "popular"])
    assert result.exit_code == 0
    assert "python" in result.stdout
    assert "docs" in result.stdout


@patch("file_organizer.services.auto_tagging.AutoTaggingService")
def test_autotag_popular_with_limit(mock_service_cls):
    """popular respects --limit flag."""
    mock_service = MagicMock()
    mock_service_cls.return_value = mock_service
    mock_service.get_popular_tags.return_value = [("python", 10)]

    result = runner.invoke(app, ["autotag", "popular", "--limit", "5"])
    assert result.exit_code == 0
    mock_service.get_popular_tags.assert_called_once_with(limit=5)


@patch("file_organizer.services.auto_tagging.AutoTaggingService")
def test_autotag_recent_tags(mock_service_cls):
    """recent shows recently used tags."""
    mock_service = MagicMock()
    mock_service_cls.return_value = mock_service
    mock_service.get_recent_tags.return_value = ["python", "docs"]

    result = runner.invoke(app, ["autotag", "recent"])
    assert result.exit_code == 0
    assert "python" in result.stdout
    assert "docs" in result.stdout


@patch("file_organizer.services.auto_tagging.AutoTaggingService")
def test_autotag_batch_mode(mock_service_cls, tmp_path):
    """batch processes all files in a directory."""
    (tmp_path / "file1.txt").write_text("hello")
    (tmp_path / "file2.txt").write_text("world")

    mock_service = MagicMock()
    mock_service_cls.return_value = mock_service

    suggestions = [_make_suggestion("text", 90.0, "content", "Plain text file")]
    batch_results = {}
    for f in tmp_path.iterdir():
        if f.is_file():
            batch_results[f] = _make_recommendation(f, suggestions)
    mock_service.recommender.batch_recommend.return_value = batch_results

    result = runner.invoke(app, ["autotag", "batch", str(tmp_path)])
    assert result.exit_code == 0
    assert "text" in result.stdout


def test_autotag_nonexistent_dir():
    """suggest fails with exit 1 for a non-existent directory."""
    result = runner.invoke(app, ["autotag", "suggest", "/nonexistent"])
    assert result.exit_code == 1


@patch("file_organizer.services.auto_tagging.AutoTaggingService")
def test_autotag_json_output(mock_service_cls, tmp_path):
    """suggest --json outputs valid JSON."""
    (tmp_path / "data.csv").write_text("a,b,c\n1,2,3")

    mock_service = MagicMock()
    mock_service_cls.return_value = mock_service

    suggestions = [
        _make_suggestion("csv", 95.0, "content", "CSV data file"),
    ]
    mock_service.suggest_tags.return_value = _make_recommendation(
        tmp_path / "data.csv", suggestions
    )

    result = runner.invoke(app, ["autotag", "suggest", str(tmp_path), "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert isinstance(parsed, list)
    assert len(parsed) >= 1
    assert "suggestions" in parsed[0]
    assert parsed[0]["suggestions"][0]["tag"] == "csv"
