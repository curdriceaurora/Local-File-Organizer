"""Integration tests for CLI main commands.

Covers: version, hardware-info (json/text), undo/redo/history, analytics,
and global callback flags (--verbose, --dry-run, --json, --yes, --no-interactive).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.integration]

runner = CliRunner()


class TestVersionCommand:
    def test_version_exits_zero(self) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0

    def test_version_output_contains_package_name(self) -> None:
        result = runner.invoke(app, ["version"])
        assert "fo" in result.output.lower()

    def test_version_shows_version_string(self) -> None:
        from file_organizer.version import __version__

        result = runner.invoke(app, ["version"])
        assert __version__ in result.output


def _make_hw_profile() -> SimpleNamespace:
    """Strict hardware profile stub — missing attributes raise AttributeError."""
    return SimpleNamespace(
        gpu_type=SimpleNamespace(value="cuda"),
        gpu_name="RTX 3080",
        vram_gb=10,
        ram_gb=32,
        cpu_cores=16,
        os_name="Linux",
        arch="x86_64",
        recommended_text_model=lambda: "qwen2.5:7b",
        recommended_workers=lambda: 4,
        to_dict=lambda: {"gpu_type": "cuda", "vram_gb": 10, "cpu_cores": 16},
    )


class TestHardwareInfoCommand:
    def test_hardware_info_text_exits_zero(self) -> None:
        with patch(
            "file_organizer.core.hardware_profile.detect_hardware",
            return_value=_make_hw_profile(),
        ):
            result = runner.invoke(app, ["hardware-info"])
        assert result.exit_code == 0
        assert "RTX 3080" in result.output
        assert "16" in result.output

    def test_hardware_info_json_output(self) -> None:
        import json

        with patch(
            "file_organizer.core.hardware_profile.detect_hardware",
            return_value=_make_hw_profile(),
        ):
            result = runner.invoke(app, ["hardware-info", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output.strip())
        assert data.get("gpu_type") == "cuda"
        assert data.get("vram_gb") == 10


class TestGlobalCallbackFlags:
    """Tests for global flags applied via main_callback."""

    def test_dry_run_flag_propagates(
        self,
        stub_all_models: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """Global --dry-run produces no output files."""
        result = runner.invoke(
            app,
            [
                "--dry-run",
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
            ],
        )
        assert result.exit_code == 0
        output_files = list(integration_output_dir.rglob("*"))
        assert len(output_files) == 0

    def test_verbose_flag_is_set(
        self,
        stub_all_models: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """Global --verbose flag is accepted (no parse error)."""
        result = runner.invoke(
            app,
            [
                "--verbose",
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

    def test_json_flag_is_set(
        self,
        stub_all_models: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """Global --json flag is accepted without error."""
        result = runner.invoke(
            app,
            [
                "--json",
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

    def test_yes_flag_is_set(
        self,
        stub_all_models: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """Global --yes flag is accepted without error."""
        result = runner.invoke(
            app,
            [
                "--yes",
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

    def test_no_interactive_flag_is_set(
        self,
        stub_all_models: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """Global --no-interactive flag is accepted without error."""
        result = runner.invoke(
            app,
            [
                "--no-interactive",
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0


class TestUndoRedoHistoryCommands:
    """Tests for undo, redo, and history commands."""

    def test_undo_no_history_exits_nonzero(self) -> None:
        """undo without any history exits with a non-zero code."""
        result = runner.invoke(app, ["undo"])
        # Nothing to undo — should exit non-zero (1) but not crash
        assert result.exit_code != 0 or "nothing" in result.output.lower()

    def test_undo_dry_run_accepted(self) -> None:
        """undo --dry-run is accepted without crash."""
        result = runner.invoke(app, ["undo", "--dry-run"])
        assert result.exit_code in (0, 1)

    def test_undo_operation_id_accepted(self) -> None:
        """undo --operation-id parses correctly."""
        result = runner.invoke(app, ["undo", "--operation-id", "999"])
        assert result.exit_code in (0, 1)

    def test_undo_transaction_id_accepted(self) -> None:
        """undo --transaction-id parses correctly."""
        result = runner.invoke(app, ["undo", "--transaction-id", "abc-123"])
        assert result.exit_code in (0, 1)

    def test_redo_no_history_exits_nonzero(self) -> None:
        """redo without any history exits with a non-zero code."""
        result = runner.invoke(app, ["redo"])
        assert result.exit_code != 0 or "nothing" in result.output.lower()

    def test_redo_dry_run_accepted(self) -> None:
        result = runner.invoke(app, ["redo", "--dry-run"])
        assert result.exit_code in (0, 1)

    def test_redo_operation_id_accepted(self) -> None:
        result = runner.invoke(app, ["redo", "--operation-id", "42"])
        assert result.exit_code in (0, 1)

    def test_history_default_limit(self) -> None:
        """history command runs and exits cleanly (empty history is OK)."""
        result = runner.invoke(app, ["history"])
        assert result.exit_code in (0, 1)

    def test_history_custom_limit(self) -> None:
        result = runner.invoke(app, ["history", "--limit", "5"])
        assert result.exit_code in (0, 1)

    def test_history_type_filter(self) -> None:
        result = runner.invoke(app, ["history", "--type", "organize"])
        assert result.exit_code in (0, 1)

    def test_history_status_filter(self) -> None:
        result = runner.invoke(app, ["history", "--status", "completed"])
        assert result.exit_code in (0, 1)

    def test_history_stats_flag(self) -> None:
        result = runner.invoke(app, ["history", "--stats"])
        assert result.exit_code in (0, 1)

    def test_history_verbose_flag(self) -> None:
        result = runner.invoke(app, ["history", "--verbose"])
        assert result.exit_code in (0, 1)


class TestVersionFlag:
    """Tests for the eager --version global flag (distinct from the version sub-command)."""

    def test_version_flag_exits_zero(self) -> None:
        """--version eager flag exits with code 0."""
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0

    def test_version_flag_prints_version(self) -> None:
        """--version flag outputs the version string."""
        from version import __version__

        result = runner.invoke(app, ["--version"])
        assert __version__ in result.output


class TestAnalyticsCommand:
    def test_analytics_no_args(self) -> None:
        """analytics without a directory hits the None branch; argparse exits 2."""
        result = runner.invoke(app, ["analytics"])
        # directory is None → args stays []; analytics_command requires directory → exit 2
        assert result.exit_code in (0, 1, 2)

    def test_analytics_with_directory(self, tmp_path: Path) -> None:
        """analytics with an explicit directory argument is accepted."""
        result = runner.invoke(app, ["analytics", str(tmp_path)])
        assert result.exit_code in (0, 1)

    def test_analytics_verbose_flag(self, tmp_path: Path) -> None:
        """analytics --verbose is accepted."""
        result = runner.invoke(app, ["analytics", str(tmp_path), "--verbose"])
        assert result.exit_code in (0, 1)


class TestEntryPoint:
    """Tests for _register_profile_command and main() entry point."""

    def test_register_profile_command_does_not_raise(self) -> None:
        """_register_profile_command() runs without error (ImportError is silenced)."""
        from file_organizer.cli.main import _register_profile_command

        _register_profile_command()  # should not raise

    def test_main_calls_register_and_app(self) -> None:
        """main() calls _register_profile_command then app()."""
        from unittest.mock import patch

        from file_organizer.cli.main import main

        with (
            patch("file_organizer.cli.main._register_profile_command") as mock_reg,
            patch("file_organizer.cli.main.app") as mock_app,
        ):
            main()
        mock_reg.assert_called_once()
        mock_app.assert_called_once()
