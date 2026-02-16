"""Marketplace-specific plugin errors."""
from __future__ import annotations

from file_organizer.plugins.errors import PluginError


class MarketplaceError(PluginError):
    """Base class for marketplace failures."""


class MarketplaceSchemaError(MarketplaceError):
    """Raised when repository payloads are malformed."""


class MarketplaceRepositoryError(MarketplaceError):
    """Raised when repository requests fail."""


class MarketplaceInstallError(MarketplaceError):
    """Raised when plugin installation or update fails."""


class MarketplaceReviewError(MarketplaceError):
    """Raised when review operations fail."""

