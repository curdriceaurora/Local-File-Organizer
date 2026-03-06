"""Tests for the ``search`` CLI command."""

from __future__ import annotations

import json
import re
from pathlib import Path

from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from *text* for portable string assertions."""
    return _ANSI_RE.sub("", text)


def test_search_help():
    """``search --help`` exits 0 and documents query, directory, --type options."""
    result = runner.invoke(app, ["search", "--help"])
    assert result.exit_code == 0
    plain = _strip_ansi(result.output)
    assert "query" in plain.lower()
    assert "directory" in plain.lower()
    assert "--type" in plain


def test_search_finds_files_by_name(tmp_path: Path):
    """Glob pattern *.txt matches only .txt files."""
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "b.pdf").write_text("world")
    (tmp_path / "c.py").write_text("code")

    result = runner.invoke(app, ["search", "*.txt", str(tmp_path)])
    assert result.exit_code == 0
    assert "a.txt" in result.output
    assert "b.pdf" not in result.output


def test_search_finds_files_by_keyword(tmp_path: Path):
    """Keyword search without glob characters does substring matching."""
    (tmp_path / "readme.md").write_text("docs")
    (tmp_path / "notes.txt").write_text("notes")

    result = runner.invoke(app, ["search", "readme", str(tmp_path)])
    assert result.exit_code == 0
    assert "readme.md" in result.output


def test_search_case_insensitive(tmp_path: Path):
    """Keyword search is case-insensitive."""
    (tmp_path / "README.md").write_text("docs")

    result = runner.invoke(app, ["search", "readme", str(tmp_path)])
    assert result.exit_code == 0
    assert "README.md" in result.output


def test_search_type_filter(tmp_path: Path):
    """--type image only returns image files."""
    (tmp_path / "a.txt").write_text("text")
    (tmp_path / "b.pdf").write_text("pdf")
    (tmp_path / "c.png").write_bytes(b"\x89PNG")

    result = runner.invoke(app, ["search", "*", str(tmp_path), "--type", "image"])
    assert result.exit_code == 0
    assert "c.png" in result.output
    assert "a.txt" not in result.output
    assert "b.pdf" not in result.output


def test_search_recursive(tmp_path: Path):
    """Recursive search (default) finds files in subdirectories."""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested")

    result = runner.invoke(app, ["search", "*.txt", str(tmp_path)])
    assert result.exit_code == 0
    assert "nested.txt" in result.output


def test_search_no_recursive(tmp_path: Path):
    """--no-recursive does NOT find files in subdirectories."""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested")
    (tmp_path / "top.txt").write_text("top")

    result = runner.invoke(app, ["search", "*.txt", str(tmp_path), "--no-recursive"])
    assert result.exit_code == 0
    assert "top.txt" in result.output
    assert "nested.txt" not in result.output


def test_search_limit_results(tmp_path: Path):
    """--limit caps the number of results shown."""
    for i in range(10):
        (tmp_path / f"file{i:02d}.txt").write_text(f"content {i}")

    result = runner.invoke(app, ["search", "*.txt", str(tmp_path), "--limit", "3"])
    assert result.exit_code == 0
    # Count how many .txt filenames appear in the output
    count = sum(1 for i in range(10) if f"file{i:02d}.txt" in result.output)
    assert count <= 3


def test_search_no_matches(tmp_path: Path):
    """Search with no matches exits 0 with 'No files' message."""
    (tmp_path / "a.txt").write_text("hello")

    result = runner.invoke(app, ["search", "nonexistent", str(tmp_path)])
    assert result.exit_code == 0
    assert "no file" in result.output.lower()


def test_search_empty_directory(tmp_path: Path):
    """Search in an empty directory exits 0 with 'No file' message."""
    result = runner.invoke(app, ["search", "*", str(tmp_path)])
    assert result.exit_code == 0
    assert "no file" in result.output.lower()


def test_search_nonexistent_directory():
    """Search in a nonexistent directory exits 1 with 'does not exist' message."""
    result = runner.invoke(app, ["search", "*", "/nonexistent/path/xyz"])
    assert result.exit_code == 1
    assert "does not exist" in result.output.lower()


def test_search_json_output(tmp_path: Path):
    """--json outputs a valid JSON array with expected fields."""
    (tmp_path / "data.csv").write_text("a,b,c")

    result = runner.invoke(app, ["search", "*.csv", str(tmp_path), "--json"])
    assert result.exit_code == 0
    records = json.loads(result.output)
    assert isinstance(records, list)
    assert len(records) == 1
    assert "path" in records[0]
    assert "size" in records[0]
    assert "modified" in records[0]


def test_search_glob_pattern_star(tmp_path: Path):
    """Glob *.log matches only .log files."""
    (tmp_path / "a.log").write_text("log a")
    (tmp_path / "b.log").write_text("log b")
    (tmp_path / "c.txt").write_text("text")

    result = runner.invoke(app, ["search", "*.log", str(tmp_path)])
    assert result.exit_code == 0
    assert "a.log" in result.output
    assert "b.log" in result.output
    assert "c.txt" not in result.output


def test_search_glob_pattern_question(tmp_path: Path):
    """Glob a?.txt matches a1.txt and a2.txt but not b1.txt."""
    (tmp_path / "a1.txt").write_text("a1")
    (tmp_path / "a2.txt").write_text("a2")
    (tmp_path / "b1.txt").write_text("b1")

    result = runner.invoke(app, ["search", "a?.txt", str(tmp_path)])
    assert result.exit_code == 0
    assert "a1.txt" in result.output
    assert "a2.txt" in result.output
    assert "b1.txt" not in result.output
