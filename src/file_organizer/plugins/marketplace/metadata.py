"""Local metadata cache for marketplace packages."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from file_organizer.plugins.marketplace.errors import MarketplaceRepositoryError
from file_organizer.plugins.marketplace.models import PluginPackage
from file_organizer.plugins.marketplace.validators import version_sort_key


class PluginMetadataStore:
    """Persist and query marketplace metadata locally."""

    def __init__(self, db_path: Path) -> None:
        """Set up the metadata store backed by the given database path."""
        self.db_path = db_path

    def sync(self, packages: list[PluginPackage]) -> None:
        """Replace stored metadata with a fresh package snapshot."""
        payload = {"plugins": [package.to_dict() for package in packages]}
        self._write_payload(payload)

    def list_all(self) -> list[PluginPackage]:
        """Load all cached plugins."""
        payload = self._read_payload()
        raw_plugins = payload.get("plugins", [])
        if not isinstance(raw_plugins, list):
            raise MarketplaceRepositoryError("Stored metadata is invalid (plugins must be a list).")

        packages: list[PluginPackage] = []
        for item in raw_plugins:
            if not isinstance(item, dict):
                continue
            packages.append(PluginPackage.from_dict(item))
        packages.sort(key=lambda package: (package.name.lower(), version_sort_key(package.version)))
        return packages

    def get_plugin(self, name: str) -> PluginPackage | None:
        """Return the newest cached package for a plugin name."""
        candidate = name.strip().lower()
        if not candidate:
            return None

        matches = [package for package in self.list_all() if package.name.lower() == candidate]
        if not matches:
            return None
        matches.sort(key=lambda package: version_sort_key(package.version), reverse=True)
        return matches[0]

    def search(
        self,
        query: str,
        *,
        tags: list[str] | None = None,
        category: str | None = None,
    ) -> list[PluginPackage]:
        """Search cached package metadata."""
        token = query.strip().lower()
        selected_tags = {tag.strip().lower() for tag in tags or [] if tag.strip()}
        category_token = category.strip().lower() if category else None

        results: list[PluginPackage] = []
        for package in self.list_all():
            haystack = " ".join([package.name, package.description, package.author]).lower()
            if token and token not in haystack:
                continue
            if selected_tags and not selected_tags.issubset({tag.lower() for tag in package.tags}):
                continue
            if category_token and package.category.lower() != category_token:
                continue
            results.append(package)
        return results

    def _read_payload(self) -> dict[str, Any]:
        if not self.db_path.exists():
            return {"plugins": []}
        try:
            payload = json.loads(self.db_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MarketplaceRepositoryError(
                f"Failed to read metadata store: {self.db_path}"
            ) from exc
        if not isinstance(payload, dict):
            raise MarketplaceRepositoryError("Metadata store root must be a JSON object.")
        return payload

    def _write_payload(self, payload: dict[str, Any]) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.db_path.parent),
            prefix=f".{self.db_path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True)
            Path(tmp_path).replace(self.db_path)
        except OSError as exc:
            raise MarketplaceRepositoryError(
                f"Failed to write metadata store: {self.db_path}"
            ) from exc
        finally:
            leftover = Path(tmp_path)
            if leftover.exists():
                leftover.unlink(missing_ok=True)
