"""Plugin marketplace repository client."""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import ParseResult, unquote, urljoin, urlparse
from urllib.request import url2pathname

import httpx

from file_organizer.plugins.marketplace.errors import (
    MarketplaceRepositoryError,
    MarketplaceSchemaError,
)
from file_organizer.plugins.marketplace.models import PluginPackage
from file_organizer.plugins.marketplace.validators import version_sort_key

_DEFAULT_TIMEOUT_SECONDS = 10.0
_DEFAULT_CACHE_TTL_SECONDS = 300


def _to_file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _url_to_local_path(url: str) -> Path:
    parsed = urlparse(url)
    if parsed.scheme != "file":
        raise MarketplaceRepositoryError(f"Expected file URL, got: {url}")
    if parsed.netloc and parsed.netloc not in ("", "localhost"):
        raise MarketplaceRepositoryError(f"Unsupported file URL host: {parsed.netloc}")
    return Path(url2pathname(unquote(parsed.path))).resolve()


class PluginRepository:
    """Read package metadata and package files from a marketplace repository."""

    def __init__(
        self,
        repo_url: str,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        cache_ttl_seconds: int = _DEFAULT_CACHE_TTL_SECONDS,
    ) -> None:
        self.repo_url = self._normalize_repo_url(repo_url)
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: list[PluginPackage] | None = None
        self._cache_expires_at = 0.0
        self._base_file_root = self._resolve_base_file_root(self.repo_url)

    @staticmethod
    def _normalize_repo_url(repo_url: str) -> str:
        candidate = repo_url.strip()
        if not candidate:
            raise MarketplaceRepositoryError("Repository URL must not be empty.")
        parsed = urlparse(candidate)
        if parsed.scheme in {"http", "https", "file"}:
            return candidate
        return _to_file_url(Path(candidate))

    @staticmethod
    def _resolve_base_file_root(repo_url: str) -> Optional[Path]:
        parsed = urlparse(repo_url)
        if parsed.scheme != "file":
            return None
        path = _url_to_local_path(repo_url)
        if path.name.endswith(".json"):
            return path.parent
        return path

    def clear_cache(self) -> None:
        """Clear cached repository metadata."""
        self._cache = None
        self._cache_expires_at = 0.0

    def is_cache_fresh(self) -> bool:
        """Return true when repository metadata cache can be reused."""
        return self._cache is not None and time.time() < self._cache_expires_at

    def list_plugins(self, *, page: int = 1, per_page: int = 20) -> list[PluginPackage]:
        """Return paginated plugin package list."""
        if page < 1 or per_page < 1:
            raise MarketplaceRepositoryError("page and per_page must be >= 1.")
        packages = self._load_packages()
        start = (page - 1) * per_page
        end = start + per_page
        return packages[start:end]

    def all_plugins(self) -> list[PluginPackage]:
        """Return full package list."""
        return list(self._load_packages())

    def search_plugins(
        self,
        query: str,
        *,
        tags: Optional[list[str]] = None,
        category: Optional[str] = None,
    ) -> list[PluginPackage]:
        """Search plugins by query with optional tag/category filters."""
        token = query.strip().lower()
        selected_tags = {tag.strip().lower() for tag in tags or [] if tag.strip()}
        category_token = category.strip().lower() if category else None

        matches: list[PluginPackage] = []
        for package in self._load_packages():
            haystack = " ".join([package.name, package.description, package.author]).lower()
            if token and token not in haystack:
                continue
            if selected_tags and not selected_tags.issubset({tag.lower() for tag in package.tags}):
                continue
            if category_token and package.category.lower() != category_token:
                continue
            matches.append(package)
        return matches

    def get_plugin(self, name: str, *, version: Optional[str] = None) -> PluginPackage:
        """Get a plugin package by name and optional version."""
        candidate_name = name.strip().lower()
        if not candidate_name:
            raise MarketplaceRepositoryError("Plugin name must not be empty.")

        matches = [
            package for package in self._load_packages() if package.name.lower() == candidate_name
        ]
        if not matches:
            raise MarketplaceRepositoryError(f"Plugin '{name}' was not found in repository.")

        if version is not None:
            requested = version.strip()
            for package in matches:
                if package.version == requested:
                    return package
            raise MarketplaceRepositoryError(
                f"Plugin '{name}' version '{version}' was not found in repository."
            )

        matches.sort(key=lambda item: version_sort_key(item.version), reverse=True)
        return matches[0]

    def download_plugin(self, package: PluginPackage, destination_dir: Path) -> Path:
        """Download package artifact into destination directory."""
        destination_dir.mkdir(parents=True, exist_ok=True)
        artifact_name = f"{package.name}-{package.version}.zip"
        destination_path = destination_dir / artifact_name
        source_url = self._resolve_package_url(package.download_url)
        parsed = urlparse(source_url)

        if parsed.scheme == "file":
            source_path = _url_to_local_path(source_url)
            if self._base_file_root is not None:
                try:
                    source_path.relative_to(self._base_file_root)
                except ValueError as exc:
                    raise MarketplaceRepositoryError(
                        "Refusing to read file outside repository root."
                    ) from exc
            if not source_path.exists() or not source_path.is_file():
                raise MarketplaceRepositoryError(f"Plugin artifact not found: {source_path}")
            shutil.copy2(source_path, destination_path)
            return destination_path

        if parsed.scheme not in {"http", "https"}:
            raise MarketplaceRepositoryError(f"Unsupported download scheme: {parsed.scheme}")

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                with client.stream("GET", source_url) as response:
                    response.raise_for_status()
                    with destination_path.open("wb") as handle:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            if chunk:
                                handle.write(chunk)
        except httpx.HTTPError as exc:
            raise MarketplaceRepositoryError(
                f"Failed to download plugin package: {source_url}"
            ) from exc
        return destination_path

    def verify_checksum(self, file_path: Path, expected_sha256: str) -> bool:
        """Verify SHA256 checksum for downloaded artifact."""
        import hashlib

        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest().lower() == expected_sha256.lower()

    def _resolve_package_url(self, package_url: str) -> str:
        parsed = urlparse(package_url)
        if parsed.scheme in {"http", "https", "file"}:
            return package_url
        if parsed.netloc:
            raise MarketplaceRepositoryError(
                "download_url must not include a network location without an explicit scheme."
            )

        if self._base_file_root is not None:
            path = (self._base_file_root / package_url).resolve()
            return _to_file_url(path)

        base = self._index_url()
        return urljoin(base, package_url)

    def _index_url(self) -> str:
        parsed = urlparse(self.repo_url)
        if parsed.scheme == "file":
            path = _url_to_local_path(self.repo_url)
            if path.name.endswith(".json"):
                return _to_file_url(path)
            return _to_file_url(path / "index.json")

        if self.repo_url.endswith(".json"):
            return self.repo_url
        base = self.repo_url if self.repo_url.endswith("/") else f"{self.repo_url}/"
        return urljoin(base, "index.json")

    def _load_packages(self) -> list[PluginPackage]:
        now = time.time()
        if self._cache is not None and now < self._cache_expires_at:
            return self._cache

        payload = self._load_index_payload(self._index_url())
        raw_plugins = payload.get("plugins", [])
        if not isinstance(raw_plugins, list):
            raise MarketplaceSchemaError("Repository index 'plugins' must be a list.")

        packages: list[PluginPackage] = []
        for item in raw_plugins:
            if not isinstance(item, dict):
                raise MarketplaceSchemaError("Each plugin metadata entry must be a JSON object.")
            packages.append(PluginPackage.from_dict(item))
        packages.sort(key=lambda item: (item.name.lower(), version_sort_key(item.version)))

        self._cache = packages
        self._cache_expires_at = now + float(self.cache_ttl_seconds)
        return packages

    def _load_index_payload(self, index_url: str) -> dict[str, Any]:
        parsed: ParseResult = urlparse(index_url)
        if parsed.scheme == "file":
            path = _url_to_local_path(index_url)
            if not path.exists():
                # A missing local index should not hard-fail startup UIs/CLIs.
                return {"plugins": []}
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise MarketplaceRepositoryError(
                    f"Failed to read repository index: {path}"
                ) from exc
            if not isinstance(payload, dict):
                raise MarketplaceSchemaError("Repository index root must be a JSON object.")
            return payload

        if parsed.scheme not in {"http", "https"}:
            raise MarketplaceRepositoryError(f"Unsupported repository scheme: {parsed.scheme}")

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(index_url)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as exc:
            raise MarketplaceRepositoryError(
                f"Failed to fetch marketplace index: {index_url}"
            ) from exc
        if not isinstance(payload, dict):
            raise MarketplaceSchemaError("Repository index root must be a JSON object.")
        return payload
