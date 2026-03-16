"""Analytics service - orchestrates all analytics components.

Main service that coordinates storage analysis, metrics calculation,
chart generation, and dashboard creation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ...models.analytics import (
    AnalyticsDashboard,
    DuplicateStats,
    QualityMetrics,
    StorageStats,
    TimeSavings,
)
from .metrics_calculator import MetricsCalculator
from .storage_analyzer import StorageAnalyzer

logger = logging.getLogger(__name__)

# Extensions considered to have sufficient content-type metadata for reliable
# downstream processing.  Defined at module level to avoid recreation per call.
_KNOWN_EXTENSIONS = {
    ".txt",
    ".pdf",
    ".doc",
    ".docx",
    ".md",
    ".rst",
    ".jpg",
    ".jpeg",
    ".png",
    ".gif",
    ".svg",
    ".webp",
    ".mp3",
    ".wav",
    ".mp4",
    ".mov",
    ".avi",
    ".py",
    ".js",
    ".ts",
    ".java",
    ".go",
    ".rs",
    ".cpp",
    ".c",
    ".h",
    ".csv",
    ".json",
    ".xml",
    ".yaml",
    ".yml",
    ".toml",
    ".zip",
    ".tar",
    ".gz",
}


class AnalyticsService:
    """Main analytics service that orchestrates all analytics components.

    Coordinates:
    - Storage analysis
    - Quality metrics calculation
    - Duplicate statistics
    - Time savings estimation
    - Dashboard generation
    """

    def __init__(
        self,
        storage_analyzer: StorageAnalyzer | None = None,
        metrics_calculator: MetricsCalculator | None = None,
    ):
        """Initialize analytics service.

        Args:
            storage_analyzer: Storage analyzer instance (creates new if None)
            metrics_calculator: Metrics calculator instance (creates new if None)
        """
        self.storage_analyzer = storage_analyzer or StorageAnalyzer()
        self.metrics_calculator = metrics_calculator or MetricsCalculator()

    def generate_dashboard(
        self,
        directory: Path,
        duplicate_groups: list[dict[str, Any]] | None = None,
        max_depth: int | None = None,
    ) -> AnalyticsDashboard:
        """Generate complete analytics dashboard.

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
        duplicate_stats = self.get_duplicate_stats(duplicate_groups or [], storage_stats.total_size)

        # Get quality metrics
        quality_metrics = self.get_quality_metrics(directory, max_depth=max_depth)

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
            generated_at=datetime.now(UTC),
        )

        logger.info("Dashboard generation complete")
        return dashboard

    def get_storage_stats(self, directory: Path, max_depth: int | None = None) -> StorageStats:
        """Get storage usage statistics.

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
        self, duplicate_groups: list[dict[str, Any]], total_size: int
    ) -> DuplicateStats:
        """Get duplication statistics.

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
        actual_duplicate_groups = 0
        space_wasted = 0
        by_type: dict[str, int] = {}
        largest_group = None
        max_group_size = 0

        for group in duplicate_groups:
            files = group.get("files", [])
            group_count = len(files)

            if group_count > 1:
                # Count only the extra copies (exclude one original per group)
                extra_copies = group_count - 1
                total_duplicates += extra_copies
                actual_duplicate_groups += 1

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
            duplicate_groups=actual_duplicate_groups,
            space_wasted=space_wasted,
            space_recoverable=space_wasted,
            by_type=by_type,
            largest_duplicate_group=largest_group,
        )

    def get_quality_metrics(
        self,
        directory: Path,
        max_depth: int | None = None,
    ) -> QualityMetrics:
        """Calculate organization quality metrics.

        Computes four scores, all clamped to [0.0, 1.0]:
        - naming_compliance: fraction of files following lowercase/delimiter conventions
        - structure_consistency: fraction of files placed in subdirectories
        - metadata_completeness: fraction of files with a recognized extension and
          non-trivial stem (proxy for content-type discoverability)
        - categorization_accuracy: fraction of files in subdirectories that have
          at least 2 sibling files (proxy for intentional grouping)

        Args:
            directory: Directory to analyze
            max_depth: Maximum directory depth to traverse (None = unlimited).
                Must match the depth used when computing storage statistics to
                ensure consistent denominators across all metrics.

        Returns:
            QualityMetrics object with all scores in [0.0, 1.0]
        """
        logger.info("Calculating quality metrics")

        # Collect files using the same depth limit as storage analysis so that
        # all metric denominators are consistent with storage_stats.file_count.
        file_paths = [
            p for p in self.storage_analyzer.walk_directory(directory, max_depth) if p.is_file()
        ]

        # Calculate individual metrics
        naming_compliance = self.metrics_calculator.measure_naming_compliance(
            file_paths[:1000]  # Sample for performance
        )

        # Single pass: compute organized_files, files_with_metadata, and dir_file_counts
        # together to avoid iterating file_paths multiple times.
        organized_files = 0
        files_with_metadata = 0
        dir_file_counts: dict[Path, int] = {}
        for f in file_paths:
            if len(f.relative_to(directory).parts) > 1:
                organized_files += 1
            if f.suffix.lower() in _KNOWN_EXTENSIONS and f.stem and not f.stem.isdigit():
                files_with_metadata += 1
            dir_file_counts[f.parent] = dir_file_counts.get(f.parent, 0) + 1

        n = max(len(file_paths), 1)
        structure_consistency = min(1.0, organized_files / n)

        # Metadata completeness: fraction of files with a recognized extension and
        # a non-trivial stem (not purely numeric).  Files that match both criteria
        # carry enough content-type metadata for reliable downstream processing.
        metadata_completeness = min(1.0, files_with_metadata / n)

        # Categorization accuracy: fraction of files that are in subdirectories
        # with at least 2 sibling files.  Single-file "folders" suggest random
        # scatter rather than intentional grouping; directories with multiple
        # files suggest the organizer placed related content together.
        well_categorized = sum(
            1 for f in file_paths if f.parent != directory and dir_file_counts.get(f.parent, 0) >= 2
        )
        categorization_accuracy = min(1.0, well_categorized / n)

        # Calculate overall quality score
        quality_score = self.metrics_calculator.calculate_quality_score(
            total_files=len(file_paths),
            organized_files=organized_files,
            naming_compliance=naming_compliance,
            structure_consistency=structure_consistency,
        )

        return QualityMetrics(
            quality_score=quality_score,  # already clamped to [0, 100] by calculate_quality_score
            naming_compliance=naming_compliance,
            structure_consistency=structure_consistency,
            metadata_completeness=metadata_completeness,
            categorization_accuracy=categorization_accuracy,
        )

    def calculate_time_saved(self, total_files: int, duplicates_removed: int) -> TimeSavings:
        """Calculate time saved through automation.

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
        """Export dashboard to file.

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
        """Format dashboard as plain text.

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
