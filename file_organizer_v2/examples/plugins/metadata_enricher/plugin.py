"""Plugin example that writes sidecar metadata for organized files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from file_organizer.plugins import Plugin, PluginMetadata
from file_organizer.plugins.sdk import hook


class MetadataEnricherPlugin(Plugin):
    """Creates .json sidecar metadata for organized files."""

    def on_load(self) -> None:
        return None

    def on_enable(self) -> None:
        default_tags = self.config.get("default_tags", ["organized"])
        if isinstance(default_tags, list):
            self.default_tags = [str(tag) for tag in default_tags]
        else:
            self.default_tags = ["organized"]

    def on_disable(self) -> None:
        return None

    def on_unload(self) -> None:
        return None

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="metadata_enricher",
            version="1.0.0",
            author="File Organizer Team",
            description="Adds metadata sidecar files after organization.",
        )

    @hook("file.organized", priority=15)
    def on_file_organized(self, payload: dict[str, Any]) -> dict[str, object]:
        destination = payload.get("destination_path")
        if not isinstance(destination, str) or not destination:
            return {"enriched": False, "reason": "missing destination_path"}

        target = Path(destination)
        if not target.exists():
            return {"enriched": False, "reason": "destination file missing"}

        sidecar_payload = {
            "path": str(target),
            "source_path": payload.get("source_path"),
            "tags": self.default_tags,
            "plugin": "metadata_enricher",
        }
        sidecar = target.with_suffix(f"{target.suffix}.metadata.json")
        sidecar.write_text(json.dumps(sidecar_payload, indent=2, sort_keys=True), encoding="utf-8")
        return {"enriched": True, "metadata_file": str(sidecar)}
