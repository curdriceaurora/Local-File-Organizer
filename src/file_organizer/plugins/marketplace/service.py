"""High-level service for plugin marketplace use cases."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from file_organizer.plugins.marketplace.installer import PluginInstaller
from file_organizer.plugins.marketplace.metadata import PluginMetadataStore
from file_organizer.plugins.marketplace.models import InstalledPlugin, PluginPackage, PluginReview
from file_organizer.plugins.marketplace.repository import PluginRepository
from file_organizer.plugins.marketplace.reviews import ReviewManager


def default_marketplace_home() -> Path:
    """Resolve the marketplace home directory from environment or defaults."""
    configured = os.environ.get("FO_MARKETPLACE_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".config" / "file-organizer" / "marketplace").resolve()


def default_repo_url(home_dir: Path) -> str:
    """Resolve repository URL from environment or local default path."""
    configured = os.environ.get("FO_MARKETPLACE_REPO_URL")
    if configured:
        return configured
    return str(home_dir / "repository")


class MarketplaceService:
    """Facade that coordinates repository, installation, metadata, and reviews."""

    def __init__(
        self,
        *,
        home_dir: Optional[Path] = None,
        repo_url: Optional[str] = None,
    ) -> None:
        """Set up the marketplace service using the given home directory."""
        self.home_dir = (home_dir or default_marketplace_home()).resolve()
        self.home_dir.mkdir(parents=True, exist_ok=True)

        repository_url = repo_url or default_repo_url(self.home_dir)
        self.repository = PluginRepository(repository_url)
        self.installer = PluginInstaller(
            self.home_dir / "plugins",
            self.repository,
            installed_plugins_file=self.home_dir / "installed.json",
        )
        self.metadata_store = PluginMetadataStore(self.home_dir / "metadata.json")
        self.review_manager = ReviewManager(self.home_dir / "reviews.json")

    def refresh_metadata(self) -> list[PluginPackage]:
        """Refresh local metadata cache from repository."""
        packages = self.repository.all_plugins()
        self.metadata_store.sync(packages)
        return packages

    def _read_or_refresh_metadata(self) -> list[PluginPackage]:
        metadata_path = self.home_dir / "metadata.json"
        try:
            is_missing_or_empty = (not metadata_path.exists()) or metadata_path.stat().st_size == 0
        except OSError:
            is_missing_or_empty = True
        if is_missing_or_empty:
            return self.refresh_metadata()

        if self.repository.is_cache_fresh():
            return self.metadata_store.list_all()

        latest_packages = self.repository.all_plugins()
        cached_packages = self.metadata_store.list_all()
        if latest_packages != cached_packages:
            self.metadata_store.sync(latest_packages)
            return latest_packages
        return cached_packages

    def list_plugins(
        self,
        *,
        page: int = 1,
        per_page: int = 20,
        query: str = "",
        tags: Optional[list[str]] = None,
        category: Optional[str] = None,
    ) -> tuple[list[PluginPackage], int]:
        """List/search repository plugins and return total count for pagination."""
        packages = self._read_or_refresh_metadata()

        if query.strip() or (tags and len(tags) > 0) or (category and category.strip()):
            filtered = self.metadata_store.search(
                query=query,
                tags=tags,
                category=category,
            )
        else:
            filtered = packages

        if page < 1 or per_page < 1:
            return [], len(filtered)
        start = (page - 1) * per_page
        end = start + per_page
        return filtered[start:end], len(filtered)

    def get_plugin(self, name: str, *, version: Optional[str] = None) -> PluginPackage:
        """Fetch package metadata from repository."""
        return self.repository.get_plugin(name, version=version)

    def install(self, name: str, *, version: Optional[str] = None) -> InstalledPlugin:
        """Install a plugin package."""
        return self.installer.install(name, version=version)

    def uninstall(self, name: str) -> None:
        """Uninstall a plugin package."""
        self.installer.uninstall(name)

    def update(self, name: str) -> Optional[InstalledPlugin]:
        """Update installed plugin to latest version."""
        return self.installer.update(name)

    def list_installed(self) -> list[InstalledPlugin]:
        """List installed plugins."""
        return self.installer.list_installed()

    def check_updates(self) -> list[str]:
        """List installed plugins with available updates."""
        return self.installer.check_updates()

    def get_reviews(self, plugin_name: str, *, limit: int = 10) -> list[PluginReview]:
        """Get plugin reviews."""
        return self.review_manager.get_reviews(plugin_name, limit=limit)

    def add_review(self, review: PluginReview) -> None:
        """Add or update a plugin review."""
        self.review_manager.add_review(review)

    def get_average_rating(self, plugin_name: str) -> float:
        """Get average user rating for a plugin."""
        return self.review_manager.get_average_rating(plugin_name)
