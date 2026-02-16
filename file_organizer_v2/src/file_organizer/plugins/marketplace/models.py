"""Data models for plugin marketplace operations."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from file_organizer.plugins.marketplace.errors import MarketplaceSchemaError
from file_organizer.plugins.marketplace.validators import (
    normalize_plugin_name,
    normalize_plugin_version,
)


def utc_now_iso() -> str:
    """Return the current UTC timestamp in RFC3339/Zulu format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_str_list(raw: object, *, field_name: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise MarketplaceSchemaError(f"Field '{field_name}' must be a list of strings.")
    values: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            raise MarketplaceSchemaError(f"Field '{field_name}' must contain only strings.")
        token = item.strip()
        if token:
            values.append(token)
    return tuple(values)


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hex digest for a file."""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class PluginPackage:
    """Repository package metadata."""

    name: str
    version: str
    author: str
    description: str
    download_url: str
    checksum_sha256: str
    size_bytes: int
    dependencies: tuple[str, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    category: str = "general"
    license: str = "MIT"
    min_organizer_version: str = "2.0.0"
    max_organizer_version: Optional[str] = None
    homepage: Optional[str] = None
    downloads: int = 0
    rating: float = 0.0
    reviews_count: int = 0

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PluginPackage:
        """Build a package object from raw repository JSON."""
        required_fields = (
            "name",
            "version",
            "author",
            "description",
            "download_url",
            "checksum_sha256",
            "size_bytes",
        )
        missing = [field_name for field_name in required_fields if field_name not in payload]
        if missing:
            joined = ", ".join(sorted(missing))
            raise MarketplaceSchemaError(f"Plugin metadata missing required fields: {joined}")

        try:
            name = normalize_plugin_name(str(payload["name"]))
        except ValueError as exc:
            raise MarketplaceSchemaError(str(exc)) from exc
        try:
            version = normalize_plugin_version(str(payload["version"]))
        except ValueError as exc:
            raise MarketplaceSchemaError(str(exc)) from exc
        author = str(payload["author"]).strip()
        description = str(payload["description"]).strip()
        download_url = str(payload["download_url"]).strip()
        checksum_sha256 = str(payload["checksum_sha256"]).strip().lower()
        if not name or not version or not author or not description or not download_url:
            raise MarketplaceSchemaError("Plugin metadata contains empty required values.")
        if len(checksum_sha256) != 64:
            raise MarketplaceSchemaError("checksum_sha256 must be a 64-character hex digest.")
        try:
            size_bytes = int(payload["size_bytes"])
        except (TypeError, ValueError) as exc:
            raise MarketplaceSchemaError("size_bytes must be an integer.") from exc
        if size_bytes <= 0:
            raise MarketplaceSchemaError("size_bytes must be positive.")

        try:
            rating = float(payload.get("rating", 0.0))
        except (TypeError, ValueError) as exc:
            raise MarketplaceSchemaError("rating must be numeric.") from exc
        if rating < 0.0 or rating > 5.0:
            raise MarketplaceSchemaError("rating must be between 0.0 and 5.0.")

        try:
            downloads = int(payload.get("downloads", 0))
            reviews_count = int(payload.get("reviews_count", 0))
        except (TypeError, ValueError) as exc:
            raise MarketplaceSchemaError(
                "downloads and reviews_count must be integers."
            ) from exc
        if downloads < 0 or reviews_count < 0:
            raise MarketplaceSchemaError("downloads and reviews_count cannot be negative.")

        dependencies = _parse_str_list(payload.get("dependencies"), field_name="dependencies")
        tags = _parse_str_list(payload.get("tags"), field_name="tags")

        min_version = str(payload.get("min_organizer_version", "2.0.0")).strip() or "2.0.0"
        max_version_raw = payload.get("max_organizer_version")
        max_version = str(max_version_raw).strip() if isinstance(max_version_raw, str) else None
        if max_version == "":
            max_version = None

        category = str(payload.get("category", "general")).strip() or "general"
        license_name = str(payload.get("license", "MIT")).strip() or "MIT"
        homepage_raw = payload.get("homepage")
        homepage = str(homepage_raw).strip() if isinstance(homepage_raw, str) else None
        if homepage == "":
            homepage = None

        return cls(
            name=name,
            version=version,
            author=author,
            description=description,
            download_url=download_url,
            checksum_sha256=checksum_sha256,
            size_bytes=size_bytes,
            dependencies=dependencies,
            tags=tags,
            category=category,
            license=license_name,
            min_organizer_version=min_version,
            max_organizer_version=max_version,
            homepage=homepage,
            downloads=downloads,
            rating=rating,
            reviews_count=reviews_count,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize package metadata into JSON-safe shape."""
        return {
            "name": self.name,
            "version": self.version,
            "author": self.author,
            "description": self.description,
            "homepage": self.homepage,
            "download_url": self.download_url,
            "checksum_sha256": self.checksum_sha256,
            "size_bytes": self.size_bytes,
            "dependencies": list(self.dependencies),
            "tags": list(self.tags),
            "category": self.category,
            "license": self.license,
            "min_organizer_version": self.min_organizer_version,
            "max_organizer_version": self.max_organizer_version,
            "downloads": self.downloads,
            "rating": self.rating,
            "reviews_count": self.reviews_count,
        }


@dataclass(frozen=True)
class InstalledPlugin:
    """Installed plugin state."""

    name: str
    version: str
    source_url: str
    installed_at: str = field(default_factory=utc_now_iso)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> InstalledPlugin:
        try:
            name = normalize_plugin_name(str(payload.get("name", "")))
        except ValueError as exc:
            raise MarketplaceSchemaError(str(exc)) from exc
        try:
            version = normalize_plugin_version(str(payload.get("version", "")))
        except ValueError as exc:
            raise MarketplaceSchemaError(str(exc)) from exc
        source_url = str(payload.get("source_url", "")).strip()
        installed_at = str(payload.get("installed_at", "")).strip() or utc_now_iso()
        if not name or not version or not source_url:
            raise MarketplaceSchemaError("Installed plugin entry is missing required fields.")
        return cls(name=name, version=version, source_url=source_url, installed_at=installed_at)

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "source_url": self.source_url,
            "installed_at": self.installed_at,
        }


