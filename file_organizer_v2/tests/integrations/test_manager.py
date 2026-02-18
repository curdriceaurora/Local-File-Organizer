"""Unit tests for integration manager orchestration."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from file_organizer.integrations import (
    IntegrationConfig,
    IntegrationManager,
    IntegrationType,
    WorkflowIntegration,
)

pytestmark = pytest.mark.ci


def test_manager_register_update_connect_send(tmp_path: Path) -> None:
    manager = IntegrationManager()
    output_dir = tmp_path / "workflow"
    source = tmp_path / "source.txt"
    source.write_text("data", encoding="utf-8")

    integration = WorkflowIntegration(
        IntegrationConfig(
            name="workflow",
            integration_type=IntegrationType.WORKFLOW,
            settings={"output_dir": str(output_dir)},
        )
    )
    manager.register(integration)

    assert manager.get("workflow") is integration
    assert manager.update_settings("workflow", {"output_dir": str(output_dir / "nested")}) is True

    statuses = asyncio.run(manager.list_statuses())
    assert statuses[0].name == "workflow"
    assert statuses[0].connected is False

    assert asyncio.run(manager.connect("workflow")) is True
    assert asyncio.run(manager.send_file("workflow", str(source), metadata={"k": "v"})) is True

    exported = list((output_dir / "nested").glob("*.json"))
    assert exported


def test_manager_handles_missing_integrations_gracefully() -> None:
    manager = IntegrationManager()
    assert manager.get("missing") is None
    assert manager.update_settings("missing", {"x": 1}) is False
    assert asyncio.run(manager.connect("missing")) is False
    assert asyncio.run(manager.disconnect("missing")) is False
    assert asyncio.run(manager.send_file("missing", "/tmp/nope")) is False
