"""Tests for the organize CLI commands (organize.py).

Tests the ``organize`` and ``preview`` top-level commands with mocked
FileOrganizer service.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app

pytestmark = [pytest.mark.unit]

runner = CliRunner()


def _mock_result(
    total: int = 10,
    processed: int = 8,
    skipped: int = 1,
    failed: int = 1,
) -> MagicMock:
    """Create a mock organize result."""
    result = MagicMock()
    result.total_files = total
    result.processed_files = processed
    result.skipped_files = skipped
    result.failed_files = failed
    return result


# ---------------------------------------------------------------------------
# organize
# ---------------------------------------------------------------------------


class TestOrganize:
    """Tests for the ``organize`` command."""

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_basic(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(app, ["organize", str(input_dir), str(output_dir)])
        assert result.exit_code == 0
        assert "8 processed" in result.output
        assert "1 skipped" in result.output
        mock_cls.assert_called_once_with(
            dry_run=False,
            parallel_workers=None,
            prefetch_depth=2,
            enable_vision=True,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_dry_run(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(app, ["organize", str(input_dir), str(output_dir), "--dry-run"])
        assert result.exit_code == 0
        assert "dry run" in result.output.lower() or "Dry run" in result.output
        mock_cls.assert_called_once_with(
            dry_run=True,
            parallel_workers=None,
            prefetch_depth=2,
            enable_vision=True,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_parallel_controls(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        """CLI parallel controls should be wired into runtime config."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(
            app,
            [
                "organize",
                str(input_dir),
                str(output_dir),
                "--max-workers",
                "3",
                "--prefetch-depth",
                "1",
                "--no-vision",
            ],
        )
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=False,
            parallel_workers=3,
            prefetch_depth=1,
            enable_vision=False,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_sequential_forces_single_worker(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        """--sequential should force one worker and disable queue-ahead."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(
            app,
            ["organize", str(input_dir), str(output_dir), "--sequential"],
        )
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=False,
            parallel_workers=1,
            prefetch_depth=0,
            enable_vision=True,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_rejects_incompatible_worker_flags(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        """--sequential and --max-workers>1 should fail fast."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        result = runner.invoke(
            app,
            [
                "organize",
                str(input_dir),
                str(output_dir),
                "--sequential",
                "--max-workers",
                "4",
            ],
        )
        assert result.exit_code == 2
        assert "--sequential cannot be combined with --max-workers > 1" in result.output
        mock_cls.assert_not_called()

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_text_only_alias_for_no_vision(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        """--text-only should route as --no-vision (enable_vision=False)."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(
            app,
            ["organize", str(input_dir), str(output_dir), "--text-only"],
        )
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=False,
            parallel_workers=None,
            prefetch_depth=2,
            enable_vision=False,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_no_prefetch_flag_passes_through(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        """--no-prefetch should be forwarded as no_prefetch=True."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(
            app,
            ["organize", str(input_dir), str(output_dir), "--no-prefetch"],
        )
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=False,
            parallel_workers=None,
            prefetch_depth=0,
            enable_vision=True,
            no_prefetch=True,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_sequential_with_max_workers_one_is_valid(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        """--sequential with --max-workers 1 should succeed."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(
            app,
            [
                "organize",
                str(input_dir),
                str(output_dir),
                "--sequential",
                "--max-workers",
                "1",
            ],
        )
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=False,
            parallel_workers=1,
            prefetch_depth=0,
            enable_vision=True,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_organize_prefetch_depth_zero_explicit(
        self, mock_cls: MagicMock, tmp_path: Path
    ) -> None:
        """Explicit --prefetch-depth 0 should be forwarded unchanged."""
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result()

        result = runner.invoke(
            app,
            ["organize", str(input_dir), str(output_dir), "--prefetch-depth", "0"],
        )
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=False,
            parallel_workers=None,
            prefetch_depth=0,
            enable_vision=True,
            no_prefetch=False,
        )

    @patch(
        "file_organizer.core.organizer.FileOrganizer",
        side_effect=RuntimeError("Ollama not running"),
    )
    def test_organize_error(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()
        output_dir.mkdir()

        result = runner.invoke(app, ["organize", str(input_dir), str(output_dir)])
        assert result.exit_code == 1
        assert "Ollama not running" in result.output


# ---------------------------------------------------------------------------
# preview
# ---------------------------------------------------------------------------


class TestPreview:
    """Tests for the ``preview`` command."""

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_preview_basic(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result(total=15)

        result = runner.invoke(app, ["preview", str(tmp_path)])
        assert result.exit_code == 0
        assert "15" in result.output
        mock_cls.assert_called_once_with(
            dry_run=True,
            parallel_workers=None,
            prefetch_depth=2,
            enable_vision=True,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_preview_max_workers(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result(total=5)

        result = runner.invoke(app, ["preview", str(tmp_path), "--max-workers", "4"])
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=True,
            parallel_workers=4,
            prefetch_depth=2,
            enable_vision=True,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_preview_sequential(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result(total=5)

        result = runner.invoke(app, ["preview", str(tmp_path), "--sequential"])
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=True,
            parallel_workers=1,
            prefetch_depth=0,
            enable_vision=True,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_preview_no_vision(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result(total=5)

        result = runner.invoke(app, ["preview", str(tmp_path), "--no-vision"])
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=True,
            parallel_workers=None,
            prefetch_depth=2,
            enable_vision=False,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_preview_text_only_alias(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result(total=5)

        result = runner.invoke(app, ["preview", str(tmp_path), "--text-only"])
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=True,
            parallel_workers=None,
            prefetch_depth=2,
            enable_vision=False,
            no_prefetch=False,
        )

    @patch("file_organizer.core.organizer.FileOrganizer")
    def test_preview_no_prefetch(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        mock_org = MagicMock()
        mock_cls.return_value = mock_org
        mock_org.organize.return_value = _mock_result(total=5)

        result = runner.invoke(app, ["preview", str(tmp_path), "--no-prefetch"])
        assert result.exit_code == 0
        mock_cls.assert_called_once_with(
            dry_run=True,
            parallel_workers=None,
            prefetch_depth=0,
            enable_vision=True,
            no_prefetch=True,
        )

    def test_preview_sequential_conflicts_with_max_workers(self, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["preview", str(tmp_path), "--sequential", "--max-workers", "4"]
        )
        assert result.exit_code == 2
        assert "--sequential" in result.output

    @patch(
        "file_organizer.core.organizer.FileOrganizer",
        side_effect=ValueError("Invalid directory"),
    )
    def test_preview_error(self, mock_cls: MagicMock, tmp_path: Path) -> None:
        result = runner.invoke(app, ["preview", str(tmp_path)])
        assert result.exit_code == 1
        assert "Invalid directory" in result.output
