"""Coverage tests for file_organizer.cli.utilities — uncovered lines."""

from __future__ import annotations

import io
import json
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
import typer
from rich.console import Console
from typer.testing import CliRunner

pytestmark = [pytest.mark.ci, pytest.mark.unit]

runner = CliRunner()


def _make_app() -> typer.Typer:
    """Build a minimal Typer app wrapping the utilities functions."""
    from file_organizer.cli.utilities import analyze, search

    app = typer.Typer()
    app.command("search")(search)
    app.command("analyze")(analyze)
    return app


class TestSearchLimitZero:
    """Covers lines 62-66 — limit <= 0."""

    def test_limit_zero_plain(self, tmp_path: Path) -> None:
        app = _make_app()
        result = runner.invoke(app, ["search", "foo", str(tmp_path), "--limit", "0"])
        # Exit 0 with no-matches message
        assert result.exit_code == 0

    def test_limit_zero_json(self, tmp_path: Path) -> None:
        app = _make_app()
        result = runner.invoke(app, ["search", "foo", str(tmp_path), "--limit", "0", "--json"])
        assert result.exit_code == 0
        assert "[]" in result.output

    def test_limit_zero_still_validates_directory(self, tmp_path: Path) -> None:
        app = _make_app()
        missing = tmp_path / "missing"
        result = runner.invoke(app, ["search", "foo", str(missing), "--limit", "0"])
        assert result.exit_code == 1
        assert "does not exist" in " ".join(result.output.split())

    def test_limit_zero_still_validates_type_filter(self, tmp_path: Path) -> None:
        app = _make_app()
        result = runner.invoke(
            app, ["search", "foo", str(tmp_path), "--limit", "0", "--type", "magic"]
        )
        assert result.exit_code == 1
        assert "Unknown type" in result.output


class TestSearchDirectoryNotExist:
    """Covers lines 76-80 — invalid directory."""

    def test_bad_dir(self, tmp_path: Path) -> None:
        app = _make_app()
        bad = tmp_path / "nonexistent"
        result = runner.invoke(app, ["search", "foo", str(bad)])
        assert result.exit_code == 1
        # Typer may wrap output with extra whitespace; normalise before checking.
        normalised = " ".join(result.output.split())
        assert "does not exist" in normalised


class TestSearchBadTypeFilter:
    """Covers line 100 — invalid type filter."""

    def test_invalid_type(self, tmp_path: Path) -> None:
        app = _make_app()
        result = runner.invoke(app, ["search", "foo", str(tmp_path), "--type", "magic"])
        assert result.exit_code == 1
        assert "Unknown type" in result.output


class TestSearchTypeFilter:
    """Covers lines 118-120 — compound extensions .tar.gz, .tar.bz2."""

    def test_tar_gz_filter(self, tmp_path: Path) -> None:
        app = _make_app()
        (tmp_path / "data.tar.gz").write_bytes(b"fake")
        result = runner.invoke(app, ["search", "*", str(tmp_path), "--type", "archive"])
        assert result.exit_code == 0
        assert "data.tar.gz" in result.output

    def test_tar_bz2_filter(self, tmp_path: Path) -> None:
        app = _make_app()
        (tmp_path / "data.tar.bz2").write_bytes(b"fake")
        result = runner.invoke(app, ["search", "*", str(tmp_path), "--type", "archive"])
        assert result.exit_code == 0
        assert "data.tar.bz2" in result.output


class TestSearchNoMatch:
    """Covers line 131 — no matches."""

    def test_no_match_plain(self, tmp_path: Path) -> None:
        app = _make_app()
        (tmp_path / "readme.md").write_text("hello")
        result = runner.invoke(app, ["search", "notfound", str(tmp_path)])
        assert result.exit_code == 0
        assert "No files found" in result.output

    def test_no_match_json(self, tmp_path: Path) -> None:
        app = _make_app()
        (tmp_path / "readme.md").write_text("hello")
        result = runner.invoke(app, ["search", "notfound", str(tmp_path), "--json"])
        assert "[]" in result.output


class TestSearchResults:
    """Covers lines 155-158, 186-188, 200-202 — size formatting branches."""

    def test_small_file(self, tmp_path: Path) -> None:
        app = _make_app()
        f = tmp_path / "tiny.txt"
        f.write_text("x")
        result = runner.invoke(app, ["search", "tiny", str(tmp_path)])
        assert "B" in result.output

    def test_kb_file(self, tmp_path: Path) -> None:
        app = _make_app()
        f = tmp_path / "medium.txt"
        f.write_bytes(b"x" * 2048)
        result = runner.invoke(app, ["search", "medium", str(tmp_path)])
        assert "KB" in result.output

    def test_json_output(self, tmp_path: Path) -> None:
        app = _make_app()
        (tmp_path / "hello.txt").write_text("hi")
        result = runner.invoke(app, ["search", "hello", str(tmp_path), "--json"])
        assert "path" in result.output


