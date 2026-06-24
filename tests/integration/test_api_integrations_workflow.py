"""Integration coverage for API integrations workflows."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_current_active_user, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.integrations import router
from file_organizer.integrations import IntegrationConfig, IntegrationType, ObsidianIntegration

pytestmark = pytest.mark.integration


@pytest.fixture()
def integrations_settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        environment="test",
        auth_enabled=False,
        allowed_paths=[str(tmp_path)],
    )


@pytest.fixture()
def integrations_client(
    tmp_path: Path,
    integrations_settings: ApiSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    vault = tmp_path / "vault"
    vault.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    monkeypatch.setenv("FO_OBSIDIAN_VAULT_PATH", str(vault))
    monkeypatch.setenv("FO_VSCODE_WORKSPACE_PATH", str(workspace))
    monkeypatch.setenv("FO_WORKFLOW_OUTPUT_PATH", str(tmp_path / "workflow"))
    monkeypatch.setenv("FO_VSCODE_COMMAND_PATH", str(tmp_path / "vscode.jsonl"))

    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: integrations_settings
    app.dependency_overrides[get_current_active_user] = lambda: MagicMock(
        is_active=True,
        is_admin=True,
        username="integration-admin",
    )
    app.include_router(router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False)


def test_full_integrations_workflow(integrations_client: TestClient, tmp_path: Path) -> None:
    source = tmp_path / "report.txt"
    source.write_text("Quarterly integration export", encoding="utf-8")

    listed = integrations_client.get("/api/v1/integrations")
    assert listed.status_code == 200
    items = {item["name"]: item for item in listed.json()["items"]}
    assert {"obsidian", "vscode", "workflow"} <= set(items)
    assert items["obsidian"]["details"]["vault_exists"] is True

    obsidian_settings = {
        "settings": {
            "vault_path": str(tmp_path / "vault"),
            "attachments_subdir": "Attachments",
            "notes_subdir": "Notes",
        }
    }
    updated = integrations_client.post(
        "/api/v1/integrations/obsidian/settings",
        json=obsidian_settings,
    )
    assert updated.status_code == 200
    assert updated.json()["integration"] == "obsidian"

    connected = integrations_client.post("/api/v1/integrations/obsidian/connect")
    assert connected.status_code == 200
    assert connected.json()["connected"] is True

    sent = integrations_client.post(
        "/api/v1/integrations/obsidian/send",
        json={"path": str(source), "metadata": {"summary": "Q4 report"}},
    )
    assert sent.status_code == 200
    assert sent.json()["sent"] is True
    attachment = tmp_path / "vault" / "Attachments" / source.name
    note = tmp_path / "vault" / "Notes" / "report.md"
    assert attachment.exists()
    assert note.exists()
    assert "Q4 report" in note.read_text(encoding="utf-8")

    disconnected = integrations_client.post("/api/v1/integrations/obsidian/disconnect")
    assert disconnected.status_code == 200
    assert disconnected.json()["connected"] is False

    vscode_updated = integrations_client.post(
        "/api/v1/integrations/vscode/settings",
        json={"settings": {"command_output_path": "commands.jsonl"}},
    )
    assert vscode_updated.status_code == 200

    vscode_sent = integrations_client.post(
        "/api/v1/integrations/vscode/send",
        json={"path": str(source), "metadata": {"source": "integration-test"}},
    )
    assert vscode_sent.status_code == 200
    command_output = tmp_path / "commands.jsonl"
    assert command_output.exists()
    command_payload = json.loads(command_output.read_text(encoding="utf-8").strip())
    assert command_payload["command"] == "vscode.open"
    assert command_payload["metadata"]["source"] == "integration-test"

    workflow_updated = integrations_client.post(
        "/api/v1/integrations/workflow/settings",
        json={"settings": {"output_dir": str(tmp_path / "workflow-out")}},
    )
    assert workflow_updated.status_code == 200

    workflow_sent = integrations_client.post(
        "/api/v1/integrations/workflow/send",
        json={"path": str(source), "metadata": {"summary": "launcher export"}},
    )
    assert workflow_sent.status_code == 200
    workflow_dir = tmp_path / "workflow-out"
    exports = sorted(workflow_dir.glob("*.json"))
    assert len(exports) == 2
    exported_names = {path.name.split("-", 1)[0] for path in exports}
    assert exported_names == {"alfred", "raycast"}


def test_browser_token_flow_and_validation_errors(
    integrations_client: TestClient,
) -> None:
    config_resp = integrations_client.get("/api/v1/integrations/browser/config")
    assert config_resp.status_code == 200
    assert config_resp.json()["token_ttl_seconds"] == 3600

    issue = integrations_client.post(
        "/api/v1/integrations/browser/token",
        json={"extension_id": "browser-extension-1"},
    )
    assert issue.status_code == 200
    token = issue.json()["token"]

    verified = integrations_client.post(
        "/api/v1/integrations/browser/verify",
        json={"token": token},
    )
    assert verified.status_code == 200
    assert verified.json() == {"valid": True}

    invalid_verify = integrations_client.post(
        "/api/v1/integrations/browser/verify",
        json={"token": "invalid-token"},
    )
    assert invalid_verify.status_code == 200
    assert invalid_verify.json() == {"valid": False}


def test_integrations_reject_invalid_paths_and_names(
    integrations_client: TestClient,
) -> None:
    forbidden = integrations_client.post(
        "/api/v1/integrations/obsidian/settings",
        json={"settings": {"vault_path": "/etc"}},
    )
    assert forbidden.status_code == 403

    invalid_name = integrations_client.post(
        "/api/v1/integrations/vscode/settings",
        json={"settings": {"command_output_path": "../escape.jsonl"}},
    )
    assert invalid_name.status_code == 403
    assert invalid_name.json()["error"] == "path_not_allowed"

    missing_integration = integrations_client.post(
        "/api/v1/integrations/unknown/connect",
    )
    assert missing_integration.status_code == 404


def test_integrations_settings_reject_invalid_filename_in_command_output_path(
    integrations_client: TestClient, tmp_path: Path
) -> None:
    invalid_filename = integrations_client.post(
        "/api/v1/integrations/vscode/settings",
        json={"settings": {"command_output_path": str(tmp_path) + "/.."}},
    )
    assert invalid_filename.status_code == 400
    assert invalid_filename.json()["error"] == "invalid_filename"


@pytest.mark.parametrize(
    ("subdir_value", "message_fragment"),
    [
        (123, "must be a string"),
        ("   ", "cannot be empty"),
        ("a//b", "empty path segments"),
        ("a\\\\b", "empty path segments"),
        ("C:\\folder", "must be a relative path"),
        ("../escape", "path traversal"),
    ],
)
def test_integrations_settings_reject_invalid_subdir_values(
    integrations_client: TestClient,
    subdir_value: object,
    message_fragment: str,
) -> None:
    response = integrations_client.post(
        "/api/v1/integrations/obsidian/settings",
        json={"settings": {"attachments_subdir": subdir_value}},
    )
    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "invalid_settings"
    assert message_fragment in body["message"]


# ---------------------------------------------------------------------------
# ObsidianIntegration adapter — auth and path-validation branch coverage
# ---------------------------------------------------------------------------


def _obsidian_integration(vault: Path, **subdir_overrides: str) -> ObsidianIntegration:
    settings: dict[str, object] = {
        "vault_path": str(vault),
        "attachments_subdir": "Attachments",
        "notes_subdir": "Notes",
    }
    settings.update(subdir_overrides)
    return ObsidianIntegration(
        IntegrationConfig(
            name="obsidian",
            integration_type=IntegrationType.EDITOR,
            settings=settings,
        )
    )


class TestObsidianIntegrationBranches:
    def test_init_coerces_integration_type_to_desktop_app(self, tmp_path: Path) -> None:
        integration = _obsidian_integration(tmp_path / "vault")
        assert integration.config.integration_type is IntegrationType.DESKTOP_APP

    def test_validate_auth_none_returns_true(self, tmp_path: Path) -> None:
        integration = _obsidian_integration(tmp_path / "vault")
        integration.config.auth_method = "none"
        assert asyncio.run(integration.validate_auth()) is True

    def test_validate_auth_api_key_present_returns_true(self, tmp_path: Path) -> None:
        integration = _obsidian_integration(tmp_path / "vault")
        integration.config.auth_method = "api_key"
        integration.config.settings["api_key"] = "secret-key"
        assert asyncio.run(integration.validate_auth()) is True

    def test_validate_auth_api_key_missing_returns_false(self, tmp_path: Path) -> None:
        integration = _obsidian_integration(tmp_path / "vault")
        integration.config.auth_method = "api_key"
        assert asyncio.run(integration.validate_auth()) is False

    def test_validate_auth_unsupported_method_returns_false(self, tmp_path: Path) -> None:
        integration = _obsidian_integration(tmp_path / "vault")
        integration.config.auth_method = "oauth"
        assert asyncio.run(integration.validate_auth()) is False

    def test_send_file_returns_false_when_vault_missing(self, tmp_path: Path) -> None:
        source = tmp_path / "source.txt"
        source.write_text("content", encoding="utf-8")
        integration = _obsidian_integration(tmp_path / "missing-vault")
        assert asyncio.run(integration.send_file(str(source))) is False

    def test_send_file_returns_false_when_auth_fails(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        source = tmp_path / "source.txt"
        source.write_text("content", encoding="utf-8")
        integration = _obsidian_integration(vault)
        integration.config.auth_method = "api_key"
        assert asyncio.run(integration.send_file(str(source))) is False

    def test_send_file_returns_false_when_source_missing(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        integration = _obsidian_integration(vault)
        assert asyncio.run(integration.send_file(str(tmp_path / "nope.txt"))) is False

    @pytest.mark.parametrize(
        "subdir_overrides",
        [
            {"attachments_subdir": ""},
            {"attachments_subdir": "a//b"},
            {"attachments_subdir": "a\\\\b"},
            {"attachments_subdir": "../escape"},
        ],
    )
    def test_send_file_rejects_invalid_attachments_subdir(
        self, tmp_path: Path, subdir_overrides: dict[str, str]
    ) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        source = tmp_path / "source.txt"
        source.write_text("content", encoding="utf-8")
        integration = _obsidian_integration(vault, **subdir_overrides)
        assert asyncio.run(integration.send_file(str(source))) is False

    def test_send_file_rejects_attachments_dir_escaping_vault(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (vault / "Attachments").symlink_to(outside, target_is_directory=True)
        source = tmp_path / "source.txt"
        source.write_text("content", encoding="utf-8")
        integration = _obsidian_integration(vault)
        assert asyncio.run(integration.send_file(str(source))) is False

    def test_send_file_rejects_destination_escaping_vault(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        attachments = vault / "Attachments"
        attachments.mkdir(parents=True)
        outside = tmp_path / "outside.txt"
        outside.write_text("outside-content", encoding="utf-8")
        source = tmp_path / "source.txt"
        source.write_text("content", encoding="utf-8")
        (attachments / source.name).symlink_to(outside)
        integration = _obsidian_integration(vault)
        assert asyncio.run(integration.send_file(str(source))) is False

    def test_send_file_rejects_notes_dir_escaping_vault(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        vault.mkdir()
        outside = tmp_path / "outside"
        outside.mkdir()
        (vault / "Notes").symlink_to(outside, target_is_directory=True)
        source = tmp_path / "source.txt"
        source.write_text("content", encoding="utf-8")
        integration = _obsidian_integration(vault)
        assert asyncio.run(integration.send_file(str(source))) is False

    def test_send_file_rejects_note_path_escaping_vault(self, tmp_path: Path) -> None:
        vault = tmp_path / "vault"
        notes = vault / "Notes"
        notes.mkdir(parents=True)
        outside = tmp_path / "outside.md"
        outside.write_text("outside-note", encoding="utf-8")
        source = tmp_path / "source.txt"
        source.write_text("content", encoding="utf-8")
        (notes / f"{source.stem}.md").symlink_to(outside)
        integration = _obsidian_integration(vault)
        assert asyncio.run(integration.send_file(str(source))) is False
