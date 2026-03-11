"""Integration tests for Gap P6: CLI End-to-End.

Verifies that CLI commands invoke the real FileOrganizer and that flags
(``--dry-run``, ``--verbose``) flow through correctly.

These tests use ``typer.testing.CliRunner`` with stubbed models so that
no real Ollama/OpenAI connection is required.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.integration]

runner = CliRunner()


class TestCLIOrganize:
    """CLI organize command invokes real FileOrganizer pipeline."""

    def test_cli_organize_dry_run(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """``organize --dry-run`` produces output and exit code 0."""
        result = runner.invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
            ],
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"
        assert "processed" in result.output.lower() or "done" in result.output.lower()

        # Dry run should not create files in output
        output_files = [f for f in integration_output_dir.rglob("*") if f.is_file()]
        assert len(output_files) == 0

    def test_cli_organize_creates_output(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """``organize`` without --dry-run creates files in output dir."""
        result = runner.invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
            ],
        )

        assert result.exit_code == 0, f"CLI failed: {result.output}"

        # Files should exist in output
        output_files = [f for f in integration_output_dir.rglob("*") if f.is_file()]
        assert len(output_files) == 3

    def test_cli_verbose_increases_output(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """``--verbose`` flag produces more output than default."""
        # Run without verbose
        result_quiet = runner.invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
            ],
        )

        # Run with verbose (need fresh output dir)
        verbose_out = integration_output_dir.parent / "verbose_output"
        verbose_out.mkdir()

        result_verbose = runner.invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(verbose_out),
                "--dry-run",
                "--verbose",
            ],
        )

        assert result_quiet.exit_code == 0
        assert result_verbose.exit_code == 0
        # Verbose output should be strictly longer than quiet output
        assert len(result_verbose.output) > len(result_quiet.output), (
            "Verbose mode did not produce additional output"
        )
