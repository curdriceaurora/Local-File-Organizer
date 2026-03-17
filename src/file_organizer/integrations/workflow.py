"""Alfred/Raycast workflow integration adapter."""

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


class WorkflowIntegration(Integration):
    """Export workflow payloads consumable by launcher tools."""

    def __init__(self, config: IntegrationConfig) -> None:
        """Initialize the workflow integration with the given config."""
        if config.integration_type is not IntegrationType.WORKFLOW:
            config.integration_type = IntegrationType.WORKFLOW
        super().__init__(config)

    def _output_dir(self) -> Path:
        """Return the configured output directory, falling back to the default config path."""
        raw = str(self.config.settings.get("output_dir", "")).strip()
        if raw:
            return Path(raw).expanduser()
        from file_organizer.config.path_manager import get_config_dir

        return get_config_dir() / "integrations" / "workflow"

    async def connect(self) -> bool:
        """Connect to the workflow output directory, creating it if needed."""
        output_dir = self._output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
        self.connected = output_dir.exists() and output_dir.is_dir()
        return self.connected

    async def disconnect(self) -> None:
        """Disconnect from the workflow integration."""
        self.connected = False

    async def validate_auth(self) -> bool:
        """Validate auth; workflow integration requires no credentials."""
        return True

    async def send_file(self, file_path: str, metadata: dict[str, Any] | None = None) -> bool:
        """Export Alfred and Raycast workflow payloads for the given file."""
        if not self.connected and not await self.connect():
            return False

        source = Path(file_path).expanduser()
        if not source.exists() or not source.is_file():
            return False

        payload = metadata or {}
        now = datetime.now(UTC)
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
        """Return the current connection status for this integration."""
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
