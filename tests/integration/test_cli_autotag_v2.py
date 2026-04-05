"""Integration tests for the autotag_v2 Typer CLI sub-app.

Covers: suggest, apply, popular, recent, batch commands and their error paths.

All AutoTaggingService calls are mocked — zero real file I/O outside tmp_path.

Note: autotag_v2.py uses local imports (inside each command function), so the
correct patch target is the module where the class lives:
  file_organizer.services.auto_tagging.AutoTaggingService
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.autotag_v2 import autotag_app

pytestmark = [pytest.mark.integration, pytest.mark.ci]

runner = CliRunner()

# Patch target — the class lives in the service module, imported locally per command.
_PATCH_TARGET = "file_organizer.services.auto_tagging.AutoTaggingService"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_suggestion(
    tag: str = "document",
    confidence: float = 80.0,
    source: str = "content",
    reasoning: str = "matches keyword",
) -> MagicMock:
    s = MagicMock()
    s.tag = tag
    s.confidence = confidence
    s.source = source
    s.reasoning = reasoning
    return s


def _make_recommendation(suggestions: list | None = None) -> MagicMock:
    rec = MagicMock()
    rec.suggestions = suggestions or []
    return rec


# ---------------------------------------------------------------------------
# suggest command
# ---------------------------------------------------------------------------


class TestSuggestCommand:
    def test_suggest_directory_not_found_exits_1(self, tmp_path) -> None:
        missing = tmp_path / "does_not_exist"
        result = runner.invoke(autotag_app, ["suggest", str(missing)])
        assert result.exit_code == 1

    def test_suggest_empty_directory_exits_0(self, tmp_path) -> None:
        result = runner.invoke(autotag_app, ["suggest", str(tmp_path)])
        assert result.exit_code == 0

    def test_suggest_service_init_failure_exits_1(self, tmp_path) -> None:
        (tmp_path / "file.txt").write_text("hello")
        with patch(
            _PATCH_TARGET,
            side_effect=RuntimeError("no config"),
        ):
            result = runner.invoke(autotag_app, ["suggest", str(tmp_path)])
        assert result.exit_code == 1

    def test_suggest_returns_table_output(self, tmp_path) -> None:
        (tmp_path / "report.txt").write_text("quarterly report")
        suggestion = _make_suggestion("report", 90.0)
        rec = _make_recommendation([suggestion])

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.suggest_tags.return_value = rec
            result = runner.invoke(autotag_app, ["suggest", str(tmp_path)])

        assert result.exit_code == 0

    def test_suggest_filters_below_min_confidence(self, tmp_path) -> None:
        (tmp_path / "file.txt").write_text("data")
        low = _make_suggestion("low-tag", confidence=10.0)
        high = _make_suggestion("high-tag", confidence=80.0)
        rec = _make_recommendation([low, high])

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.suggest_tags.return_value = rec
            result = runner.invoke(
                autotag_app,
                ["suggest", str(tmp_path), "--min-confidence", "50.0"],
            )

        assert result.exit_code == 0
        # The service was called
        mock_cls.return_value.suggest_tags.assert_called_once()

    def test_suggest_json_output(self, tmp_path) -> None:
        import json

        (tmp_path / "file.txt").write_text("data")
        suggestion = _make_suggestion("json-tag", 75.0)
        rec = _make_recommendation([suggestion])

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.suggest_tags.return_value = rec
            result = runner.invoke(autotag_app, ["suggest", str(tmp_path), "--json"])

        assert result.exit_code == 0
        # Output should contain valid JSON
        parsed = json.loads(result.output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["suggestions"][0]["tag"] == "json-tag"
        assert parsed[0]["suggestions"][0]["confidence"] == 75.0

    def test_suggest_skips_file_on_exception(self, tmp_path) -> None:
        (tmp_path / "good.txt").write_text("data")
        (tmp_path / "bad.txt").write_text("data")
        good_rec = _make_recommendation([_make_suggestion("ok")])

        call_count = 0

        def side_effect(file_path, top_n):
            nonlocal call_count
            call_count += 1
            if file_path.name == "bad.txt":
                raise ValueError("inference error")
            return good_rec

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.suggest_tags.side_effect = side_effect
            result = runner.invoke(autotag_app, ["suggest", str(tmp_path)])

        assert result.exit_code == 0
        assert call_count == 2

    def test_suggest_top_n_passed_to_service(self, tmp_path) -> None:
        (tmp_path / "file.txt").write_text("data")
        rec = _make_recommendation([_make_suggestion("t")])

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.suggest_tags.return_value = rec
            runner.invoke(autotag_app, ["suggest", str(tmp_path), "--top-n", "5"])

        mock_cls.return_value.suggest_tags.assert_called_once()
        call_kwargs = mock_cls.return_value.suggest_tags.call_args
        assert call_kwargs[1]["top_n"] == 5


# ---------------------------------------------------------------------------
# apply command
# ---------------------------------------------------------------------------


class TestApplyCommand:
    def test_apply_file_not_found_exits_1(self, tmp_path) -> None:
        missing = tmp_path / "missing.txt"
        result = runner.invoke(autotag_app, ["apply", str(missing), "tag1"])
        assert result.exit_code == 1

    def test_apply_success(self, tmp_path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("content")

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.record_tag_usage.return_value = None
            result = runner.invoke(autotag_app, ["apply", str(f), "invoice", "finance"])

        assert result.exit_code == 0
        mock_cls.return_value.record_tag_usage.assert_called_once()
        call_args = mock_cls.return_value.record_tag_usage.call_args
        applied_tags = call_args[0][1]
        assert "invoice" in applied_tags
        assert "finance" in applied_tags

    def test_apply_service_error_exits_1(self, tmp_path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("content")

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.record_tag_usage.side_effect = RuntimeError("db error")
            result = runner.invoke(autotag_app, ["apply", str(f), "tag1"])

        assert result.exit_code == 1

    def test_apply_service_init_failure_exits_1(self, tmp_path) -> None:
        f = tmp_path / "doc.txt"
        f.write_text("content")

        with patch(
            _PATCH_TARGET,
            side_effect=RuntimeError("init failed"),
        ):
            result = runner.invoke(autotag_app, ["apply", str(f), "tag1"])

        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# popular command
# ---------------------------------------------------------------------------


class TestPopularCommand:
    def test_popular_no_data_exits_0(self) -> None:
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.get_popular_tags.return_value = []
            result = runner.invoke(autotag_app, ["popular"])
        assert result.exit_code == 0

    def test_popular_returns_table(self) -> None:
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.get_popular_tags.return_value = [
                ("invoice", 42),
                ("report", 17),
            ]
            result = runner.invoke(autotag_app, ["popular"])
        assert result.exit_code == 0

    def test_popular_limit_passed_to_service(self) -> None:
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.get_popular_tags.return_value = [("tag", 5)]
            runner.invoke(autotag_app, ["popular", "--limit", "5"])
        mock_cls.return_value.get_popular_tags.assert_called_once_with(limit=5)

    def test_popular_service_error_exits_1(self) -> None:
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.get_popular_tags.side_effect = RuntimeError("err")
            result = runner.invoke(autotag_app, ["popular"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# recent command
# ---------------------------------------------------------------------------


class TestRecentCommand:
    def test_recent_no_data_exits_0(self) -> None:
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.get_recent_tags.return_value = []
            result = runner.invoke(autotag_app, ["recent"])
        assert result.exit_code == 0

    def test_recent_returns_table(self) -> None:
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.get_recent_tags.return_value = ["invoice", "report"]
            result = runner.invoke(autotag_app, ["recent"])
        assert result.exit_code == 0

    def test_recent_days_and_limit_passed_to_service(self) -> None:
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.get_recent_tags.return_value = ["tag1"]
            runner.invoke(autotag_app, ["recent", "--days", "7", "--limit", "10"])
        mock_cls.return_value.get_recent_tags.assert_called_once_with(days=7, limit=10)

    def test_recent_service_error_exits_1(self) -> None:
        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.get_recent_tags.side_effect = RuntimeError("err")
            result = runner.invoke(autotag_app, ["recent"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# batch command
# ---------------------------------------------------------------------------


class TestBatchCommand:
    def test_batch_directory_not_found_exits_1(self, tmp_path) -> None:
        missing = tmp_path / "no_dir"
        result = runner.invoke(autotag_app, ["batch", str(missing)])
        assert result.exit_code == 1

    def test_batch_no_matching_files_exits_0(self, tmp_path) -> None:
        result = runner.invoke(autotag_app, ["batch", str(tmp_path), "--pattern", "*.xyz"])
        assert result.exit_code == 0

    def test_batch_service_init_failure_exits_1(self, tmp_path) -> None:
        (tmp_path / "file.txt").write_text("data")
        with patch(
            _PATCH_TARGET,
            side_effect=RuntimeError("no config"),
        ):
            result = runner.invoke(autotag_app, ["batch", str(tmp_path)])
        assert result.exit_code == 1

    def test_batch_success_table_output(self, tmp_path) -> None:
        (tmp_path / "doc.txt").write_text("data")
        suggestion = _make_suggestion("batch-tag", 70.0)
        rec = _make_recommendation([suggestion])

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.recommender.batch_recommend.return_value = {
                tmp_path / "doc.txt": rec
            }
            result = runner.invoke(autotag_app, ["batch", str(tmp_path)])

        assert result.exit_code == 0
        mock_cls.return_value.recommender.batch_recommend.assert_called_once()

    def test_batch_success_json_output(self, tmp_path) -> None:
        import json

        (tmp_path / "doc.txt").write_text("data")
        suggestion = _make_suggestion("json-batch-tag", 65.0)
        rec = _make_recommendation([suggestion])

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.recommender.batch_recommend.return_value = {
                tmp_path / "doc.txt": rec
            }
            result = runner.invoke(autotag_app, ["batch", str(tmp_path), "--json"])

        assert result.exit_code == 0
        # The batch command prints "Processing N files..." before the JSON array.
        output = result.output
        json_start = output.index("[")
        parsed = json.loads(output[json_start:])
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["suggestions"][0]["tag"] == "json-batch-tag"
        assert parsed[0]["suggestions"][0]["confidence"] == 65.0

    def test_batch_recommender_error_exits_1(self, tmp_path) -> None:
        (tmp_path / "doc.txt").write_text("data")

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.recommender.batch_recommend.side_effect = RuntimeError("OOM")
            result = runner.invoke(autotag_app, ["batch", str(tmp_path)])

        assert result.exit_code == 1

    def test_batch_non_recursive(self, tmp_path) -> None:
        (tmp_path / "top.txt").write_text("data")
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("data")

        suggestion = _make_suggestion("nr-tag", 60.0)
        rec = _make_recommendation([suggestion])

        with patch(_PATCH_TARGET) as mock_cls:
            mock_cls.return_value.recommender.batch_recommend.return_value = {
                tmp_path / "top.txt": rec
            }
            result = runner.invoke(autotag_app, ["batch", str(tmp_path), "--no-recursive"])

        assert result.exit_code == 0
        call_args = mock_cls.return_value.recommender.batch_recommend.call_args
        files_arg: list[Path] = call_args[0][0]
        # Non-recursive: only top-level file should be passed
        names = [f.name for f in files_arg]
        assert "top.txt" in names
        assert "nested.txt" not in names