@dataclass(frozen=True)
class PluginReview:
    """User review for a plugin package."""

    plugin_name: str
    user_id: str
    rating: int
    title: str
    content: str
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)
    helpful_count: int = 0

    def __post_init__(self) -> None:
        if not self.plugin_name.strip():
            raise MarketplaceSchemaError("plugin_name cannot be empty.")
        if not self.user_id.strip():
            raise MarketplaceSchemaError("user_id cannot be empty.")
        if self.rating < 1 or self.rating > 5:
            raise MarketplaceSchemaError("rating must be between 1 and 5.")
        if not self.title.strip():
            raise MarketplaceSchemaError("title cannot be empty.")
        if not self.content.strip():
            raise MarketplaceSchemaError("content cannot be empty.")
        if self.helpful_count < 0:
            raise MarketplaceSchemaError("helpful_count cannot be negative.")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PluginReview:
        try:
            rating = int(payload.get("rating", 0))
            helpful_count = int(payload.get("helpful_count", 0))
        except (TypeError, ValueError) as exc:
            raise MarketplaceSchemaError("rating/helpful_count must be integers.") from exc
        return cls(
            plugin_name=str(payload.get("plugin_name", "")),
            user_id=str(payload.get("user_id", "")),
            rating=rating,
            title=str(payload.get("title", "")),
            content=str(payload.get("content", "")),
            created_at=str(payload.get("created_at", "")) or utc_now_iso(),
            updated_at=str(payload.get("updated_at", "")) or utc_now_iso(),
            helpful_count=helpful_count,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin_name": self.plugin_name,
            "user_id": self.user_id,
            "rating": self.rating,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "helpful_count": self.helpful_count,
        }
