"""Coverage tests for file_organizer.cli.autotag_v2 — uncovered error/edge branches."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

pytestmark = pytest.mark.unit

runner = CliRunner()


@dataclass
class _FakeTagSuggestion:
    tag: str = "report"
    confidence: float = 75.0
    source: str = "pattern"
    reasoning: str = "Matches report pattern"


@dataclass
class _FakeRecommendation:
    suggestions: list = field(default_factory=list)


class TestAutotagSuggestErrors:
    """Covers error branches in suggest command (lines 47-49, 53-54, 61-62)."""

    def test_suggest_dir_not_found(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        bad = tmp_path / "nonexistent"
        result = runner.invoke(autotag_app, ["suggest", str(bad)])
        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_suggest_service_init_error(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            side_effect=RuntimeError("no model"),
        ):
            result = runner.invoke(autotag_app, ["suggest", str(tmp_path)])

        assert result.exit_code == 1
        assert "initializing" in result.output.lower()

    def test_suggest_empty_dir(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        mock_service = MagicMock()

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(autotag_app, ["suggest", str(tmp_path)])

        assert result.exit_code == 0
        assert "No files found" in result.output

    def test_suggest_file_error_continues(self, tmp_path: Path) -> None:
        """When suggest_tags raises for one file, it continues."""
        from file_organizer.cli.autotag_v2 import autotag_app

        (tmp_path / "a.txt").write_text("hello")

        mock_service = MagicMock()
        mock_service.suggest_tags.side_effect = RuntimeError("model error")

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(autotag_app, ["suggest", str(tmp_path)])

        # Should not crash
        assert result.exit_code == 0


class TestAutotagApplyErrors:
    """Covers error branches in apply command (lines 113-114, 119-121)."""

    def test_apply_file_not_found(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        missing = tmp_path / "gone.txt"
        result = runner.invoke(autotag_app, ["apply", str(missing), "tag1", "tag2"])
        assert result.exit_code == 1

    def test_apply_service_error(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        f = tmp_path / "real.txt"
        f.write_text("hi")

        mock_service = MagicMock()
        mock_service.record_tag_usage.side_effect = RuntimeError("db error")

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(autotag_app, ["apply", str(f), "tag1"])

        assert result.exit_code == 1


class TestAutotagPopularErrors:
    """Covers error branches in popular command (lines 138-140, 143-144)."""

    def test_popular_error(self) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        mock_service = MagicMock()
        mock_service.get_popular_tags.side_effect = RuntimeError("db error")

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(autotag_app, ["popular"])

        assert result.exit_code == 1

    def test_popular_empty(self) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        mock_service = MagicMock()
        mock_service.get_popular_tags.return_value = []

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(autotag_app, ["popular"])

        assert result.exit_code == 0
        assert "No tag usage" in result.output


class TestAutotagRecentErrors:
    """Covers error branches in recent command (lines 168-170, 173-174)."""

    def test_recent_error(self) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        mock_service = MagicMock()
        mock_service.get_recent_tags.side_effect = RuntimeError("db error")

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(autotag_app, ["recent"])

        assert result.exit_code == 1

    def test_recent_empty(self) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        mock_service = MagicMock()
        mock_service.get_recent_tags.return_value = []

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(autotag_app, ["recent"])

        assert result.exit_code == 0
        assert "No tags used" in result.output


class TestAutotagBatchErrors:
    """Covers error branches in batch command (lines 198-199, 203-205, 211-212, 218-220)."""

    def test_batch_dir_not_found(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        bad = tmp_path / "missing"
        result = runner.invoke(autotag_app, ["batch", str(bad)])
        assert result.exit_code == 1

    def test_batch_service_init_error(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            side_effect=RuntimeError("no model"),
        ):
            result = runner.invoke(autotag_app, ["batch", str(tmp_path)])

        assert result.exit_code == 1

    def test_batch_empty(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        mock_service = MagicMock()

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(autotag_app, ["batch", str(tmp_path)])

        assert result.exit_code == 0
        assert "No files found" in result.output

    def test_batch_processing_error(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        (tmp_path / "a.txt").write_text("hello")

        mock_service = MagicMock()
        mock_service.recommender.batch_recommend.side_effect = RuntimeError("err")

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(autotag_app, ["batch", str(tmp_path)])

        assert result.exit_code == 1
