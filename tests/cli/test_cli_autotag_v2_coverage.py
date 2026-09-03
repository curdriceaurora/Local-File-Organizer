"""Coverage tests for cli.autotag_v2 — uncovered error/edge branches."""

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


@pytest.mark.ci
@pytest.mark.integration
@pytest.mark.parametrize("command", ["suggest", "batch"])
def test_traversal_error_fails_command(command: str, tmp_path: Path) -> None:
    from file_organizer.cli.autotag_v2 import autotag_app

    def failed_walk(root: Path, **kwargs):
        kwargs["on_error"](root, PermissionError("denied"))
        return iter(())

    with (
        patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=MagicMock(),
        ),
        patch("file_organizer.cli.autotag_v2.safe_walk", side_effect=failed_walk),
    ):
        result = runner.invoke(autotag_app, [command, str(tmp_path)])

    assert result.exit_code == 1
    assert str(tmp_path) in result.output.replace("\n", "")
    assert "denied" in result.output


@pytest.mark.ci
@pytest.mark.integration
def test_batch_skips_unreadable_descendant_and_processes_other_files(tmp_path: Path) -> None:
    from file_organizer.cli.autotag_v2 import autotag_app

    good_file = tmp_path / "good.txt"
    good_file.write_text("good")
    restricted = tmp_path / "restricted"
    mock_service = MagicMock()
    mock_service.recommender.batch_recommend.return_value = {}

    def partial_walk(_root: Path, **kwargs):
        kwargs["on_error"](restricted, PermissionError("denied"))
        return iter([good_file])

    with (
        patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ),
        patch("file_organizer.cli.autotag_v2.safe_walk", side_effect=partial_walk),
    ):
        result = runner.invoke(autotag_app, ["batch", str(tmp_path), "--recursive"])

    assert result.exit_code == 0
    assert "Skipping unreadable path" in result.output
    assert str(restricted) in result.output.replace("\n", "")
    mock_service.recommender.batch_recommend.assert_called_once_with([good_file], top_n=5)


class TestAutotagSuggestErrors:
    """Covers error branches in suggest command (lines 47-49, 53-54, 61-62)."""

    def test_suggest_dir_not_found(self, tmp_path: Path) -> None:
        """A.cli: non-existent dir → ``typer.BadParameter`` (exit 2)."""
        from file_organizer.cli.autotag_v2 import autotag_app

        bad = tmp_path / "nonexistent"
        result = runner.invoke(autotag_app, ["suggest", str(bad)])
        assert result.exit_code == 2
        assert "does not exist" in result.output.lower()

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
        """A.cli: non-existent file → ``typer.BadParameter`` (exit 2)."""
        from file_organizer.cli.autotag_v2 import autotag_app

        missing = tmp_path / "gone.txt"
        result = runner.invoke(autotag_app, ["apply", str(missing), "tag1", "tag2"])
        assert result.exit_code == 2
        assert "does not exist" in result.output.lower()

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
        """A.cli: non-existent dir → ``typer.BadParameter`` (exit 2)."""
        from file_organizer.cli.autotag_v2 import autotag_app

        bad = tmp_path / "missing"
        result = runner.invoke(autotag_app, ["batch", str(bad)])
        assert result.exit_code == 2
        assert "does not exist" in result.output.lower()

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

    def test_batch_invalid_style(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        result = runner.invoke(autotag_app, ["batch", str(tmp_path), "--style", "invalid_style"])
        assert result.exit_code == 2
        assert "Invalid tag_style" in result.output

    def test_batch_invalid_prompt(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        result = runner.invoke(autotag_app, ["batch", str(tmp_path), "--prompt", "x" * 501])
        assert result.exit_code == 2
        assert "exceeds maximum length" in result.output

    def test_batch_valid_style_and_prompt(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        good_file = tmp_path / "file.py"
        good_file.write_text("print('hi')")

        mock_service = MagicMock()
        mock_service.recommender.batch_recommend.return_value = {
            good_file: _FakeRecommendation(
                suggestions=[_FakeTagSuggestion(tag="py", confidence=85.0)]
            )
        }

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(
                autotag_app,
                ["batch", str(tmp_path), "-s", "code", "-p", "python code", "--no-recursive"],
            )

        assert result.exit_code == 0
        mock_service.recommender.batch_recommend.assert_called_once_with(
            [good_file], top_n=5, style="code", prompt="python code"
        )

    def test_batch_json_output(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        good_file = tmp_path / "file.py"
        good_file.write_text("print('hi')")

        mock_service = MagicMock()
        mock_service.recommender.batch_recommend.return_value = {
            good_file: _FakeRecommendation(
                suggestions=[_FakeTagSuggestion(tag="py", confidence=85.0)]
            )
        }

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(
                autotag_app,
                ["batch", str(tmp_path), "--json"],
            )

        assert result.exit_code == 0
        assert '"tag": "py"' in result.output


class TestAutotagSuggestOptions:
    """Covers style and prompt options for suggest command."""

    def test_suggest_invalid_style(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        result = runner.invoke(autotag_app, ["suggest", str(tmp_path), "--style", "invalid_style"])
        assert result.exit_code == 2
        assert "Invalid tag_style" in result.output

    def test_suggest_invalid_prompt(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        result = runner.invoke(autotag_app, ["suggest", str(tmp_path), "--prompt", "x" * 501])
        assert result.exit_code == 2
        assert "exceeds maximum length" in result.output

    def test_suggest_valid_style_and_prompt(self, tmp_path: Path) -> None:
        from file_organizer.cli.autotag_v2 import autotag_app

        good_file = tmp_path / "audio.wav"
        good_file.write_text("dummy")

        mock_service = MagicMock()
        mock_service.suggest_tags.return_value = _FakeRecommendation(
            suggestions=[_FakeTagSuggestion(tag="whoosh", confidence=90.0)]
        )

        with patch(
            "file_organizer.services.auto_tagging.AutoTaggingService",
            return_value=mock_service,
        ):
            result = runner.invoke(
                autotag_app,
                ["suggest", str(tmp_path), "-s", "sfx", "-p", "whoosh impact"],
            )

        assert result.exit_code == 0
        mock_service.suggest_tags.assert_called_once_with(
            good_file, top_n=10, style="sfx", prompt="whoosh impact"
        )
