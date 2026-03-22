"""Integration tests for organize/preview command options.

Covers: _resolve_parallel_settings (conflict detection, sequential, no_prefetch),
--max-workers, --sequential, --no-vision/--text-only, --prefetch-depth, preview
command with the same flag combinations.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import typer

from file_organizer.cli.organize import _resolve_parallel_settings

pytestmark = [pytest.mark.integration]


class TestResolveParallelSettings:
    """Unit-level tests for the _resolve_parallel_settings helper."""

    def test_sequential_and_max_workers_conflict_raises(self) -> None:
        with pytest.raises(typer.Exit) as exc_info:
            _resolve_parallel_settings(sequential=True, max_workers=4, prefetch_depth=2)
        assert exc_info.value.exit_code == 2

    def test_sequential_with_no_max_workers_is_ok(self) -> None:
        workers, depth = _resolve_parallel_settings(
            sequential=True, max_workers=None, prefetch_depth=2
        )
        assert workers == 1
        assert depth == 0

    def test_sequential_with_max_workers_1_is_ok(self) -> None:
        workers, depth = _resolve_parallel_settings(
            sequential=True, max_workers=1, prefetch_depth=2
        )
        assert workers == 1
        assert depth == 0

    def test_max_workers_auto_when_not_sequential(self) -> None:
        workers, depth = _resolve_parallel_settings(
            sequential=False, max_workers=None, prefetch_depth=2
        )
        assert workers is None
        assert depth == 2

    def test_max_workers_explicit(self) -> None:
        workers, depth = _resolve_parallel_settings(
            sequential=False, max_workers=3, prefetch_depth=2
        )
        assert workers == 3
        assert depth == 2

    def test_no_prefetch_alias_zeroes_depth(self) -> None:
        workers, depth = _resolve_parallel_settings(
            sequential=False, max_workers=2, prefetch_depth=4, no_prefetch=True
        )
        assert workers == 2
        assert depth == 0

    def test_prefetch_depth_zero_respected(self) -> None:
        workers, depth = _resolve_parallel_settings(
            sequential=False, max_workers=None, prefetch_depth=0
        )
        assert depth == 0

    def test_sequential_overrides_prefetch_depth(self) -> None:
        """sequential=True must set depth=0 regardless of prefetch_depth value."""
        workers, depth = _resolve_parallel_settings(
            sequential=True, max_workers=1, prefetch_depth=5
        )
        assert depth == 0


class TestOrganizeCLIOptions:
    """Integration tests for the organize command option parsing and routing."""

    def test_organize_sequential_flag(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
                "--sequential",
            ],
        )
        assert result.exit_code == 0

    def test_organize_max_workers(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
                "--max-workers",
                "2",
            ],
        )
        assert result.exit_code == 0

    def test_organize_no_vision_flag(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
                "--no-vision",
            ],
        )
        assert result.exit_code == 0

    def test_organize_text_only_alias(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """--text-only is an alias for --no-vision."""
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
                "--text-only",
            ],
        )
        assert result.exit_code == 0

    def test_organize_no_prefetch_flag(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
                "--no-prefetch",
            ],
        )
        assert result.exit_code == 0

    def test_organize_prefetch_depth_zero(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--dry-run",
                "--prefetch-depth",
                "0",
            ],
        )
        assert result.exit_code == 0

    def test_organize_sequential_max_workers_conflict_exits_2(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """--sequential combined with --max-workers > 1 must exit code 2."""
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "organize",
                str(integration_source_dir),
                str(integration_output_dir),
                "--sequential",
                "--max-workers",
                "4",
            ],
        )
        assert result.exit_code == 2

    def test_organize_exception_exits_1(
        self,
        stub_nltk: None,
        integration_source_dir: Path,
        integration_output_dir: Path,
    ) -> None:
        """A FileOrganizer exception propagates as exit code 1."""
        from unittest.mock import patch

        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        with patch(
            "file_organizer.core.organizer.FileOrganizer.organize",
            side_effect=RuntimeError("simulated organizer failure"),
        ):
            result = CliRunner().invoke(
                app,
                [
                    "organize",
                    str(integration_source_dir),
                    str(integration_output_dir),
                ],
            )
        assert result.exit_code == 1
        assert "error" in result.output.lower()


class TestPreviewCLIOptions:
    def test_preview_sequential_flag(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
    ) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "preview",
                str(integration_source_dir),
                "--sequential",
            ],
        )
        assert result.exit_code == 0

    def test_preview_max_workers(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
    ) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "preview",
                str(integration_source_dir),
                "--max-workers",
                "3",
            ],
        )
        assert result.exit_code == 0

    def test_preview_no_vision(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
    ) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "preview",
                str(integration_source_dir),
                "--no-vision",
            ],
        )
        assert result.exit_code == 0

    def test_preview_sequential_max_workers_conflict(
        self,
        stub_all_models: None,
        stub_nltk: None,
        integration_source_dir: Path,
    ) -> None:
        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        result = CliRunner().invoke(
            app,
            [
                "preview",
                str(integration_source_dir),
                "--sequential",
                "--max-workers",
                "2",
            ],
        )
        assert result.exit_code == 2

    def test_preview_exception_exits_1(
        self,
        integration_source_dir: Path,
    ) -> None:
        from unittest.mock import patch

        from typer.testing import CliRunner

        from file_organizer.cli.main import app

        with patch(
            "file_organizer.core.organizer.FileOrganizer.organize",
            side_effect=RuntimeError("simulated failure"),
        ):
            result = CliRunner().invoke(app, ["preview", str(integration_source_dir)])
        assert result.exit_code == 1
        assert "error" in result.output.lower()
