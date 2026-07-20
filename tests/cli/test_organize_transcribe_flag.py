"""Tests that --transcribe-audio and --max-transcribe-seconds reach FileOrganizer.

Pins the CLI wiring contract end-to-end: the flags parse, get threaded
through, and convert the documented "0 disables cap" boundary to None
(the organizer's representation of uncapped).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app


@pytest.mark.unit
@pytest.mark.ci
class TestOrganizeTranscribeFlag:
    def test_transcribe_audio_flag_threads_to_organizer(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        output_dir = tmp_path / "out"

        runner = CliRunner()
        with (
            patch("file_organizer.cli.organize._check_setup_completed", return_value=True),
            patch("file_organizer.core.organizer.FileOrganizer") as mock_org_cls,
        ):
            mock_org = MagicMock()
            mock_org_cls.return_value = mock_org
            mock_org.organize.return_value = MagicMock(
                processed_files=0, skipped_files=0, failed_files=0, total_files=0
            )

            result = runner.invoke(
                app,
                [
                    "organize",
                    str(input_dir),
                    str(output_dir),
                    "--transcribe-audio",
                    "--max-transcribe-seconds",
                    "300",
                ],
            )

        assert result.exit_code == 0, result.output
        kwargs = mock_org_cls.call_args.kwargs
        assert kwargs.get("transcribe_audio") is True
        assert kwargs.get("max_transcribe_seconds") == 300.0

    def test_transcribe_audio_default_off(self, tmp_path: Path) -> None:
        # Without the flag, FileOrganizer must receive transcribe_audio=False.
        # Default ON would silently slow `fo organize` for every audio file
        # and break beta testers without the [audio] extra.
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        output_dir = tmp_path / "out"

        runner = CliRunner()
        with (
            patch("file_organizer.cli.organize._check_setup_completed", return_value=True),
            patch("file_organizer.core.organizer.FileOrganizer") as mock_org_cls,
        ):
            mock_org_cls.return_value = MagicMock()
            mock_org_cls.return_value.organize.return_value = MagicMock(
                processed_files=0, skipped_files=0, failed_files=0, total_files=0
            )

            result = runner.invoke(app, ["organize", str(input_dir), str(output_dir)])

        assert result.exit_code == 0, result.output
        kwargs = mock_org_cls.call_args.kwargs
        assert kwargs.get("transcribe_audio") is False

    def test_max_transcribe_seconds_zero_means_no_cap(self, tmp_path: Path) -> None:
        # The documented "0 disables the cap entirely" boundary maps to
        # `max_transcribe_seconds=None` in the organizer (None = uncapped).
        # Without this conversion, `--max-transcribe-seconds 0` would skip
        # every audio file because every duration > 0.
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        output_dir = tmp_path / "out"

        runner = CliRunner()
        with (
            patch("file_organizer.cli.organize._check_setup_completed", return_value=True),
            patch("file_organizer.core.organizer.FileOrganizer") as mock_org_cls,
        ):
            mock_org_cls.return_value = MagicMock()
            mock_org_cls.return_value.organize.return_value = MagicMock(
                processed_files=0, skipped_files=0, failed_files=0, total_files=0
            )

            result = runner.invoke(
                app,
                [
                    "organize",
                    str(input_dir),
                    str(output_dir),
                    "--transcribe-audio",
                    "--max-transcribe-seconds",
                    "0",
                ],
            )

        assert result.exit_code == 0, result.output
        kwargs = mock_org_cls.call_args.kwargs
        assert kwargs.get("max_transcribe_seconds") is None

    def test_preview_supports_same_flags(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        input_dir.mkdir()

        runner = CliRunner()
        with (
            patch("file_organizer.cli.organize._check_setup_completed", return_value=True),
            patch("file_organizer.core.organizer.FileOrganizer") as mock_org_cls,
        ):
            mock_org_cls.return_value = MagicMock()
            mock_org_cls.return_value.organize.return_value = MagicMock(total_files=0)

            result = runner.invoke(
                app,
                [
                    "preview",
                    str(input_dir),
                    "--transcribe-audio",
                    "--max-transcribe-seconds",
                    "120",
                    "--whisper-model",
                    "small",
                ],
            )

        assert result.exit_code == 0, result.output
        kwargs = mock_org_cls.call_args.kwargs
        assert kwargs.get("transcribe_audio") is True
        assert kwargs.get("max_transcribe_seconds") == 120.0
        assert kwargs.get("whisper_model") == "small"

    def test_whisper_model_flag_threads_to_organizer(self, tmp_path: Path) -> None:
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        output_dir = tmp_path / "out"

        runner = CliRunner()
        with (
            patch("file_organizer.cli.organize._check_setup_completed", return_value=True),
            patch("file_organizer.core.organizer.FileOrganizer") as mock_org_cls,
        ):
            mock_org_cls.return_value = MagicMock()
            mock_org_cls.return_value.organize.return_value = MagicMock(
                processed_files=0, skipped_files=0, failed_files=0, total_files=0
            )

            result = runner.invoke(
                app,
                [
                    "organize",
                    str(input_dir),
                    str(output_dir),
                    "--transcribe-audio",
                    "--whisper-model",
                    "base",
                ],
            )

        assert result.exit_code == 0, result.output
        kwargs = mock_org_cls.call_args.kwargs
        assert kwargs.get("whisper_model") == "base"

    def test_whisper_model_defaults_to_tiny(self, tmp_path: Path) -> None:
        # "tiny" keeps the default transcription path fast; larger models
        # must be an explicit opt-in via --whisper-model.
        input_dir = tmp_path / "in"
        input_dir.mkdir()
        output_dir = tmp_path / "out"

        runner = CliRunner()
        with (
            patch("file_organizer.cli.organize._check_setup_completed", return_value=True),
            patch("file_organizer.core.organizer.FileOrganizer") as mock_org_cls,
        ):
            mock_org_cls.return_value = MagicMock()
            mock_org_cls.return_value.organize.return_value = MagicMock(
                processed_files=0, skipped_files=0, failed_files=0, total_files=0
            )

            result = runner.invoke(app, ["organize", str(input_dir), str(output_dir)])

        assert result.exit_code == 0, result.output
        kwargs = mock_org_cls.call_args.kwargs
        assert kwargs.get("whisper_model") == "tiny"
