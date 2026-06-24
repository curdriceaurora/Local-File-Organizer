"""Unit tests for third-party integration adapters."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path

import pytest
import yaml

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
    note_content = note.read_text(encoding="utf-8")
    _, frontmatter_raw, _ = note_content.split("---", 2)
    frontmatter = yaml.safe_load(frontmatter_raw)
    assert frontmatter["metadata"]["topic"] == "demo"


def _obsidian_integration(vault: Path, **subdir_overrides: str) -> ObsidianIntegration:
    settings = {
        "vault_path": str(vault),
        "attachments_subdir": "Attachments",
        "notes_subdir": "Notes",
    }
    settings.update(subdir_overrides)
    return ObsidianIntegration(
        IntegrationConfig(
            name="obsidian",
            integration_type=IntegrationType.DESKTOP_APP,
            settings=settings,
        )
    )


@pytest.mark.parametrize(
    "subdir_overrides",
    [
        {"attachments_subdir": ""},
        {"attachments_subdir": "a//b"},
        {"attachments_subdir": "a\\\\b"},
        {"attachments_subdir": "../escape"},
    ],
)
def test_obsidian_send_file_rejects_invalid_attachments_subdir(
    tmp_path: Path, subdir_overrides: dict[str, str]
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")

    integration = _obsidian_integration(vault, **subdir_overrides)
    assert asyncio.run(integration.connect()) is True
    assert asyncio.run(integration.send_file(str(source))) is False


def test_obsidian_send_file_rejects_attachments_dir_escaping_vault(tmp_path: Path) -> None:
    """A symlinked attachments subdir pointing outside the vault must be rejected."""
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault / "Attachments").symlink_to(outside, target_is_directory=True)
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")

    integration = _obsidian_integration(vault)
    assert asyncio.run(integration.connect()) is True
    assert asyncio.run(integration.send_file(str(source))) is False


def test_obsidian_send_file_rejects_destination_escaping_vault(tmp_path: Path) -> None:
    """An existing symlink at the destination filename must not be followed outside the vault."""
    vault = tmp_path / "vault"
    attachments = vault / "Attachments"
    attachments.mkdir(parents=True)
    outside = tmp_path / "outside.txt"
    outside.write_text("outside-content", encoding="utf-8")
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    (attachments / source.name).symlink_to(outside)

    integration = _obsidian_integration(vault)
    assert asyncio.run(integration.connect()) is True
    assert asyncio.run(integration.send_file(str(source))) is False


def test_obsidian_send_file_rejects_notes_dir_escaping_vault(tmp_path: Path) -> None:
    """A symlinked notes subdir pointing outside the vault must be rejected."""
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (vault / "Notes").symlink_to(outside, target_is_directory=True)
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")

    integration = _obsidian_integration(vault)
    assert asyncio.run(integration.connect()) is True
    assert asyncio.run(integration.send_file(str(source))) is False
    assert not (vault / "Attachments" / source.name).exists()


def test_obsidian_send_file_rejects_note_path_escaping_vault(tmp_path: Path) -> None:
    """An existing symlink at the note filename must not be followed outside the vault."""
    vault = tmp_path / "vault"
    notes = vault / "Notes"
    notes.mkdir(parents=True)
    outside = tmp_path / "outside.md"
    outside.write_text("outside-note", encoding="utf-8")
    source = tmp_path / "source.txt"
    source.write_text("content", encoding="utf-8")
    (notes / f"{source.stem}.md").symlink_to(outside)

    integration = _obsidian_integration(vault)
    assert asyncio.run(integration.connect()) is True
    assert asyncio.run(integration.send_file(str(source))) is False
    assert not (vault / "Attachments" / source.name).exists()


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


def test_workflow_integration_reuses_single_timestamp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    output_dir = tmp_path / "workflow"
    source = tmp_path / "report.md"
    source.write_text("# report\n", encoding="utf-8")

    class _TickingDateTime:
        calls = 0

        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            value = datetime(2026, 2, 9, 12, 0, 0, tzinfo=UTC) + timedelta(seconds=cls.calls)
            cls.calls += 1
            if tz is None:
                return value
            return value.astimezone(tz)

    monkeypatch.setattr("file_organizer.integrations.workflow.datetime", _TickingDateTime)

    integration = WorkflowIntegration(
        IntegrationConfig(
            name="workflow",
            integration_type=IntegrationType.WORKFLOW,
            settings={"output_dir": str(output_dir)},
        )
    )

    assert asyncio.run(integration.connect()) is True
    assert (
        asyncio.run(integration.send_file(str(source), metadata={"summary": "Weekly report"}))
        is True
    )

    alfred_file = next(output_dir.glob("alfred-*.json"))
    raycast_file = next(output_dir.glob("raycast-*.json"))

    stamp = alfred_file.stem.split("-", 2)[2]
    alfred_payload = json.loads(alfred_file.read_text(encoding="utf-8"))
    raycast_payload = json.loads(raycast_file.read_text(encoding="utf-8"))

    assert alfred_payload["items"][0]["uid"].endswith(stamp)
    generated_stamp = datetime.fromisoformat(
        raycast_payload["generated_at"].replace("Z", "+00:00")
    ).strftime("%Y%m%dT%H%M%SZ")
    assert generated_stamp == stamp
