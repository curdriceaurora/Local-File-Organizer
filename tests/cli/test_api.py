"""Tests for CLI API sub-commands."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from typer.testing import CliRunner

from file_organizer.cli.api import api_app
from file_organizer.client.exceptions import ClientError
from file_organizer.client.models import OrganizationOptionsPayload

runner = CliRunner()


@pytest.fixture
def mock_client_cls():
    """Mock the FileOrganizerClient class.

    Patches at the source module since the import is deferred inside _build_client()
    to reduce startup latency (Issue #472).
    """
    with patch("file_organizer.client.sync_client.FileOrganizerClient") as mock:
        yield mock


def test_health_command(mock_client_cls):
    """Test the health command success."""
    mock_instance = MagicMock()
    mock_instance.health.return_value = MagicMock(status="ok", version="1.0.0", environment="test")
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["health"])

    assert result.exit_code == 0
    assert "ok" in result.stdout
    assert "1.0.0" in result.stdout
    mock_instance.close.assert_called_once()


def test_health_command_json(mock_client_cls):
    """Test the health command JSON output."""
    mock_instance = MagicMock()
    mock_health = MagicMock()
    mock_health.model_dump.return_value = {"status": "ok", "version": "1.0.0"}
    mock_instance.health.return_value = mock_health
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["health", "--json"])

    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["schema_version"] == 1
    assert data["outcome"] == "ok"
    assert data["command"] == "api health"
    assert data["result"]["status"] == "ok"


def test_health_command_error(mock_client_cls):
    """Test health command handles errors."""
    mock_instance = MagicMock()
    mock_instance.health.side_effect = ClientError("Connection failed")
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["health"])

    assert result.exit_code == 1
    assert "Error:" in result.stdout
    assert "Connection failed" in result.stdout


def test_remote_capabilities_distinguish_commands_from_sdk_only_access():
    """Remote inventory must make unsupported fo api operations explicit."""
    result = runner.invoke(api_app, ["capabilities", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "ok"
    rows = {row["capability_id"]: row for row in payload["result"]}
    assert rows["organization.preview"]["availability"] == "available"
    assert "fo api preview" in rows["organization.preview"]["commands"]
    assert rows["deduplication.manage"]["availability"] == "sdk-only"
    assert rows["organization.preview"]["auth_gated"] is True


def test_login_command(mock_client_cls, tmp_path):
    """Test the login command success."""
    mock_instance = MagicMock()
    mock_tokens = MagicMock()
    mock_tokens.model_dump.return_value = {"access_token": "abc", "refresh_token": "def"}
    mock_instance.login.return_value = mock_tokens
    mock_client_cls.return_value = mock_instance

    token_file = tmp_path / "token.json"

    result = runner.invoke(
        api_app, ["login", "--save-token", str(token_file)], input="user\npass\n"
    )

    assert result.exit_code == 0
    assert "Login successful" in result.stdout
    mock_instance.login.assert_called_once_with("user", "pass")

    assert token_file.exists()
    saved = json.loads(token_file.read_text())
    assert saved["access_token"] == "abc"


def test_login_command_error(mock_client_cls):
    """Test the login command failure."""
    mock_instance = MagicMock()
    mock_instance.login.side_effect = ClientError("Invalid credentials")
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["login"], input="user\npass\n")

    assert result.exit_code == 1
    assert "Error:" in result.stdout


def test_me_command(mock_client_cls):
    """Test the me command."""
    mock_instance = MagicMock()
    mock_instance.me.return_value = MagicMock(
        username="admin", email="admin@test.com", is_admin=True
    )
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["me", "--token", "abc"])

    assert result.exit_code == 0
    assert "User: admin" in result.stdout
    assert "admin@test.com" in result.stdout


def test_logout_command(mock_client_cls):
    """Test the logout command."""
    mock_instance = MagicMock()
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["logout", "--token", "abc", "--refresh-token", "def"])

    assert result.exit_code == 0
    assert "Logout successful" in result.stdout
    mock_instance.logout.assert_called_once_with("def")


def test_files_list_command(mock_client_cls):
    """Test the files list command."""
    mock_instance = MagicMock()

    # Mock items
    item1 = MagicMock(name="f1.txt", file_type="file", size=100)
    item1.name = "f1.txt"  # Need to set explicitly due to MagicMock behavior

    result_obj = MagicMock(total=1, items=[item1])
    mock_instance.list_files.return_value = result_obj
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["files", ".", "--token", "abc"])

    assert result.exit_code == 0
    assert "Files (1)" in result.stdout
    assert "f1.txt" in result.stdout

    mock_instance.list_files.assert_called_once_with(
        ".", recursive=False, include_hidden=False, limit=100
    )


def test_system_status_command(mock_client_cls):
    """Test system status command."""
    mock_instance = MagicMock()
    mock_instance.system_status.return_value = MagicMock(
        disk_free="10GB", disk_used="90GB", active_jobs=5
    )
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["system-status", ".", "--token", "abc"])

    assert result.exit_code == 0
    assert "10GB" in result.stdout
    assert "5" in result.stdout


def test_system_stats_command(mock_client_cls):
    """Test system stats command."""
    mock_instance = MagicMock()
    mock_instance.system_stats.return_value = MagicMock(
        file_count=100, directory_count=10, total_size="1MB"
    )
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["system-stats", ".", "--token", "abc"])

    assert result.exit_code == 0
    assert "100" in result.stdout
    assert "1MB" in result.stdout


def test_remote_scan_maps_traversal_and_emits_machine_json(mock_client_cls):
    """Remote scan must preserve traversal flags through the official SDK."""
    mock_instance = MagicMock()
    response = MagicMock(total_files=2, counts={"text": 2})
    response.model_dump.return_value = {
        "input_dir": "/remote/input",
        "total_files": 2,
        "files": ["/remote/input/a.txt", "/remote/input/b.txt"],
        "counts": {"text": 2},
    }
    mock_instance.scan.return_value = response
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(
        api_app,
        ["scan", "/remote/input", "--no-recursive", "--include-hidden", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "ok"
    assert payload["scan"]["total_files"] == 2
    assert payload["request"]["options"] == {
        "include_hidden": True,
        "recursive": False,
    }
    mock_instance.scan.assert_called_once_with(
        "/remote/input", recursive=False, include_hidden=True
    )


def test_remote_preview_maps_complete_canonical_options(mock_client_cls):
    """Remote preview must pass every behavior option as one SDK payload."""
    mock_instance = MagicMock()
    response = MagicMock(total_files=1, plan=None)
    response.model_dump.return_value = {"total_files": 1, "plan": None}
    mock_instance.preview_organize.return_value = response
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(
        api_app,
        [
            "preview",
            "/remote/input",
            "/remote/output",
            "--no-recursive",
            "--include-hidden",
            "--overwrite-existing",
            "--transfer-mode",
            "copy",
            "--methodology",
            "para",
            "--no-vision",
            "--transcribe-audio",
            "--max-transcribe-seconds",
            "0",
            "--whisper-model",
            "small",
            "--sequential",
            "--no-prefetch",
            "--text-model",
            "text-model",
            "--vision-model",
            "vision-model",
            "--text-provider",
            "ollama",
            "--vision-provider",
            "openai",
            "--json",
        ],
    )

    assert result.exit_code == 0
    options = mock_instance.preview_organize.call_args.kwargs["options"]
    assert options.model_dump() == {
        "recursive": False,
        "include_hidden": True,
        "skip_existing": False,
        "transfer_mode": "copy",
        "methodology": "para",
        "enable_vision": False,
        "transcribe_audio": True,
        "max_transcribe_seconds": None,
        "whisper_model": "small",
        "parallel_workers": 1,
        "prefetch_depth": 0,
        "text_model": "text-model",
        "vision_model": "vision-model",
        "text_provider": "ollama",
        "vision_provider": "openai",
    }


def test_remote_organize_applies_reviewed_plan_without_default_overrides(mock_client_cls, tmp_path):
    """A plan-only invocation must let the server resolve the reviewed options."""
    mock_instance = MagicMock()
    response = MagicMock(job_id="job-1", result=None, status="queued")
    response.model_dump.return_value = {"status": "queued", "job_id": "job-1"}
    mock_instance.organize.return_value = response
    mock_client_cls.return_value = mock_instance
    plan = object()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")

    with patch("file_organizer.cli.api._load_remote_plan", return_value=plan):
        result = runner.invoke(
            api_app,
            [
                "organize",
                "/remote/input",
                "/remote/output",
                "--plan",
                str(plan_path),
                "--json",
            ],
        )

    assert result.exit_code == 0
    mock_instance.organize.assert_called_once_with(
        "/remote/input",
        "/remote/output",
        options=None,
        plan=plan,
        run_in_background=True,
        idempotency_key=None,
    )
    payload = json.loads(result.stdout)
    assert payload["result"] is None
    assert payload["job"] == {"job_id": "job-1", "status": "queued"}


def test_remote_plan_overlays_only_explicit_behavior_flags(mock_client_cls, tmp_path):
    """Explicit remote flags must preserve every unspecified reviewed-plan option."""
    mock_instance = MagicMock()
    response = MagicMock(job_id="job-1", result=None, status="queued")
    response.model_dump.return_value = {"status": "queued", "job_id": "job-1"}
    mock_instance.organize.return_value = response
    mock_client_cls.return_value = mock_instance
    reviewed_options = OrganizationOptionsPayload(
        recursive=False,
        include_hidden=True,
        skip_existing=False,
        transfer_mode="copy",
        methodology="para",
        enable_vision=False,
        parallel_workers=3,
        prefetch_depth=7,
    )
    plan = MagicMock(options=reviewed_options)
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("{}", encoding="utf-8")

    with patch("file_organizer.cli.api._load_remote_plan", return_value=plan):
        result = runner.invoke(
            api_app,
            [
                "organize",
                "/remote/input",
                "/remote/output",
                "--plan",
                str(plan_path),
                "--methodology",
                "jd",
                "--json",
            ],
        )

    assert result.exit_code == 0
    options = mock_instance.organize.call_args.kwargs["options"]
    assert options.model_dump() == {
        **reviewed_options.model_dump(),
        "methodology": "jd",
    }


def test_remote_foreground_reserves_result_for_operation_result(mock_client_cls):
    """Foreground and queued responses must keep stable result and job slots."""
    mock_instance = MagicMock()
    operation_result = MagicMock(processed_files=3, skipped_files=0, failed_files=0)
    response = MagicMock(job_id=None, result=operation_result, status="completed")
    response.model_dump.return_value = {
        "status": "completed",
        "job_id": None,
        "result": {"processed_files": 3, "plan": None},
    }
    mock_instance.organize.return_value = response
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(
        api_app,
        ["organize", "/remote/input", "/remote/output", "--foreground", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["result"] == {"processed_files": 3}
    assert payload["job"] is None


@pytest.mark.parametrize(
    ("command", "method"),
    [("cancel", "cancel_job"), ("rollback", "rollback_job")],
)
def test_remote_job_mutations_preserve_revision_guard(mock_client_cls, command, method):
    """Remote lifecycle mutations must forward optimistic revision guards."""
    mock_instance = MagicMock()
    job = MagicMock(job_id="job-1", status="cancelled", revision=4)
    job.model_dump.return_value = {"job_id": "job-1", "status": job.status, "revision": 4}
    getattr(mock_instance, method).return_value = job
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(
        api_app,
        [command, "job-1", "--expected-revision", "3", "--json"],
    )

    assert result.exit_code == 0
    getattr(mock_instance, method).assert_called_once_with("job-1", expected_revision=3)


def test_remote_jobs_wraps_list_in_shared_success_envelope(mock_client_cls):
    """List-valued results must not replace the versioned top-level JSON object."""
    mock_instance = MagicMock()
    job = MagicMock()
    job.model_dump.return_value = {"job_id": "job-1", "status": "queued"}
    mock_instance.list_jobs.return_value = [job]
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["jobs", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "ok"
    assert payload["command"] == "api jobs"
    assert payload["result"] == [{"job_id": "job-1", "status": "queued"}]


def test_remote_json_error_preserves_sdk_auth_evidence(mock_client_cls):
    """Machine output must distinguish authentication failures from local-only gaps."""
    mock_instance = MagicMock()
    mock_instance.scan.side_effect = ClientError(
        "Unauthorized",
        status_code=401,
        detail="Authentication required.",
        error_code="unauthorized",
    )
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["scan", "/remote/input", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "command": "api scan",
        "error": {
            "code": "unauthorized",
            "details": {},
            "message": "Authentication required.",
            "retryable": False,
        },
        "outcome": "error",
        "schema_version": 1,
    }


def test_remote_preview_invalid_options_preserve_json_contract(mock_client_cls):
    """Local option validation must not replace JSON output with a usage banner."""
    mock_client_cls.return_value = MagicMock()

    result = runner.invoke(
        api_app,
        [
            "preview",
            "/remote/input",
            "/remote/output",
            "--methodology",
            "invented",
            "--json",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["outcome"] == "error"
    assert payload["command"] == "api preview"
    assert payload["error"]["code"] == "invalid_request"
    assert payload["error"]["retryable"] is False


def test_health_transport_failure_preserves_json_contract(mock_client_cls):
    """Connection failures must emit one retryable machine-readable error."""
    mock_instance = MagicMock()
    request = httpx.Request("GET", "http://127.0.0.1:9/api/v1/health")
    mock_instance.health.side_effect = httpx.ConnectError("Connection refused", request=request)
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["health", "--json"])

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "command": "api health",
        "error": {
            "code": "transport_error",
            "details": {"error_type": "ConnectError"},
            "message": "Connection refused",
            "retryable": True,
        },
        "outcome": "error",
        "schema_version": 1,
    }


@pytest.mark.parametrize(
    ("status_code", "error_code", "expected_exit"),
    [(404, "not_found", 2), (422, "validation_error", 2), (409, "plan_mismatch", 3)],
)
def test_remote_errors_share_local_exit_categories(
    mock_client_cls, status_code, error_code, expected_exit
):
    """Remote domain failures must use the local CLI's documented exit categories."""
    mock_instance = MagicMock()
    mock_instance.scan.side_effect = ClientError(
        "Request failed",
        status_code=status_code,
        detail="Request failed",
        error_code=error_code,
    )
    mock_client_cls.return_value = mock_instance

    result = runner.invoke(api_app, ["scan", "/remote/input", "--json"])

    assert result.exit_code == expected_exit
    assert json.loads(result.stdout)["error"]["code"] == error_code


def _make_special_file(target: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a special file (FIFO if supported) or simulate one with is_file() -> False."""
    if hasattr(os, "mkfifo"):
        try:
            os.mkfifo(target)
            return target
        except OSError:
            pass
    target.touch()
    orig_is_file = Path.is_file
    monkeypatch.setattr(
        Path,
        "is_file",
        lambda self: False if self == target.resolve() else orig_is_file(self),
    )
    return target


@pytest.mark.parametrize("as_json", [False, True])
def test_remote_preview_save_plan_rejects_existing_directory(
    mock_client_cls, tmp_path: Path, as_json: bool
) -> None:
    """Remote preview must reject an existing directory passed to --save-plan."""
    mock_client_cls.return_value = MagicMock()
    plan_dir = tmp_path / "plan_dir"
    plan_dir.mkdir()

    args = ["preview", "/remote/input", "/remote/output", "--save-plan", str(plan_dir)]
    if as_json:
        args.append("--json")

    result = runner.invoke(api_app, args)

    assert result.exit_code == 2
    if as_json:
        payload = json.loads(result.stdout)
        assert payload["outcome"] == "error"
        assert payload["command"] == "api preview"
        assert payload["error"]["code"] == "invalid_request"
        assert "Save plan output path is not a regular file" in payload["error"]["message"]
    else:
        assert "Save plan output path is not a regular file" in result.output


@pytest.mark.parametrize("as_json", [False, True])
def test_remote_preview_save_plan_rejects_special_file(
    mock_client_cls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_json: bool
) -> None:
    """Remote preview must reject a special file (e.g. FIFO) passed to --save-plan."""
    mock_client_cls.return_value = MagicMock()
    special = _make_special_file(tmp_path / "plan_fifo", monkeypatch)

    args = ["preview", "/remote/input", "/remote/output", "--save-plan", str(special)]
    if as_json:
        args.append("--json")

    result = runner.invoke(api_app, args)

    assert result.exit_code == 2
    if as_json:
        payload = json.loads(result.stdout)
        assert payload["outcome"] == "error"
        assert payload["command"] == "api preview"
        assert payload["error"]["code"] == "invalid_request"
        assert "Save plan output path is not a regular file" in payload["error"]["message"]
    else:
        assert "Save plan output path is not a regular file" in result.output


@pytest.mark.parametrize("as_json", [False, True])
def test_remote_organize_plan_rejects_existing_directory(
    mock_client_cls, tmp_path: Path, as_json: bool
) -> None:
    """Remote organize must reject an existing directory passed to --plan."""
    mock_client_cls.return_value = MagicMock()
    plan_dir = tmp_path / "plan_dir"
    plan_dir.mkdir()

    args = ["organize", "/remote/input", "/remote/output", "--plan", str(plan_dir)]
    if as_json:
        args.append("--json")

    result = runner.invoke(api_app, args)

    assert result.exit_code == 2
    if as_json:
        payload = json.loads(result.stdout)
        assert payload["outcome"] == "error"
        assert payload["command"] == "api organize"
        assert payload["error"]["code"] == "invalid_request"
        assert "Plan path is not a regular file" in payload["error"]["message"]
    else:
        assert "Plan path is not a regular file" in result.output


@pytest.mark.parametrize("as_json", [False, True])
def test_remote_organize_plan_rejects_special_file(
    mock_client_cls, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, as_json: bool
) -> None:
    """Remote organize must reject a special file (e.g. FIFO) passed to --plan."""
    mock_client_cls.return_value = MagicMock()
    special = _make_special_file(tmp_path / "plan_fifo", monkeypatch)

    args = ["organize", "/remote/input", "/remote/output", "--plan", str(special)]
    if as_json:
        args.append("--json")

    result = runner.invoke(api_app, args)

    assert result.exit_code == 2
    if as_json:
        payload = json.loads(result.stdout)
        assert payload["outcome"] == "error"
        assert payload["command"] == "api organize"
        assert payload["error"]["code"] == "invalid_request"
        assert "Plan path is not a regular file" in payload["error"]["message"]
    else:
        assert "Plan path is not a regular file" in result.output
