"""Tests for file_organizer.cli.autotag module.

Tests the argparse-based auto-tagging CLI commands including:
- setup_autotag_parser
- handle_autotag_command (router)
- Individual handlers: suggest, apply, popular, recent, analyze, batch
"""

from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.cli.autotag import (
    handle_analyze,
    handle_apply,
    handle_autotag_command,
    handle_batch,
    handle_popular,
    handle_recent,
    handle_suggest,
    setup_autotag_parser,
)

pytestmark = [pytest.mark.unit]


@pytest.fixture
def mock_service():
    """Create a mock AutoTaggingService."""
    svc = MagicMock()
    svc.content_analyzer = MagicMock()
    svc.recommender = MagicMock()
    return svc


@pytest.fixture
def mock_suggestion():
    """Create a mock tag suggestion."""
    s = MagicMock()
    s.tag = "python"
    s.confidence = 85.0
    s.source = "content"
    s.reasoning = "Contains Python code"
    s.to_dict.return_value = {
        "tag": "python",
        "confidence": 85.0,
        "source": "content",
        "reasoning": "Contains Python code",
    }
    return s


@pytest.fixture
def mock_recommendation(mock_suggestion):
    """Create a mock recommendation with suggestions."""
    rec = MagicMock()
    rec.suggestions = [mock_suggestion]
    return rec


# ============================================================================
# Parser Setup Tests
# ============================================================================


@pytest.mark.unit
class TestSetupAutotagParser:
    """Tests for setup_autotag_parser."""

    def test_parser_creation(self):
        """Verify the parser is set up with all subcommands."""
        import argparse

        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        setup_autotag_parser(subparsers)

        # Parse valid subcommand to verify it was created
        args = parser.parse_args(["autotag", "popular", "--limit", "5"])
        assert args.limit == 5


# ============================================================================
# Router Tests
# ============================================================================


@pytest.mark.unit
class TestHandleAutotagCommand:
    """Tests for handle_autotag_command router."""

    def test_route_suggest(self, mock_service):
        args = Namespace(
            autotag_command="suggest",
            files=[],
            existing_tags=None,
            top_n=10,
            min_confidence=40.0,
            json=False,
        )
        with patch("file_organizer.cli.autotag.AutoTaggingService", return_value=mock_service):
            with patch("file_organizer.cli.autotag.handle_suggest") as mock_handler:
                handle_autotag_command(args)
                mock_handler.assert_called_once()

    def test_route_apply(self, mock_service):
        args = Namespace(autotag_command="apply", file="test.txt", tags=["tag1"])
        with patch("file_organizer.cli.autotag.AutoTaggingService", return_value=mock_service):
            with patch("file_organizer.cli.autotag.handle_apply") as mock_handler:
                handle_autotag_command(args)
                mock_handler.assert_called_once()

    def test_route_popular(self, mock_service):
        args = Namespace(autotag_command="popular", limit=20)
        with patch("file_organizer.cli.autotag.AutoTaggingService", return_value=mock_service):
            with patch("file_organizer.cli.autotag.handle_popular") as mock_handler:
                handle_autotag_command(args)
                mock_handler.assert_called_once()

    def test_route_recent(self, mock_service):
        args = Namespace(autotag_command="recent", days=30, limit=20)
        with patch("file_organizer.cli.autotag.AutoTaggingService", return_value=mock_service):
            with patch("file_organizer.cli.autotag.handle_recent") as mock_handler:
                handle_autotag_command(args)
                mock_handler.assert_called_once()

    def test_route_analyze(self, mock_service):
        args = Namespace(autotag_command="analyze", file="test.txt", keywords=False, entities=False)
        with patch("file_organizer.cli.autotag.AutoTaggingService", return_value=mock_service):
            with patch("file_organizer.cli.autotag.handle_analyze") as mock_handler:
                handle_autotag_command(args)
                mock_handler.assert_called_once()

    def test_route_batch(self, mock_service):
        args = Namespace(
            autotag_command="batch", directory="/tmp", pattern="*", recursive=False, output=None
        )
        with patch("file_organizer.cli.autotag.AutoTaggingService", return_value=mock_service):
            with patch("file_organizer.cli.autotag.handle_batch") as mock_handler:
                handle_autotag_command(args)
                mock_handler.assert_called_once()

    def test_route_unknown(self, mock_service):
        args = Namespace(autotag_command=None)
        with (
            patch("file_organizer.cli.autotag.AutoTaggingService", return_value=mock_service),
            pytest.raises(SystemExit),
        ):
            handle_autotag_command(args)


# ============================================================================
# Suggest Handler Tests
# ============================================================================


