"""Analytics service package.

Provides comprehensive analytics for file organization, storage usage,
and system efficiency.
"""

from __future__ import annotations

from .analytics_service import AnalyticsService
from .metrics_calculator import MetricsCalculator
from .storage_analyzer import StorageAnalyzer

__all__ = [
    "StorageAnalyzer",
    "MetricsCalculator",
    "AnalyticsService",
]
