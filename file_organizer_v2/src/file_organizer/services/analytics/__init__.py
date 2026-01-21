"""
Analytics service package.

Provides comprehensive analytics for file organization, storage usage,
and system efficiency.
"""

from .storage_analyzer import StorageAnalyzer
from .metrics_calculator import MetricsCalculator
from .analytics_service import AnalyticsService

__all__ = [
    'StorageAnalyzer',
    'MetricsCalculator',
    'AnalyticsService',
]
