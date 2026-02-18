"""API tests for integration framework endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest

from file_organizer.api.test_utils import create_auth_client

pytestmark = pytest.mark.ci


def _client(tmp_path: Path) -> tuple[object, dict[str, str], Path, Path]:
    allowed_root = tmp_path / "allowed"
    allowed_root.mkdir()
    outside_root = tmp_path / "outside"
    outside_root.mkdir()
    client, headers, _ = create_auth_client(tmp_path, [str(allowed_root)])
    return client, headers, allowed_root, outside_root


def test_list_integrations_and_connect(tmp_path: Path) -> None:
    client, headers, allowed_root, _ = _client(tmp_path)

    listing = client.get("/api/v1/integrations", headers=headers)
    assert listing.status_code == 200
    names = {item["name"] for item in listing.json()["items"]}
    assert {"obsidian", "vscode", "workflow"}.issubset(names)

    vault = allowed_root / "vault"
    vault.mkdir()
    update = client.post(
        "/api/v1/integrations/obsidian/settings",
        json={"settings": {"vault_path": str(vault), "notes_subdir": "Notes"}},
        headers=headers,
    )
    assert update.status_code == 200

    connect = client.post("/api/v1/integrations/obsidian/connect", headers=headers)
    assert connect.status_code == 200
    assert connect.json()["connected"] is True


def test_send_file_to_obsidian_and_workflow(tmp_path: Path) -> None:
    client, headers, allowed_root, _ = _client(tmp_path)
    vault = allowed_root / "vault"
    vault.mkdir()
    source = allowed_root / "input.txt"
    source.write_text("payload", encoding="utf-8")

    obsidian_settings = client.post(
        "/api/v1/integrations/obsidian/settings",
        json={
            "settings": {
                "vault_path": str(vault),
                "attachments_subdir": "Attachments",
                "notes_subdir": "Notes",
            }
        },
        headers=headers,
    )
    assert obsidian_settings.status_code == 200

    obsidian_send = client.post(
        "/api/v1/integrations/obsidian/send",
        json={"path": str(source), "metadata": {"origin": "api-test"}},
        headers=headers,
    )
    assert obsidian_send.status_code == 200
    assert obsidian_send.json()["sent"] is True
    assert (vault / "Attachments" / "input.txt").exists()

    workflow_output = allowed_root / "workflow"
    workflow_settings = client.post(
        "/api/v1/integrations/workflow/settings",
        json={"settings": {"output_dir": str(workflow_output)}},
        headers=headers,
    )
    assert workflow_settings.status_code == 200

    workflow_send = client.post(
        "/api/v1/integrations/workflow/send",
        json={"path": str(source), "metadata": {"summary": "from-api"}},
        headers=headers,
    )
    assert workflow_send.status_code == 200
    assert workflow_send.json()["sent"] is True
    assert list(workflow_output.glob("*.json"))


def test_send_file_rejects_disallowed_paths(tmp_path: Path) -> None:
    client, headers, _, outside_root = _client(tmp_path)
    outside_file = outside_root / "blocked.txt"
    outside_file.write_text("blocked", encoding="utf-8")

    response = client.post(
        "/api/v1/integrations/vscode/send",
        json={"path": str(outside_file), "metadata": {}},
        headers=headers,
    )
    assert response.status_code == 403
    assert response.json()["error"] == "path_not_allowed"


def test_browser_extension_token_issue_and_verify(tmp_path: Path) -> None:
    client, headers, _, _ = _client(tmp_path)

    config = client.get("/api/v1/integrations/browser/config", headers=headers)
    assert config.status_code == 200
    assert config.json()["token_ttl_seconds"] > 0

    issue = client.post(
        "/api/v1/integrations/browser/token",
        json={"extension_id": "com.local.file-organizer"},
        headers=headers,
    )
    assert issue.status_code == 200
    token = issue.json()["token"]

    verify = client.post(
        "/api/v1/integrations/browser/verify",
        json={"token": token},
        headers=headers,
    )
    assert verify.status_code == 200
    assert verify.json()["valid"] is True


def test_unknown_integration_returns_404(tmp_path: Path) -> None:
    client, headers, _, _ = _client(tmp_path)

    connect = client.post("/api/v1/integrations/not-real/connect", headers=headers)
    assert connect.status_code == 404

    settings = client.post(
        "/api/v1/integrations/not-real/settings",
        json={"settings": {}},
        headers=headers,
    )
    assert settings.status_code == 404
    assert settings.json()["error"] == "not_found"


def test_vscode_settings_normalize_bare_command_output_path(tmp_path: Path) -> None:
    client, headers, allowed_root, _ = _client(tmp_path)
    workspace = allowed_root / "workspace"
    workspace.mkdir()
    source = workspace / "main.py"
    source.write_text("print('ok')\n", encoding="utf-8")

    update = client.post(
        "/api/v1/integrations/vscode/settings",
        json={
            "settings": {"workspace_path": str(workspace), "command_output_path": "commands.jsonl"}
        },
        headers=headers,
    )
    assert update.status_code == 200

    send = client.post(
        "/api/v1/integrations/vscode/send",
        json={"path": str(source), "metadata": {"origin": "api-test"}},
        headers=headers,
    )
    assert send.status_code == 200
    assert (allowed_root / "commands.jsonl").exists()
