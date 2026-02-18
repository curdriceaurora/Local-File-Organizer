"""Plugin example that copies organized files to a backup directory."""

from __future__ import annotations

import shutil
from pathlib import Path

from file_organizer.plugins import Plugin, PluginMetadata
from file_organizer.plugins.sdk import hook


class AutoBackupPlugin(Plugin):
    """Creates a backup copy when files are organized."""

    name = "auto_backup"
    version = "1.0.0"
    allowed_paths: list = []

    def on_load(self) -> None:
        return None

    def on_enable(self) -> None:
        configured = str(self.config.get("backup_dir", "")).strip()
        self.backup_dir = Path(configured) if configured else None
        if self.backup_dir is not None:
            self.backup_dir.mkdir(parents=True, exist_ok=True)

    def on_disable(self) -> None:
        return None

    def on_unload(self) -> None:
        return None

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="auto_backup",
            version="1.0.0",
            author="File Organizer Team",
            description="Backs up files after organization.",
        )

    @hook("file.organized", priority=5)
    def on_file_organized(self, payload: dict[str, object]) -> dict[str, object]:
        if self.backup_dir is None:
            return {"backed_up": False, "reason": "backup_dir not configured"}

        destination = payload.get("destination_path")
        if not isinstance(destination, str) or not destination:
            return {"backed_up": False, "reason": "missing destination_path"}

        source_path = Path(destination)
        if not source_path.is_file():
            return {"backed_up": False, "reason": "destination file missing"}

        backup_path = self.backup_dir / source_path.name
        shutil.copy2(source_path, backup_path)
        return {"backed_up": True, "backup_path": str(backup_path)}
