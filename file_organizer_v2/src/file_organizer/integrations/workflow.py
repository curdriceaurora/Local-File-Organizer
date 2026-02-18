"""Alfred/Raycast workflow integration adapter."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from file_organizer.integrations.base import (
    Integration,
    IntegrationConfig,
    IntegrationStatus,
    IntegrationType,
)


class WorkflowIntegration(Integration):
    """Export workflow payloads consumable by launcher tools."""

    def __init__(self, config: IntegrationConfig) -> None:
        if config.integration_type is not IntegrationType.WORKFLOW:
            config.integration_type = IntegrationType.WORKFLOW
        super().__init__(config)

    def _output_dir(self) -> Path:
        raw = str(self.config.settings.get("output_dir", "")).strip()
        if raw:
            return Path(raw).expanduser()
        return Path.home() / ".config" / "file-organizer" / "integrations" / "workflow"

    async def connect(self) -> bool:
        output_dir = self._output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        self.connected = output_dir.exists() and output_dir.is_dir()
        return self.connected

    async def disconnect(self) -> None:
        self.connected = False

    async def validate_auth(self) -> bool:
        return True

    async def send_file(self, file_path: str, metadata: dict[str, Any] | None = None) -> bool:
        if not self.connected and not await self.connect():
            return False

        source = Path(file_path).expanduser()
        if not source.exists() or not source.is_file():
            return False

        payload = metadata or {}
        now = datetime.now(timezone.utc)
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        stem = source.stem

        alfred = {
            "items": [
                {
                    "title": source.name,
                    "subtitle": payload.get("summary", "File exported by File Organizer"),
                    "arg": str(source.resolve(strict=False)),
                    "uid": f"{stem}-{stamp}",
                }
            ]
        }
        raycast = {
            "name": f"Open {source.name}",
            "path": str(source.resolve(strict=False)),
            "metadata": payload,
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

        output_dir = self._output_dir()
        alfred_path = output_dir / f"alfred-{stem}-{stamp}.json"
        raycast_path = output_dir / f"raycast-{stem}-{stamp}.json"

        alfred_path.write_text(
            json.dumps(alfred, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        raycast_path.write_text(
            json.dumps(raycast, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return True

    async def get_status(self) -> IntegrationStatus:
        output_dir = self._output_dir()
        return IntegrationStatus(
            name=self.config.name,
            integration_type=self.config.integration_type,
            enabled=self.config.enabled,
            connected=self.connected,
            details={
                "output_dir": str(output_dir),
                "output_exists": output_dir.exists() and output_dir.is_dir(),
            },
        )