@pytest.mark.unit
class TestHandleSuggest:
    """Tests for handle_suggest."""

    def test_suggest_text_output(self, mock_service, mock_recommendation, tmp_path, capsys):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        mock_service.suggest_tags.return_value = mock_recommendation

        args = Namespace(
            files=[str(test_file)],
            existing_tags=None,
            top_n=10,
            min_confidence=40.0,
            json=False,
        )
        handle_suggest(mock_service, args)
        captured = capsys.readouterr()
        assert "python" in captured.out
        assert "85.0%" in captured.out

    def test_suggest_json_output(self, mock_service, mock_recommendation, tmp_path, capsys):
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        mock_service.suggest_tags.return_value = mock_recommendation

        args = Namespace(
            files=[str(test_file)],
            existing_tags=None,
            top_n=10,
            min_confidence=40.0,
            json=True,
        )
        handle_suggest(mock_service, args)
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert data[0]["suggestions"][0]["tag"] == "python"

    def test_suggest_file_not_found(self, mock_service, capsys):
        args = Namespace(
            files=["/nonexistent/file.txt"],
            existing_tags=None,
            top_n=10,
            min_confidence=40.0,
            json=False,
        )
        handle_suggest(mock_service, args)
        captured = capsys.readouterr()
        assert "File not found" in captured.err

    def test_suggest_no_results_above_threshold(self, mock_service, tmp_path, capsys):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        low_conf = MagicMock()
        low_conf.confidence = 10.0
        rec = MagicMock()
        rec.suggestions = [low_conf]
        mock_service.suggest_tags.return_value = rec

        args = Namespace(
            files=[str(test_file)],
            existing_tags=None,
            top_n=10,
            min_confidence=40.0,
            json=False,
        )
        handle_suggest(mock_service, args)
        captured = capsys.readouterr()
        assert "No suggestions" in captured.out

    def test_suggest_multiple_files(self, mock_service, mock_recommendation, tmp_path, capsys):
        f1 = tmp_path / "a.txt"
        f1.write_text("aaa")
        f2 = tmp_path / "b.txt"
        f2.write_text("bbb")

        mock_service.suggest_tags.return_value = mock_recommendation

        args = Namespace(
            files=[str(f1), str(f2)],
            existing_tags=None,
            top_n=10,
            min_confidence=40.0,
            json=False,
        )
        handle_suggest(mock_service, args)
        captured = capsys.readouterr()
        assert "a.txt" in captured.out
        assert "b.txt" in captured.out


# ============================================================================
# Apply Handler Tests
# ============================================================================


@pytest.mark.unit
class TestHandleApply:
    """Tests for handle_apply."""

    def test_apply_success(self, mock_service, tmp_path, capsys):
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        args = Namespace(file=str(test_file), tags=["python", "code"])
        handle_apply(mock_service, args)

        mock_service.record_tag_usage.assert_called_once()
        captured = capsys.readouterr()
        assert "Applied tags" in captured.out
        assert "python" in captured.out

    def test_apply_file_not_found(self, mock_service):
        args = Namespace(file="/nonexistent/file.txt", tags=["tag"])
        with pytest.raises(SystemExit):
            handle_apply(mock_service, args)


# ============================================================================
# Popular Handler Tests
# ============================================================================


@pytest.mark.unit
class TestHandlePopular:
    """Tests for handle_popular."""

    def test_popular_with_data(self, mock_service, capsys):
        mock_service.get_popular_tags.return_value = [("python", 50), ("code", 30)]
        args = Namespace(limit=20)
        handle_popular(mock_service, args)
        captured = capsys.readouterr()
        assert "python" in captured.out
        assert "50" in captured.out

    def test_popular_empty(self, mock_service, capsys):
        mock_service.get_popular_tags.return_value = []
        args = Namespace(limit=20)
        handle_popular(mock_service, args)
        captured = capsys.readouterr()
        assert "No tag usage data" in captured.out


# ============================================================================
# Recent Handler Tests
# ============================================================================


@pytest.mark.unit
class TestHandleRecent:
    """Tests for handle_recent."""

    def test_recent_with_data(self, mock_service, capsys):
        mock_service.get_recent_tags.return_value = ["tag1", "tag2"]
        args = Namespace(days=30, limit=20)
        handle_recent(mock_service, args)
        captured = capsys.readouterr()
        assert "tag1" in captured.out
        assert "Last 30 days" in captured.out

    def test_recent_empty(self, mock_service, capsys):
        mock_service.get_recent_tags.return_value = []
        args = Namespace(days=7, limit=20)
        handle_recent(mock_service, args)
        captured = capsys.readouterr()
        assert "No tags used in the last 7 days" in captured.out


# ============================================================================
# Analyze Handler Tests
# ============================================================================


