"""Compatibility tests for CLI transcription flags at the canonical boundary."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from file_organizer.cli.main import app
from file_organizer.core.organization_service import OrganizationScan, OrganizationService
from file_organizer.core.types import OrganizationResult


@pytest.fixture
def service() -> MagicMock:
    mock = MagicMock(spec=OrganizationService)
    mock.scan.return_value = OrganizationScan(Path("input"), (), {})
    mock.preview.return_value = OrganizationResult()
    mock.execute.return_value = OrganizationResult()
    return mock


@pytest.mark.unit
@pytest.mark.ci
@pytest.mark.parametrize(
    ("command", "expected_seconds", "expected_model"),
    [
        ("organize", 300.0, "base"),
        ("preview", 120.0, "small"),
        ("organize", None, "tiny"),
    ],
)
def test_transcription_flags_reach_canonical_options(
    command: str,
    expected_seconds: float | None,
    expected_model: str,
    service: MagicMock,
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    args = [command, str(input_dir)]
    if command == "organize":
        args.append(str(output_dir))
    seconds = "0" if expected_seconds is None else str(expected_seconds)
    args.extend(
        [
            "--transcribe-audio",
            "--max-transcribe-seconds",
            seconds,
            "--whisper-model",
            expected_model,
        ]
    )
    with (
        patch("file_organizer.cli.organize._check_setup_completed", return_value=True),
        patch("file_organizer.cli.organize._create_service", return_value=service),
    ):
        result = CliRunner().invoke(app, args)
    assert result.exit_code == 0, result.output
    call = service.execute.call_args or service.preview.call_args
    options = call.args[0].options
    assert options.transcribe_audio is True
    assert options.max_transcribe_seconds == expected_seconds
    assert options.whisper_model == expected_model


@pytest.mark.unit
@pytest.mark.ci
def test_transcription_remains_opt_in(service: MagicMock, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    with (
        patch("file_organizer.cli.organize._check_setup_completed", return_value=True),
        patch("file_organizer.cli.organize._create_service", return_value=service),
    ):
        result = CliRunner().invoke(app, ["organize", str(input_dir), str(output_dir)])
    assert result.exit_code == 0, result.output
    options = service.execute.call_args.args[0].options
    assert options.transcribe_audio is False
    assert options.whisper_model == "tiny"
