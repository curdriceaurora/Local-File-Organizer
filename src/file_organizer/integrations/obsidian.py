"""Obsidian vault integration adapter."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from file_organizer.integrations.base import (
    Integration,
    IntegrationConfig,
    IntegrationStatus,
    IntegrationType,
)


class ObsidianIntegration(Integration):
    """Export files and metadata into an Obsidian vault layout."""

    def __init__(self, config: IntegrationConfig) -> None:
        if config.integration_type is not IntegrationType.DESKTOP_APP:
            config.integration_type = IntegrationType.DESKTOP_APP
        super().__init__(config)

    def _vault_path(self) -> Path:
        raw = str(self.config.settings.get("vault_path", "")).strip()
        return Path(raw).expanduser()

    async def connect(self) -> bool:
        vault = self._vault_path()
        self.connected = bool(vault.exists() and vault.is_dir())
        return self.connected

    async def disconnect(self) -> None:
        self.connected = False

    async def validate_auth(self) -> bool:
        if self.config.auth_method == "none":
            return True
        if self.config.auth_method == "api_key":
            return bool(str(self.config.settings.get("api_key", "")).strip())
        return False

    async def send_file(self, file_path: str, metadata: dict[str, Any] | None = None) -> bool:
        if not self.connected and not await self.connect():
            return False
        if not await self.validate_auth():
            return False

        source = Path(file_path).expanduser()
        if not source.exists() or not source.is_file():
            return False

        vault = self._vault_path()
        attachments_subdir = str(
            self.config.settings.get("attachments_subdir", "Attachments")
        ).strip()
        notes_subdir = str(self.config.settings.get("notes_subdir", "Notes")).strip()

        target_dir = (vault / attachments_subdir).resolve(strict=False)
        target_dir.mkdir(parents=True, exist_ok=True)
        destination = target_dir / source.name

        shutil.copy2(source, destination)

        note_dir = (vault / notes_subdir).resolve(strict=False)
        note_dir.mkdir(parents=True, exist_ok=True)
        note_path = note_dir / f"{source.stem}.md"
        note_path.write_text(
            self._build_note_content(source, destination, metadata), encoding="utf-8"
        )
        return True

    async def get_status(self) -> IntegrationStatus:
        vault = self._vault_path()
        return IntegrationStatus(
            name=self.config.name,
            integration_type=self.config.integration_type,
            enabled=self.config.enabled,
            connected=self.connected,
            details={
                "vault_path": str(vault),
                "vault_exists": vault.exists() and vault.is_dir(),
                "auth_method": self.config.auth_method,
            },
        )

    def _build_note_content(
        self,
        source: Path,
        destination: Path,
        metadata: dict[str, Any] | None,
    ) -> str:
        payload = metadata or {}
        now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        frontmatter: dict[str, Any] = {
            "source": source.as_posix(),
            "exported_at": now,
            "attachment": destination.as_posix(),
        }
        if payload:
            frontmatter["metadata"] = payload

        yaml_frontmatter = yaml.safe_dump(
            frontmatter,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ).strip()

        lines = [
            "---",
            yaml_frontmatter,
        ]
        lines.extend(
            [
                "---",
                "",
                f"# {source.name}",
                "",
                "Exported by File Organizer Obsidian integration.",
            ]
        )
        return "\n".join(lines) + "\n"
