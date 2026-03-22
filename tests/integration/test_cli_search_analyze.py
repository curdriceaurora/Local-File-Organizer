"""Integration tests for CLI search and analyze commands.

Covers: search (glob, keyword, type-filter, json output, limit=0, nonexistent dir,
invalid type, no matches, non-recursive, compound extension), analyze (missing
file, binary file, OSError reading, json output, runtime error from model).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.integration]

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_test_dir(tmp_path: Path) -> Path:
    """Create a temp dir with files of various types for search tests."""
    d = tmp_path / "files"
    d.mkdir()
    (d / "report.txt").write_text("quarterly report content")
    (d / "photo.jpg").write_bytes(b"\xff\xd8\xff" + b"\x00" * 10)  # JPEG header
    (d / "archive.tar.gz").write_bytes(b"\x1f\x8b\x08" + b"\x00" * 10)  # gzip header
    (d / "notes.md").write_text("# Notes\n\nsome markdown")
    (d / "data.csv").write_text("col1,col2\n1,2")
    sub = d / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested file")
    return d


# ---------------------------------------------------------------------------
# Search command tests
# ---------------------------------------------------------------------------


class TestSearchCommand:
    def test_search_keyword_finds_matching_file(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "report", str(d)])
        assert result.exit_code == 0
        assert "report.txt" in result.output

    def test_search_glob_pattern(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "*.txt", str(d)])
        assert result.exit_code == 0
        assert "report.txt" in result.output

    def test_search_no_matches_exits_zero(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "xyznonexistent", str(d)])
        assert result.exit_code == 0
        assert "no files" in result.output.lower()

    def test_search_nonexistent_directory_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["search", "anything", str(tmp_path / "gone")])
        assert result.exit_code == 1
        assert "error" in result.output.lower() or "does not exist" in result.output.lower()

    def test_search_invalid_type_filter_exits_1(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "report", str(d), "--type", "database"])
        assert result.exit_code == 1
        assert "unknown type" in result.output.lower() or "database" in result.output.lower()

    def test_search_type_filter_text(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "*", str(d), "--type", "text"])
        assert result.exit_code == 0
        # txt and md files should appear; jpg should not
        assert "report.txt" in result.output or "notes.md" in result.output
        assert "photo.jpg" not in result.output

    def test_search_type_filter_image(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "*", str(d), "--type", "image"])
        assert result.exit_code == 0
        assert "photo.jpg" in result.output
        assert "report.txt" not in result.output

    def test_search_json_output_is_valid_json(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "report", str(d), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert isinstance(data, list)
        assert len(data) >= 1
        assert "path" in data[0]
        assert "size" in data[0]
        assert "modified" in data[0]

    def test_search_json_empty_result_is_empty_array(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "xyznonexistent", str(d), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data == []

    def test_search_limit_zero_exits_zero(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "report", str(d), "--limit", "0"])
        assert result.exit_code == 0

    def test_search_limit_zero_json_returns_empty_array(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "report", str(d), "--limit", "0", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data == []

    def test_search_non_recursive_does_not_find_nested(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "nested", str(d), "--no-recursive"])
        assert result.exit_code == 0
        assert "nested.txt" not in result.output

    def test_search_recursive_finds_nested(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "nested", str(d)])
        assert result.exit_code == 0
        assert "nested.txt" in result.output

    def test_search_limit_respected(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "*", str(d), "--limit", "2", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert len(data) == 2

    def test_search_type_archive_finds_tar_gz(self, tmp_path: Path) -> None:
        d = _make_test_dir(tmp_path)
        result = runner.invoke(app, ["search", "*", str(d), "--type", "archive"])
        assert result.exit_code == 0
        assert "archive.tar.gz" in result.output


class TestAnalyzeCommand:
    def test_analyze_missing_file_exits_1(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["analyze", str(tmp_path / "nonexistent.txt")])
        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "error" in result.output.lower()

    def test_analyze_binary_file_exits_1(self, tmp_path: Path) -> None:
        binary_file = tmp_path / "binary.bin"
        binary_file.write_bytes(b"\x00\x01\x02\x03" * 100)  # null bytes trigger binary detection
        result = runner.invoke(app, ["analyze", str(binary_file)])
        assert result.exit_code == 1
        assert "binary" in result.output.lower() or "cannot" in result.output.lower()

    def test_analyze_text_file_with_mocked_model(self, tmp_path: Path) -> None:
        text_file = tmp_path / "doc.txt"
        text_file.write_text("This is a quarterly financial report.")

        with (
            patch(
                "file_organizer.models.text_model.TextModel.initialize",
            ),
            patch(
                "file_organizer.models.text_model.TextModel.generate",
                return_value="Software Documentation",
            ),
            patch(
                "file_organizer.services.analyzer.generate_category",
                return_value="Finance",
            ),
            patch(
                "file_organizer.services.analyzer.generate_description",
                return_value="A financial report document.",
            ),
            patch(
                "file_organizer.services.analyzer.calculate_confidence",
                return_value=0.85,
            ),
        ):
            result = runner.invoke(app, ["analyze", str(text_file)])
        assert result.exit_code == 0
        assert "finance" in result.output.lower() or "financial" in result.output.lower()

    def test_analyze_json_output(self, tmp_path: Path) -> None:
        text_file = tmp_path / "doc.txt"
        text_file.write_text("This is a quarterly financial report.")

        with (
            patch("file_organizer.models.text_model.TextModel.initialize"),
            patch(
                "file_organizer.services.analyzer.generate_category",
                return_value="Finance",
            ),
            patch(
                "file_organizer.services.analyzer.generate_description",
                return_value="A financial report document.",
            ),
            patch(
                "file_organizer.services.analyzer.calculate_confidence",
                return_value=0.85,
            ),
        ):
            result = runner.invoke(app, ["analyze", str(text_file), "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert "category" in data
        assert "description" in data
        assert "confidence" in data
        assert data["category"] == "Finance"
        assert data["confidence"] == pytest.approx(0.85)

    def test_analyze_runtime_error_exits_1(self, tmp_path: Path) -> None:
        text_file = tmp_path / "doc.txt"
        text_file.write_text("Some content.")

        with (
            patch("file_organizer.models.text_model.TextModel.initialize"),
            patch(
                "file_organizer.services.analyzer.generate_category",
                side_effect=RuntimeError("AI failed"),
            ),
        ):
            result = runner.invoke(app, ["analyze", str(text_file)])
        assert result.exit_code == 1
        assert "error" in result.output.lower()

    def test_analyze_oserror_reading_exits_1(self, tmp_path: Path) -> None:
        text_file = tmp_path / "unreadable.txt"
        text_file.write_text("Some content.")

        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            result = runner.invoke(app, ["analyze", str(text_file)])
        assert result.exit_code == 1
        assert "error" in result.output.lower()
