"""Unit tests for third-party integration adapters."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from file_organizer.integrations import (
    IntegrationConfig,
    IntegrationType,
    ObsidianIntegration,
    VSCodeIntegration,
    WorkflowIntegration,
)

pytestmark = pytest.mark.ci


def test_obsidian_integration_exports_file_and_note(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "source.txt"
    source.write_text("obsidian-content", encoding="utf-8")

    integration = ObsidianIntegration(
        IntegrationConfig(
            name="obsidian",
            integration_type=IntegrationType.DESKTOP_APP,
            settings={
                "vault_path": str(vault),
                "attachments_subdir": "Attachments",
                "notes_subdir": "Notes",
            },
        )
    )

    assert asyncio.run(integration.connect()) is True
    sent = asyncio.run(integration.send_file(str(source), metadata={"topic": "demo"}))
    assert sent is True

    copied = vault / "Attachments" / source.name
    note = vault / "Notes" / "source.md"
    assert copied.exists()
    assert note.exists()
    assert '"topic": "demo"' in note.read_text(encoding="utf-8")


def test_vscode_integration_writes_command_payload(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    command_output = tmp_path / "vscode.jsonl"
    source = workspace / "file.py"
    source.write_text("print('hello')\n", encoding="utf-8")

    integration = VSCodeIntegration(
        IntegrationConfig(
            name="vscode",
            integration_type=IntegrationType.EDITOR,
            settings={
                "workspace_path": str(workspace),
                "command_output_path": str(command_output),
            },
        )
    )

    assert asyncio.run(integration.connect()) is True
    sent = asyncio.run(integration.send_file(str(source), metadata={"origin": "test"}))
    assert sent is True

    lines = command_output.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["command"] == "vscode.open"
    assert payload["metadata"]["origin"] == "test"
    assert payload["uri"].startswith("vscode://file/")


def test_workflow_integration_generates_alfred_and_raycast_payloads(tmp_path: Path) -> None:
    output_dir = tmp_path / "workflow"
    source = tmp_path / "report.md"
    source.write_text("# report\n", encoding="utf-8")

    integration = WorkflowIntegration(
        IntegrationConfig(
            name="workflow",
            integration_type=IntegrationType.WORKFLOW,
            settings={"output_dir": str(output_dir)},
        )
    )

    assert asyncio.run(integration.connect()) is True
    sent = asyncio.run(integration.send_file(str(source), metadata={"summary": "Weekly report"}))
    assert sent is True

    alfred_files = sorted(output_dir.glob("alfred-*.json"))
    raycast_files = sorted(output_dir.glob("raycast-*.json"))
    assert alfred_files
    assert raycast_files

    alfred_payload = json.loads(alfred_files[0].read_text(encoding="utf-8"))
    assert alfred_payload["items"][0]["arg"].endswith("report.md")

    raycast_payload = json.loads(raycast_files[0].read_text(encoding="utf-8"))
    assert raycast_payload["metadata"]["summary"] == "Weekly report"
