"""
Analytics data models.

Data classes for analytics dashboard, storage stats, and quality metrics.
"""

from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path


@dataclass
class FileInfo:
    """Information about a single file."""
    path: Path
    size: int
    type: str
    modified: datetime
    category: Optional[str] = None


@dataclass
class StorageStats:
    """Storage usage statistics."""
    total_size: int
    organized_size: int
    saved_size: int
    file_count: int
    directory_count: int
    largest_files: list[FileInfo] = field(default_factory=list)
    size_by_type: dict[str, int] = field(default_factory=dict)
    size_by_category: dict[str, int] = field(default_factory=dict)

    @property
    def formatted_total_size(self) -> str:
        """Get human-readable total size."""
        return self._format_size(self.total_size)

    @property
    def formatted_saved_size(self) -> str:
        """Get human-readable saved size."""
        return self._format_size(self.saved_size)

    @property
    def savings_percentage(self) -> float:
        """Calculate savings percentage."""
        if self.total_size == 0:
            return 0.0
        return (self.saved_size / self.total_size) * 100

    @staticmethod
    def _format_size(size: int) -> str:
        """Format size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} PB"


@dataclass
class FileDistribution:
    """File distribution statistics."""
    by_type: dict[str, int] = field(default_factory=dict)
    by_category: dict[str, int] = field(default_factory=dict)
    by_size_range: dict[str, int] = field(default_factory=dict)
    total_files: int = 0

    def get_type_percentage(self, file_type: str) -> float:
        """Get percentage of files of a given type."""
        if self.total_files == 0:
            return 0.0
        return (self.by_type.get(file_type, 0) / self.total_files) * 100


@dataclass
class DuplicateStats:
    """Duplicate detection statistics."""
    total_duplicates: int
    duplicate_groups: int
    space_wasted: int
    space_recoverable: int
    by_type: dict[str, int] = field(default_factory=dict)
    largest_duplicate_group: Optional[Dict] = None

    @property
    def formatted_space_wasted(self) -> str:
        """Get human-readable wasted space."""
        return StorageStats._format_size(self.space_wasted)

    @property
    def formatted_recoverable(self) -> str:
        """Get human-readable recoverable space."""
        return StorageStats._format_size(self.space_recoverable)


@dataclass
class QualityMetrics:
    """File organization quality metrics."""
    quality_score: float  # 0-100
    naming_compliance: float  # 0-1
    structure_consistency: float  # 0-1
    metadata_completeness: float  # 0-1
    categorization_accuracy: float  # 0-1
    improvement_rate: Optional[float] = None

    @property
    def grade(self) -> str:
        """Get letter grade for quality score."""
        if self.quality_score >= 90:
            return 'A'
        elif self.quality_score >= 80:
            return 'B'
        elif self.quality_score >= 70:
            return 'C'
        elif self.quality_score >= 60:
            return 'D'
        else:
            return 'F'

    @property
    def formatted_score(self) -> str:
        """Get formatted quality score."""
        return f"{self.quality_score:.1f}/100 ({self.grade})"


@dataclass
class TimeSavings:
    """Time savings from automation."""
    total_operations: int
    automated_operations: int
    manual_time_seconds: int
    automated_time_seconds: int
    estimated_time_saved_seconds: int

    @property
    def automation_percentage(self) -> float:
        """Get percentage of automated operations."""
        if self.total_operations == 0:
            return 0.0
        return (self.automated_operations / self.total_operations) * 100

    @property
    def formatted_time_saved(self) -> str:
        """Get human-readable time saved."""
        return self._format_duration(self.estimated_time_saved_seconds)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Format duration in human-readable format."""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds / 60
            return f"{minutes:.1f}m"
        elif seconds < 86400:
            hours = seconds / 3600
            return f"{hours:.1f}h"
        else:
            days = seconds / 86400
            return f"{days:.1f}d"


@dataclass
class MetricsSnapshot:
    """Snapshot of metrics at a point in time."""
    timestamp: datetime
    storage_stats: StorageStats
    quality_metrics: QualityMetrics
    duplicate_stats: Optional[DuplicateStats] = None
    time_savings: Optional[TimeSavings] = None


@dataclass
class TrendData:
    """Trend data over time."""
    metric_name: str
    values: list[float] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)

    def add_data_point(self, value: float, timestamp: datetime) -> None:
        """Add a data point to the trend."""
        self.values.append(value)
        self.timestamps.append(timestamp)

    @property
    def trend_direction(self) -> str:
        """Determine trend direction (up, down, stable)."""
        if len(self.values) < 2:
            return 'stable'

        recent = self.values[-min(5, len(self.values)):]
        first_half = sum(recent[:len(recent)//2]) / max(len(recent)//2, 1)
        second_half = sum(recent[len(recent)//2:]) / max(len(recent) - len(recent)//2, 1)

        change = ((second_half - first_half) / max(first_half, 1)) * 100

        if change > 5:
            return 'up'
        elif change < -5:
            return 'down'
        else:
            return 'stable'


@dataclass
class AnalyticsDashboard:
    """Complete analytics dashboard data."""
    storage_stats: StorageStats
    file_distribution: FileDistribution
    duplicate_stats: DuplicateStats
    quality_metrics: QualityMetrics
    time_savings: TimeSavings
    trends: dict[str, TrendData] = field(default_factory=dict)
    generated_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict:
        """Convert dashboard to dictionary for serialization."""
        return {
            'storage_stats': {
                'total_size': self.storage_stats.total_size,
                'organized_size': self.storage_stats.organized_size,
                'saved_size': self.storage_stats.saved_size,
                'file_count': self.storage_stats.file_count,
                'directory_count': self.storage_stats.directory_count,
            },
            'file_distribution': {
                'by_type': self.file_distribution.by_type,
                'by_category': self.file_distribution.by_category,
                'total_files': self.file_distribution.total_files,
            },
            'duplicate_stats': {
                'total_duplicates': self.duplicate_stats.total_duplicates,
                'duplicate_groups': self.duplicate_stats.duplicate_groups,
                'space_wasted': self.duplicate_stats.space_wasted,
                'space_recoverable': self.duplicate_stats.space_recoverable,
            },
            'quality_metrics': {
                'quality_score': self.quality_metrics.quality_score,
                'naming_compliance': self.quality_metrics.naming_compliance,
                'structure_consistency': self.quality_metrics.structure_consistency,
                'grade': self.quality_metrics.grade,
            },
            'time_savings': {
                'total_operations': self.time_savings.total_operations,
                'automated_operations': self.time_savings.automated_operations,
                'automation_percentage': self.time_savings.automation_percentage,
                'time_saved': self.time_savings.formatted_time_saved,
            },
            'generated_at': self.generated_at.isoformat()
        }
