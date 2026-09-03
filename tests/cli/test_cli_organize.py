"""Contract tests for the local organization CLI adapter."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from file_organizer.cli.main import app
from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.organization_service import OrganizationScan, OrganizationService
from file_organizer.core.organize_options import (
    OrganizationMethodology,
    OrganizeOptions,
    TransferMode,
)
from file_organizer.core.plan import PLAN_SCHEMA_VERSION, OrganizationPlan
from file_organizer.core.types import OrganizationResult

pytestmark = [pytest.mark.unit]
runner = CliRunner()
_SETUP_PATCH = "file_organizer.cli.organize._check_setup_completed"


def _fake_check_setup() -> None:
    raise typer.Exit(code=1)


@pytest.fixture
def service() -> MagicMock:
    mock = MagicMock(spec=OrganizationService)
    mock.scan.return_value = OrganizationScan(Path("input"), (), {"text": 0})
    mock.preview.return_value = OrganizationResult(total_files=5)
    mock.execute.return_value = OrganizationResult(
        total_files=10, processed_files=8, skipped_files=1, failed_files=1
    )
    return mock


@pytest.fixture(autouse=True)
def _adapter_seams(service: MagicMock):
    with (
        patch(_SETUP_PATCH, return_value=True),
        patch("file_organizer.cli.organize._create_service", return_value=service),
    ):
        yield


def _roots(tmp_path: Path) -> tuple[Path, Path]:
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    return input_dir, output_dir


def _plan(input_dir: Path, output_dir: Path) -> OrganizationPlan:
    options = OrganizeOptions(recursive=False, transfer_mode="copy", methodology="para")
    return OrganizationPlan(
        plan_id="plan-1",
        schema_version=PLAN_SCHEMA_VERSION,
        input_path=str(input_dir.resolve()),
        output_path=str(output_dir.resolve()),
        created_at="2026-01-01T00:00:00Z",
        skip_existing=options.skip_existing,
        use_hardlinks=options.use_hardlinks,
        total_files=0,
        processed_files=0,
        skipped_files=0,
        failed_files=0,
        deduplicated_files=0,
        options=options,
    )


def test_organize_fails_when_setup_not_completed(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    with patch(_SETUP_PATCH, side_effect=_fake_check_setup):
        result = runner.invoke(app, ["organize", str(input_dir), str(output_dir)])
    assert result.exit_code == 1
    # The setup gate must block before any organization runs.
    service.execute.assert_not_called()
    service.preview.assert_not_called()


def test_organize_executes_through_application_service(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(app, ["organize", str(input_dir), str(output_dir)])
    assert result.exit_code == 0, result.output
    assert "8 processed" in result.output
    request, plan = service.execute.call_args.args
    assert plan is None
    assert request.input_path == input_dir.resolve()
    assert request.output_path == output_dir.resolve()
    assert request.options.transfer_mode == TransferMode.HARDLINK


@pytest.mark.parametrize("flag", ["--dry-run"])
def test_organize_dry_run_uses_preview(flag: str, service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(app, ["organize", str(input_dir), str(output_dir), flag])
    assert result.exit_code == 0, result.output
    service.preview.assert_called_once()
    service.execute.assert_not_called()
    assert "no files will be applied" in result.output


def test_all_behavior_flags_map_losslessly(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(
        app,
        [
            "organize",
            str(input_dir),
            str(output_dir),
            "--no-recursive",
            "--include-hidden",
            "--overwrite-existing",
            "--transfer-mode",
            "copy",
            "--methodology",
            "para",
            "--max-workers",
            "3",
            "--prefetch-depth",
            "1",
            "--no-vision",
            "--transcribe-audio",
            "--max-transcribe-seconds",
            "300",
            "--whisper-model",
            "small",
            "--text-model",
            "text-v1",
            "--vision-model",
            "vision-v1",
            "--text-provider",
            "openai",
            "--vision-provider",
            "claude",
        ],
    )
    assert result.exit_code == 0, result.output
    options = service.execute.call_args.args[0].options
    assert options.to_dict() == {
        "recursive": False,
        "include_hidden": True,
        "skip_existing": False,
        "transfer_mode": "copy",
        "methodology": "para",
        "enable_vision": False,
        "transcribe_audio": True,
        "max_transcribe_seconds": 300.0,
        "whisper_model": "small",
        "parallel_workers": 3,
        "prefetch_depth": 1,
        "text_model": "text-v1",
        "vision_model": "vision-v1",
        "text_provider": "openai",
        "vision_provider": "claude",
        "generate_tags": False,
        "tag_style": None,
        "tag_prompt": None,
    }


def test_compatibility_aliases_normalize(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(
        app,
        ["organize", str(input_dir), str(output_dir), "--text-only", "--no-prefetch"],
    )
    assert result.exit_code == 0, result.output
    options = service.execute.call_args.args[0].options
    assert options.enable_vision is False
    assert options.prefetch_depth == 0


def test_sequential_normalizes_workers_and_prefetch(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(app, ["organize", str(input_dir), str(output_dir), "--sequential"])
    assert result.exit_code == 0, result.output
    options = service.execute.call_args.args[0].options
    assert options.parallel_workers == 1
    assert options.prefetch_depth == 0


def test_incompatible_worker_flags_exit_two(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(
        app,
        ["organize", str(input_dir), str(output_dir), "--sequential", "--max-workers", "4"],
    )
    assert result.exit_code == 2
    assert "cannot be combined" in result.output
    service.execute.assert_not_called()


def test_incompatible_worker_flags_preserve_json_contract(
    service: MagicMock, tmp_path: Path
) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(
        app,
        [
            "organize",
            str(input_dir),
            str(output_dir),
            "--json",
            "--sequential",
            "--max-workers",
            "2",
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["outcome"] == "error"
    assert payload["error"]["code"] == "invalid_request"
    assert "--sequential cannot be combined" in payload["error"]["message"]
    service.execute.assert_not_called()


def test_invalid_canonical_option_is_usage_error(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(
        app, ["organize", str(input_dir), str(output_dir), "--transfer-mode", "move"]
    )
    assert result.exit_code == 2
    assert "not supported" in result.output
    service.execute.assert_not_called()


def test_preview_scans_and_previews_same_request(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(
        app,
        ["preview", str(input_dir), "--output-dir", str(output_dir), "--methodology", "jd"],
    )
    assert result.exit_code == 0, result.output
    scan_request = service.scan.call_args.args[0]
    preview_request = service.preview.call_args.args[0]
    assert scan_request == preview_request
    assert preview_request.options.methodology == OrganizationMethodology.JOHNNY_DECIMAL


def test_preview_keeps_legacy_single_path_invocation(service: MagicMock, tmp_path: Path) -> None:
    result = runner.invoke(app, ["preview", str(tmp_path)])
    assert result.exit_code == 0, result.output
    request = service.preview.call_args.args[0]
    assert request.input_path == request.output_path == tmp_path.resolve()


def test_json_output_is_stable_and_scriptable(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    result = runner.invoke(app, ["organize", str(input_dir), str(output_dir), "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema_version"] == 1
    assert payload["outcome"] == "ok"
    assert payload["mode"] == "execute"
    assert payload["request"]["options"]["transfer_mode"] == "hardlink"
    assert payload["result"]["processed_files"] == 8


def test_preview_saves_canonical_plan(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    plan = _plan(input_dir, output_dir)
    service.preview.return_value = OrganizationResult(plan=plan)
    plan_path = tmp_path / "review.json"
    result = runner.invoke(
        app,
        [
            "preview",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--save-plan",
            str(plan_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert OrganizationPlan.from_dict(json.loads(plan_path.read_text())) == plan


def test_organize_applies_serialized_plan_with_embedded_options(
    service: MagicMock, tmp_path: Path
) -> None:
    input_dir, output_dir = _roots(tmp_path)
    plan = _plan(input_dir, output_dir)
    plan_path = tmp_path / "review.json"
    plan_path.write_text(json.dumps(plan.to_dict()))
    result = runner.invoke(
        app,
        ["organize", str(input_dir), str(output_dir), "--plan", str(plan_path)],
    )
    assert result.exit_code == 0, result.output
    request, applied_plan = service.execute.call_args.args
    assert applied_plan == plan
    assert request.options == plan.options


def test_plan_overlays_only_explicit_behavior_fields(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    plan = _plan(input_dir, output_dir)
    plan_path = tmp_path / "review.json"
    plan_path.write_text(json.dumps(plan.to_dict()))
    result = runner.invoke(
        app,
        [
            "organize",
            str(input_dir),
            str(output_dir),
            "--plan",
            str(plan_path),
            "--recursive",
        ],
    )
    assert result.exit_code == 0, result.output
    request, _ = service.execute.call_args.args
    assert request.options.recursive is True
    assert request.options.transfer_mode == TransferMode.COPY
    assert request.options.methodology == OrganizationMethodology.PARA
    assert request.options.text_model == plan.options.text_model


def test_domain_errors_have_stable_json_and_exit_code(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    service.execute.side_effect = DomainError(
        DomainErrorCode.PLAN_MISMATCH, "reviewed plan no longer matches"
    )
    result = runner.invoke(app, ["organize", str(input_dir), str(output_dir), "--json"])
    assert result.exit_code == 3
    payload = json.loads(result.output)
    assert payload["outcome"] == "error"
    assert payload["error"] == {
        "code": "plan_mismatch",
        "message": "reviewed plan no longer matches",
        "retryable": False,
    }


def test_unexpected_errors_remain_actionable(service: MagicMock, tmp_path: Path) -> None:
    input_dir, output_dir = _roots(tmp_path)
    service.execute.side_effect = RuntimeError("Ollama not running")
    result = runner.invoke(app, ["organize", str(input_dir), str(output_dir)])
    assert result.exit_code == 1
    assert "Ollama not running" in result.output
