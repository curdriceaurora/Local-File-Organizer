"""
Analytics service - orchestrates all analytics components.

Main service that coordinates storage analysis, metrics calculation,
chart generation, and dashboard creation.
"""

from pathlib import Path
from typing import Optional, List, Dict
from datetime import datetime
import logging

from ...models.analytics import (
    AnalyticsDashboard,
    StorageStats,
    FileDistribution,
    DuplicateStats,
    QualityMetrics,
    TimeSavings,
    TrendData,
)
from .storage_analyzer import StorageAnalyzer
from .metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)


class AnalyticsService:
    """
    Main analytics service that orchestrates all analytics components.

    Coordinates:
    - Storage analysis
    - Quality metrics calculation
    - Duplicate statistics
    - Time savings estimation
    - Dashboard generation
    """

    def __init__(
        self,
        storage_analyzer: Optional[StorageAnalyzer] = None,
        metrics_calculator: Optional[MetricsCalculator] = None,
    ):
        """
        Initialize analytics service.

        Args:
            storage_analyzer: Storage analyzer instance (creates new if None)
            metrics_calculator: Metrics calculator instance (creates new if None)
        """
        self.storage_analyzer = storage_analyzer or StorageAnalyzer()
        self.metrics_calculator = metrics_calculator or MetricsCalculator()

    def generate_dashboard(
        self,
        directory: Path,
        duplicate_groups: Optional[List[Dict]] = None,
        max_depth: Optional[int] = None,
    ) -> AnalyticsDashboard:
        """
        Generate complete analytics dashboard.

        Args:
            directory: Directory to analyze
            duplicate_groups: Optional duplicate groups from deduplication
            max_depth: Maximum directory depth to analyze

        Returns:
            Complete AnalyticsDashboard object
        """
        logger.info(f"Generating analytics dashboard for {directory}")

        # Get storage statistics
        storage_stats = self.get_storage_stats(directory, max_depth)

        # Get file distribution
        file_distribution = self.storage_analyzer.calculate_size_distribution(directory)

        # Get duplicate statistics
        duplicate_stats = self.get_duplicate_stats(
            duplicate_groups or [], storage_stats.total_size
        )

        # Get quality metrics
        quality_metrics = self.get_quality_metrics(
            directory, storage_stats.file_count, storage_stats.organized_size
        )

        # Calculate time savings
        time_savings = self.calculate_time_saved(
            storage_stats.file_count, duplicate_stats.total_duplicates
        )

        dashboard = AnalyticsDashboard(
            storage_stats=storage_stats,
            file_distribution=file_distribution,
            duplicate_stats=duplicate_stats,
            quality_metrics=quality_metrics,
            time_savings=time_savings,
            generated_at=datetime.utcnow(),
        )

        logger.info("Dashboard generation complete")
        return dashboard

    def get_storage_stats(
        self, directory: Path, max_depth: Optional[int] = None
    ) -> StorageStats:
        """
        Get storage usage statistics.

        Args:
            directory: Directory to analyze
            max_depth: Maximum depth to traverse

        Returns:
            StorageStats object
        """
        logger.info("Analyzing storage usage")
        stats = self.storage_analyzer.analyze_directory(directory, max_depth)
        return stats

    def get_duplicate_stats(
        self, duplicate_groups: List[Dict], total_size: int
    ) -> DuplicateStats:
        """
        Get duplication statistics.

        Args:
            duplicate_groups: List of duplicate groups
            total_size: Total storage size

        Returns:
            DuplicateStats object
        """
        logger.info("Calculating duplicate statistics")

        if not duplicate_groups:
            return DuplicateStats(
                total_duplicates=0,
                duplicate_groups=0,
                space_wasted=0,
                space_recoverable=0,
            )

        total_duplicates = 0
        space_wasted = 0
        by_type: Dict[str, int] = {}
        largest_group = None
        max_group_size = 0

        for group in duplicate_groups:
            files = group.get("files", [])
            group_count = len(files)

            if group_count > 1:
                total_duplicates += group_count

                # Calculate wasted space
                first_file = Path(files[0]) if isinstance(files[0], str) else files[0]
                if first_file.exists():
                    file_size = first_file.stat().st_size
                    group_wasted = (group_count - 1) * file_size
                    space_wasted += group_wasted

                    # Track by type
                    file_type = first_file.suffix.lower() or "no_extension"
                    by_type[file_type] = by_type.get(file_type, 0) + (group_count - 1)

                    # Track largest group
                    if group_wasted > max_group_size:
                        max_group_size = group_wasted
                        largest_group = {
                            "files": files,
                            "size": file_size,
                            "count": group_count,
                            "wasted": group_wasted,
                        }

        return DuplicateStats(
            total_duplicates=total_duplicates,
            duplicate_groups=len(duplicate_groups),
            space_wasted=space_wasted,
            space_recoverable=space_wasted,
            by_type=by_type,
            largest_duplicate_group=largest_group,
        )

    def get_quality_metrics(
        self, directory: Path, total_files: int, organized_size: int
    ) -> QualityMetrics:
        """
        Calculate organization quality metrics.

        Args:
            directory: Directory to analyze
            total_files: Total number of files
            organized_size: Size of organized files

        Returns:
            QualityMetrics object
        """
        logger.info("Calculating quality metrics")

        # Collect files for analysis
        files = list(directory.rglob("*"))
        file_paths = [f for f in files if f.is_file()]

        # Calculate individual metrics
        naming_compliance = self.metrics_calculator.measure_naming_compliance(
            file_paths[:1000]  # Sample for performance
        )

        # Structure consistency: check if files are in organized subdirectories
        organized_files = sum(1 for f in file_paths if len(f.relative_to(directory).parts) > 1)
        structure_consistency = organized_files / max(total_files, 1)

        # Metadata completeness: estimate based on file properties
        # In a real implementation, this would check for tags, descriptions, etc.
        metadata_completeness = 0.5  # Placeholder

        # Categorization accuracy: estimate based on directory structure
        categorization_accuracy = 0.7  # Placeholder

        # Calculate overall quality score
        quality_score = self.metrics_calculator.calculate_quality_score(
            total_files=total_files,
            organized_files=organized_files,
            naming_compliance=naming_compliance,
            structure_consistency=structure_consistency,
        )

        return QualityMetrics(
            quality_score=quality_score,
            naming_compliance=naming_compliance,
            structure_consistency=structure_consistency,
            metadata_completeness=metadata_completeness,
            categorization_accuracy=categorization_accuracy,
        )

    def calculate_time_saved(
        self, total_files: int, duplicates_removed: int
    ) -> TimeSavings:
        """
        Calculate time saved through automation.

        Args:
            total_files: Total number of files processed
            duplicates_removed: Number of duplicates removed

        Returns:
            TimeSavings object
        """
        logger.info("Calculating time savings")

        # Estimate operations
        total_operations = total_files
        automated_operations = total_files  # All file processing is automated

        # Estimate time per operation
        # Manual file organization: ~30 seconds per file
        # Duplicate detection: ~60 seconds per duplicate manually
        avg_manual_time_per_file = 30  # seconds
        avg_manual_time_per_duplicate = 60  # seconds

        manual_time = (
            total_files * avg_manual_time_per_file
            + duplicates_removed * avg_manual_time_per_duplicate
        )

        # Automated time: ~1 second per file
        automated_time = total_files  # seconds

        # Time saved
        time_saved = max(0, manual_time - automated_time)

        return TimeSavings(
            total_operations=total_operations,
            automated_operations=automated_operations,
            manual_time_seconds=manual_time,
            automated_time_seconds=automated_time,
            estimated_time_saved_seconds=time_saved,
        )

    def export_dashboard(
        self, dashboard: AnalyticsDashboard, output_path: Path, format: str = "json"
    ) -> None:
        """
        Export dashboard to file.

        Args:
            dashboard: Dashboard to export
            output_path: Output file path
            format: Export format ('json' or 'text')
        """
        logger.info(f"Exporting dashboard to {output_path} as {format}")

        if format == "json":
            import json

            with open(output_path, "w") as f:
                json.dump(dashboard.to_dict(), f, indent=2)

        elif format == "text":
            with open(output_path, "w") as f:
                f.write(self._format_dashboard_text(dashboard))

        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Dashboard exported to {output_path}")

    def _format_dashboard_text(self, dashboard: AnalyticsDashboard) -> str:
        """
        Format dashboard as plain text.

        Args:
            dashboard: Dashboard to format

        Returns:
            Formatted text string
        """
        lines = [
            "=" * 70,
            "File Organizer Analytics Dashboard",
            "=" * 70,
            "",
            "STORAGE STATISTICS",
            "-" * 70,
            f"Total Size: {dashboard.storage_stats.formatted_total_size}",
            f"Files: {dashboard.storage_stats.file_count}",
            f"Directories: {dashboard.storage_stats.directory_count}",
            f"Space Saved: {dashboard.storage_stats.formatted_saved_size}",
            f"Savings: {dashboard.storage_stats.savings_percentage:.1f}%",
            "",
            "QUALITY METRICS",
            "-" * 70,
            f"Quality Score: {dashboard.quality_metrics.formatted_score}",
            f"Naming Compliance: {dashboard.quality_metrics.naming_compliance * 100:.1f}%",
            f"Structure Consistency: {dashboard.quality_metrics.structure_consistency * 100:.1f}%",
            "",
            "DUPLICATE STATISTICS",
            "-" * 70,
            f"Duplicate Groups: {dashboard.duplicate_stats.duplicate_groups}",
            f"Total Duplicates: {dashboard.duplicate_stats.total_duplicates}",
            f"Space Wasted: {dashboard.duplicate_stats.formatted_space_wasted}",
            f"Recoverable: {dashboard.duplicate_stats.formatted_recoverable}",
            "",
            "TIME SAVINGS",
            "-" * 70,
            f"Automation Rate: {dashboard.time_savings.automation_percentage:.1f}%",
            f"Time Saved: {dashboard.time_savings.formatted_time_saved}",
            f"Total Operations: {dashboard.time_savings.total_operations}",
            "",
            "FILE DISTRIBUTION",
            "-" * 70,
            f"Total Files: {dashboard.file_distribution.total_files}",
            f"File Types: {len(dashboard.file_distribution.by_type)}",
            "",
            f"Generated: {dashboard.generated_at.isoformat()}",
            "=" * 70,
        ]

        return "\n".join(lines)
