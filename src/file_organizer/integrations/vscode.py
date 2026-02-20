"""VS Code integration adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from file_organizer.integrations.base import (
    Integration,
    IntegrationConfig,
    IntegrationStatus,
    IntegrationType,
)


class VSCodeIntegration(Integration):
    """Generate VS Code open-file commands for companion tooling."""

    def __init__(self, config: IntegrationConfig) -> None:
        if config.integration_type is not IntegrationType.EDITOR:
            config.integration_type = IntegrationType.EDITOR
        super().__init__(config)

    def _workspace_path(self) -> Path | None:
        raw = str(self.config.settings.get("workspace_path", "")).strip()
        if not raw:
            return None
        return Path(raw).expanduser()

    def _command_output_path(self) -> Path:
        raw = str(self.config.settings.get("command_output_path", "")).strip()
        if raw:
            return Path(raw).expanduser()
        return Path.home() / ".config" / "file-organizer" / "integrations" / "vscode-commands.jsonl"

    async def connect(self) -> bool:
        workspace = self._workspace_path()
        self.connected = workspace is None or (workspace.exists() and workspace.is_dir())
        return self.connected

    async def disconnect(self) -> None:
        self.connected = False

    async def validate_auth(self) -> bool:
        # VS Code integration uses local command relay and does not require auth.
        return True

    async def send_file(self, file_path: str, metadata: dict[str, Any] | None = None) -> bool:
        if not self.connected and not await self.connect():
            return False

        source = Path(file_path).expanduser()
        if not source.exists() or not source.is_file():
            return False

        output = self._command_output_path()
        output.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "command": "vscode.open",
            "path": str(source.resolve(strict=False)),
            "uri": f"vscode://file/{source.resolve(strict=False).as_posix()}",
            "workspace": str(self._workspace_path()) if self._workspace_path() else None,
            "metadata": metadata or {},
            "created_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with output.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")
        return True

    async def get_status(self) -> IntegrationStatus:
        workspace = self._workspace_path()
        command_output = self._command_output_path()
        return IntegrationStatus(
            name=self.config.name,
            integration_type=self.config.integration_type,
            enabled=self.config.enabled,
            connected=self.connected,
            details={
                "workspace_path": str(workspace) if workspace else None,
                "workspace_exists": workspace.exists() if workspace else True,
                "command_output_path": str(command_output),
            },
        )
