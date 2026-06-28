"""Tests for the api-keys CLI commands."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.ci, pytest.mark.integration]

runner = CliRunner()


def test_api_keys_generate_command(tmp_path: Path) -> None:
    """Verify that api-keys generate command works correctly."""
    output_file = tmp_path / "new_key.txt"
    result = runner.invoke(
        app,
        ["api-keys", "generate", "--output", str(output_file), "--prefix", "testprefix"],
    )
    assert result.exit_code == 0
    assert "API key saved to:" in result.stdout
    assert "Bcrypt hash:" in result.stdout
    assert output_file.exists()
    assert output_file.read_text().startswith("testprefix_")
