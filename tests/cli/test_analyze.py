"""Tests for the ``analyze`` CLI command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from file_organizer.cli.main import app

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_model() -> MagicMock:
    """Return a mock TextModel whose generate() returns canned responses."""
    model = MagicMock()
    # First call -> category, second call -> description
    model.generate.side_effect = ["technical", "A technical document about Python."]
    return model


def _patch_text_model(mock_model: MagicMock | None = None):
    """Patch TextModel so import + init succeeds and returns *mock_model*."""
    if mock_model is None:
        mock_model = _make_mock_model()

    cls = MagicMock()
    cls.get_default_config.return_value = MagicMock(name="test-model")
    instance = mock_model
    cls.return_value = instance
    return patch("file_organizer.models.text_model.TextModel", cls)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_analyze_help():
    """``analyze --help`` exits 0 and mentions file argument."""
    result = runner.invoke(app, ["analyze", "--help"])
    assert result.exit_code == 0
    assert "file" in result.stdout.lower()


def test_analyze_text_file(tmp_path: Path):
    """Analyze a simple text file and get structured output."""
    f = tmp_path / "sample.txt"
    f.write_text("def hello(): pass")

    with _patch_text_model():
        result = runner.invoke(app, ["analyze", str(f)])

    assert result.exit_code == 0
    assert "Category:" in result.stdout


def test_analyze_shows_confidence(tmp_path: Path):
    """Output includes a 'Confidence:' line."""
    f = tmp_path / "sample.txt"
    f.write_text("Some meaningful content for analysis." * 10)

    with _patch_text_model():
        result = runner.invoke(app, ["analyze", str(f)])

    assert result.exit_code == 0
    assert "Confidence:" in result.stdout


def test_analyze_verbose_mode(tmp_path: Path):
    """Verbose flag adds model name, timing, and content length."""
    f = tmp_path / "sample.txt"
    f.write_text("Hello world content")

    with _patch_text_model():
        result = runner.invoke(app, ["analyze", str(f), "--verbose"])

    assert result.exit_code == 0
    output = result.stdout
    assert "Model:" in output
    assert "Processing time:" in output
    assert "Content length:" in output


def test_analyze_nonexistent_file():
    """Analyzing a file that doesn't exist exits with code 1."""
    result = runner.invoke(app, ["analyze", "/nonexistent/file.txt"])
    assert result.exit_code == 1
    assert "not found" in result.stdout.lower()


def test_analyze_empty_file(tmp_path: Path):
    """Empty files are handled gracefully (no crash)."""
    f = tmp_path / "empty.txt"
    f.write_text("")

    with _patch_text_model():
        result = runner.invoke(app, ["analyze", str(f)])

    assert result.exit_code == 0


def test_analyze_large_file(tmp_path: Path):
    """Large files are truncated transparently and analyzed."""
    f = tmp_path / "big.txt"
    f.write_text("x" * 5000)

    with _patch_text_model():
        result = runner.invoke(app, ["analyze", str(f)])

    assert result.exit_code == 0


def test_analyze_binary_file(tmp_path: Path):
    """Binary files are detected and rejected with a warning (exit code 1)."""
    f = tmp_path / "data.bin"
    # Write explicit NUL bytes to guarantee binary detection triggers.
    f.write_bytes(b"\x00" * 256)

    with _patch_text_model():
        result = runner.invoke(app, ["analyze", str(f)])

    assert result.exit_code == 1
    assert "binary" in result.output.lower()


def test_analyze_json_output(tmp_path: Path):
    """``--json`` flag produces valid JSON with expected keys."""
    f = tmp_path / "sample.txt"
    f.write_text("Some content here")

    with _patch_text_model():
        result = runner.invoke(app, ["analyze", str(f), "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert "description" in data
    assert "category" in data
    assert "confidence" in data


def test_analyze_handles_model_error(tmp_path: Path):
    """RuntimeError from the model yields exit code 1."""
    f = tmp_path / "sample.txt"
    f.write_text("content")

    mock_model = MagicMock()
    mock_model.generate.side_effect = RuntimeError("model exploded")

    # Patch generate_category to propagate the RuntimeError
    with (
        _patch_text_model(mock_model),
        patch(
            "file_organizer.services.analyzer.generate_category",
            side_effect=RuntimeError("AI analysis blew up"),
        ),
    ):
        result = runner.invoke(app, ["analyze", str(f)])

    assert result.exit_code == 1
    assert "AI analysis" in result.stdout


def test_analyze_handles_no_ollama(tmp_path: Path):
    """ImportError during model init yields exit 1 with 'ollama' hint."""
    f = tmp_path / "sample.txt"
    f.write_text("content")

    with patch(
        "file_organizer.models.text_model.TextModel",
        side_effect=ImportError("no ollama"),
    ):
        result = runner.invoke(app, ["analyze", str(f)])

    assert result.exit_code == 1
    assert "ollama" in result.stdout.lower()


def test_analyze_multiple_categories(tmp_path: Path):
    """Different content triggers different category responses."""
    f1 = tmp_path / "code.py"
    f1.write_text("import numpy as np")

    f2 = tmp_path / "recipe.txt"
    f2.write_text("Mix flour and eggs")

    # First file -> technical
    model_tech = MagicMock()
    model_tech.generate.side_effect = ["technical", "A Python script."]
    with _patch_text_model(model_tech):
        r1 = runner.invoke(app, ["analyze", str(f1)])

    # Second file -> recipe
    model_recipe = MagicMock()
    model_recipe.generate.side_effect = ["recipe", "A cooking recipe."]
    with _patch_text_model(model_recipe):
        r2 = runner.invoke(app, ["analyze", str(f2)])

    assert r1.exit_code == 0
    assert r2.exit_code == 0
    # Both should produce Category: lines (content differs per mock)
    assert "Category:" in r1.stdout
    assert "Category:" in r2.stdout