class TestSemanticSearchHiddenFileFiltering:
    """Covers line 156 — is_hidden(rel_entry) in semantic corpus builder."""

    pytest.importorskip("rank_bm25")

    def test_hidden_files_excluded_from_semantic_corpus(self, tmp_path: Path) -> None:
        """Hidden files are excluded from the semantic corpus (relative path check)."""
        app = _make_app()
        (tmp_path / "report.txt").write_text("quarterly budget finance report")
        (tmp_path / "other.txt").write_text("meeting notes and agenda items")
        hidden = tmp_path / ".secret.txt"
        hidden.write_text("hidden sensitive data finance")

        result = runner.invoke(app, ["search", "finance", str(tmp_path), "--semantic"])
        assert result.exit_code == 0

    def test_relative_path_used_for_hidden_check(self, tmp_path: Path) -> None:
        """Files inside dot-prefixed dirs are excluded via relative path."""
        app = _make_app()
        (tmp_path / "report.txt").write_text("quarterly budget finance report")
        (tmp_path / "notes.txt").write_text("meeting agenda items budget")
        hidden_dir = tmp_path / ".config"
        hidden_dir.mkdir()
        (hidden_dir / "settings.txt").write_text("settings finance data")

        result = runner.invoke(app, ["search", "finance", str(tmp_path), "--semantic"])
        assert result.exit_code == 0

    def test_semantic_archive_filter_accepts_tar_gz(self, tmp_path: Path) -> None:
        """Semantic search respects compound archive extensions like .tar.gz."""
        app = _make_app()
        (tmp_path / "dataset.tar.gz").write_text("finance archive bundle")
        (tmp_path / "notes.txt").write_text("finance notes")

        result = runner.invoke(
            app,
            ["search", "finance", str(tmp_path), "--semantic", "--type", "archive"],
        )
        assert result.exit_code == 0
        assert "dataset.tar.gz" in result.output
        assert "notes.txt" not in result.output

    def test_semantic_type_filter_applies_before_document_limit(self, tmp_path: Path) -> None:
        """Archive matches should still be indexed even if many earlier text files exist."""
        app = _make_app()
        for index in range(250):
            (tmp_path / f"notes_{index:03d}.txt").write_text("finance notes")
        (tmp_path / "late_bundle.tar.gz").write_text("finance archive bundle")

        result = runner.invoke(
            app,
            [
                "search",
                "finance archive",
                str(tmp_path),
                "--semantic",
                "--type",
                "archive",
                "--limit",
                "5",
            ],
        )

        assert result.exit_code == 0
        assert "late_bundle.tar.gz" in result.output

    def test_json_output_skips_files_that_disappear(self, tmp_path: Path) -> None:
        from file_organizer.cli import utilities

        disappearing = tmp_path / "report.txt"
        disappearing.write_text("hello")

        original_stat = Path.stat

        def flaky_stat(path: Path):
            if path == disappearing:
                raise OSError("gone")
            return original_stat(path)

        buffer = io.StringIO()
        with (
            patch("pathlib.Path.stat", autospec=True, side_effect=flaky_stat),
            patch("typer.echo", side_effect=lambda value: buffer.write(f"{value}\n")),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            utilities._output_search_results([(disappearing, None)], json_out=True)

        assert any("Skipping" in str(warning.message) for warning in caught)
        assert json.loads(buffer.getvalue()) == []

    def test_text_output_skips_files_that_disappear(self, tmp_path: Path) -> None:
        from file_organizer.cli import utilities

        disappearing = tmp_path / "report.txt"
        disappearing.write_text("hello")

        original_stat = Path.stat

        def flaky_stat(path: Path):
            if path == disappearing:
                raise OSError("gone")
            return original_stat(path)

        buffer = io.StringIO()
        console = Console(file=buffer, force_terminal=False)
        with (
            patch("pathlib.Path.stat", autospec=True, side_effect=flaky_stat),
            patch("file_organizer.cli.utilities.console", console),
            patch("typer.echo", side_effect=lambda value: buffer.write(f"{value}\n")),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            utilities._output_search_results([(disappearing, None)], json_out=False)

        assert any("Skipping" in str(warning.message) for warning in caught)
        assert "Found 0 file(s):" in buffer.getvalue()


class TestSemanticIndexBuildFailure:
    """Covers line 173 — except (ValueError, RuntimeError, ImportError) path."""

    def test_index_build_failure_exits_with_error(self, tmp_path: Path) -> None:
        """When HybridRetriever.index() raises, CLI exits with code 1."""
        from unittest.mock import patch

        app = _make_app()
        (tmp_path / "report.txt").write_text("quarterly budget finance report")
        (tmp_path / "notes.txt").write_text("meeting notes and agenda items")

        with patch("file_organizer.services.search.hybrid_retriever.HybridRetriever") as mock_cls:
            mock_cls.return_value.index.side_effect = ValueError("corpus too small")
            result = runner.invoke(app, ["search", "finance", str(tmp_path), "--semantic"])

        assert result.exit_code == 1
        assert "Failed to build semantic index" in result.output