@pytest.mark.unit
class TestHandleAnalyze:
    """Tests for handle_analyze."""

    def test_analyze_basic(self, mock_service, tmp_path, capsys):
        """Test basic file analysis with tag extraction."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')")

        mock_service.content_analyzer.analyze_file.return_value = ["python", "script"]

        args = Namespace(file=str(test_file), keywords=False, entities=False)
        handle_analyze(mock_service, args)
        captured = capsys.readouterr()
        assert "Content Analysis" in captured.out
        assert "python" in captured.out
        assert "script" in captured.out
        assert "Extracted Tags (2)" in captured.out

    def test_analyze_with_keywords(self, mock_service, tmp_path, capsys):
        """Test analysis with keyword extraction enabled."""
        test_file = tmp_path / "test.py"
        test_file.write_text("import numpy")

        mock_service.content_analyzer.analyze_file.return_value = ["python"]
        mock_service.content_analyzer.extract_keywords.return_value = [
            ("numpy", 0.95),
            ("import", 0.80),
        ]

        args = Namespace(file=str(test_file), keywords=True, entities=False)
        handle_analyze(mock_service, args)
        captured = capsys.readouterr()
        assert "Top Keywords" in captured.out
        assert "numpy" in captured.out
        assert "0.950" in captured.out

    def test_analyze_with_entities(self, mock_service, tmp_path, capsys):
        """Test analysis with entity extraction enabled."""
        test_file = tmp_path / "doc.txt"
        test_file.write_text("Meeting with John at Google HQ")

        mock_service.content_analyzer.analyze_file.return_value = ["meeting"]
        mock_service.content_analyzer.extract_entities.return_value = [
            "John",
            "Google HQ",
        ]

        args = Namespace(file=str(test_file), keywords=False, entities=True)
        handle_analyze(mock_service, args)
        captured = capsys.readouterr()
        assert "Extracted Entities (2)" in captured.out
        assert "John" in captured.out
        assert "Google HQ" in captured.out

    def test_analyze_with_keywords_and_entities(self, mock_service, tmp_path, capsys):
        """Test analysis with both keywords and entities enabled."""
        test_file = tmp_path / "doc.txt"
        test_file.write_text("Python at Google")

        mock_service.content_analyzer.analyze_file.return_value = ["python"]
        mock_service.content_analyzer.extract_keywords.return_value = [("python", 0.9)]
        mock_service.content_analyzer.extract_entities.return_value = ["Google"]

        args = Namespace(file=str(test_file), keywords=True, entities=True)
        handle_analyze(mock_service, args)
        captured = capsys.readouterr()
        assert "Top Keywords" in captured.out
        assert "Extracted Entities" in captured.out

    def test_analyze_file_not_found(self, mock_service):
        """Test analysis with a file that does not exist."""
        args = Namespace(file="/nonexistent/file.txt", keywords=False, entities=False)
        with pytest.raises(SystemExit):
            handle_analyze(mock_service, args)


# ============================================================================
# Batch Handler Tests
# ============================================================================


@pytest.mark.unit
class TestHandleBatch:
    """Tests for handle_batch."""

    def test_batch_print_output(self, mock_service, tmp_path, capsys):
        (tmp_path / "file.txt").write_text("content")

        mock_rec = MagicMock()
        mock_rec.suggestions = []
        mock_service.recommender.batch_recommend.return_value = {
            tmp_path / "file.txt": mock_rec,
        }

        args = Namespace(
            directory=str(tmp_path),
            pattern="*",
            recursive=False,
            output=None,
        )
        handle_batch(mock_service, args)
        captured = capsys.readouterr()
        assert "Processing" in captured.out

    def test_batch_save_to_file(self, mock_service, tmp_path, capsys):
        (tmp_path / "file.txt").write_text("content")
        output_file = str(tmp_path / "results.json")

        mock_rec = MagicMock()
        mock_rec.suggestions = []
        mock_service.recommender.batch_recommend.return_value = {
            tmp_path / "file.txt": mock_rec,
        }

        args = Namespace(
            directory=str(tmp_path),
            pattern="*",
            recursive=False,
            output=output_file,
        )
        handle_batch(mock_service, args)
        captured = capsys.readouterr()
        assert "Results saved to" in captured.out
        assert Path(output_file).exists()

    def test_batch_not_a_directory(self, mock_service, tmp_path):
        not_dir = tmp_path / "file.txt"
        not_dir.write_text("content")

        args = Namespace(
            directory=str(not_dir),
            pattern="*",
            recursive=False,
            output=None,
        )
        with pytest.raises(SystemExit):
            handle_batch(mock_service, args)

    def test_batch_no_files_found(self, mock_service, tmp_path, capsys):
        # Empty directory with a pattern that doesn't match
        args = Namespace(
            directory=str(tmp_path),
            pattern="*.xyz",
            recursive=False,
            output=None,
        )
        handle_batch(mock_service, args)
        captured = capsys.readouterr()
        assert "No files found" in captured.out

    def test_batch_recursive(self, mock_service, tmp_path, capsys):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("content")

        mock_rec = MagicMock()
        mock_rec.suggestions = []
        mock_service.recommender.batch_recommend.return_value = {
            sub / "nested.txt": mock_rec,
        }

        args = Namespace(
            directory=str(tmp_path),
            pattern="*.txt",
            recursive=True,
            output=None,
        )
        handle_batch(mock_service, args)
        captured = capsys.readouterr()
        assert "Processing 1 files" in captured.out
