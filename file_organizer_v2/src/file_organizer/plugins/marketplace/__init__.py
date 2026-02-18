"""Plugin marketplace primitives."""

from __future__ import annotations

from file_organizer.plugins.marketplace.errors import (
    MarketplaceError,
    MarketplaceInstallError,
    MarketplaceRepositoryError,
    MarketplaceReviewError,
    MarketplaceSchemaError,
)
from file_organizer.plugins.marketplace.installer import PluginInstaller
from file_organizer.plugins.marketplace.metadata import PluginMetadataStore
from file_organizer.plugins.marketplace.models import (
    InstalledPlugin,
    PluginPackage,
    PluginReview,
    compute_sha256,
    utc_now_iso,
)
from file_organizer.plugins.marketplace.repository import PluginRepository
from file_organizer.plugins.marketplace.reviews import ReviewManager
from file_organizer.plugins.marketplace.service import MarketplaceService

__all__ = [
    "InstalledPlugin",
    "MarketplaceError",
    "MarketplaceInstallError",
    "MarketplaceRepositoryError",
    "MarketplaceReviewError",
    "MarketplaceSchemaError",
    "MarketplaceService",
    "PluginInstaller",
    "PluginMetadataStore",
    "PluginPackage",
    "PluginRepository",
    "PluginReview",
    "ReviewManager",
    "compute_sha256",
    "utc_now_iso",
]
