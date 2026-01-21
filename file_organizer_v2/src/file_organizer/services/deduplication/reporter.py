"""
Storage reclamation reporter.

Generates reports on duplicate detection and storage savings.
"""

from pathlib import Path
from typing import Dict, List
import json
import csv
import logging

logger = logging.getLogger(__name__)


class StorageReporter:
    """Generates reports on storage usage and duplicate detection."""

    def __init__(self):
        """Initialize the storage reporter."""
        pass

    def calculate_reclamation(self, duplicate_groups: List[Dict]) -> Dict:
        """
        Calculate storage reclamation metrics.

        Args:
            duplicate_groups: List of duplicate groups

        Returns:
            Dictionary with reclamation metrics
        """
        total_files = sum(g['count'] for g in duplicate_groups)
        total_size = sum(g['total_size'] for g in duplicate_groups)

        # Recoverable = keep one file per group, delete rest
        recoverable = sum(
            g['total_size'] - (g['total_size'] / g['count'])
            for g in duplicate_groups
        )

        metrics = {
            'total_duplicate_files': total_files,
            'total_duplicate_groups': len(duplicate_groups),
            'total_size': total_size,
            'recoverable_space': int(recoverable),
            'recovery_percentage': (recoverable / total_size * 100) if total_size > 0 else 0
        }

        return metrics

    def generate_report(
        self,
        duplicate_results: Dict,
        output_format: str = 'text'
    ) -> str:
        """
        Generate duplicate detection report.

        Args:
            duplicate_results: Results from DocumentDeduplicator
            output_format: Output format ('text', 'json')

        Returns:
            Formatted report string
        """
        if output_format == 'json':
            return json.dumps(duplicate_results, indent=2, default=str)

        # Text format
        lines = ["=" * 60]
        lines.append("DOCUMENT DEDUPLICATION REPORT")
        lines.append("=" * 60)

        lines.append(f"\nTotal documents analyzed: {duplicate_results['analyzed_documents']}")
        lines.append(f"Duplicate groups found: {duplicate_results['num_groups']}")
        lines.append(f"Space wasted: {duplicate_results['space_wasted'] / (1024*1024):.2f} MB")

        lines.append("\n" + "-" * 60)
        lines.append("DUPLICATE GROUPS")
        lines.append("-" * 60)

        for i, group in enumerate(duplicate_results['duplicate_groups'], 1):
            lines.append(f"\nGroup {i}:")
            lines.append(f"  Files: {group['count']}")
            lines.append(f"  Similarity: {group['avg_similarity']:.2%}")
            lines.append(f"  Total size: {group['total_size'] / (1024*1024):.2f} MB")
            lines.append(f"  Representative: {Path(group['representative']).name}")

            for file_path in group['files'][:5]:  # Show first 5
                lines.append(f"    - {Path(file_path).name}")

            if len(group['files']) > 5:
                lines.append(f"    ... and {len(group['files']) - 5} more")

        return "\n".join(lines)

    def export_to_csv(
        self,
        duplicate_groups: List[Dict],
        output_path: Path
    ) -> None:
        """
        Export duplicate groups to CSV.

        Args:
            duplicate_groups: List of duplicate groups
            output_path: Output CSV file path
        """
        try:
            with open(output_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)

                # Header
                writer.writerow([
                    'Group ID',
                    'File Count',
                    'Avg Similarity',
                    'Total Size (MB)',
                    'Representative',
                    'All Files'
                ])

                # Data rows
                for i, group in enumerate(duplicate_groups, 1):
                    writer.writerow([
                        i,
                        group['count'],
                        f"{group['avg_similarity']:.2%}",
                        f"{group['total_size'] / (1024*1024):.2f}",
                        Path(group['representative']).name,
                        ';'.join([Path(f).name for f in group['files']])
                    ])

            logger.info(f"Exported duplicate report to {output_path}")

        except Exception as e:
            logger.error(f"Error exporting to CSV: {e}")
            raise

    def export_to_json(
        self,
        duplicate_results: Dict,
        output_path: Path
    ) -> None:
        """
        Export results to JSON.

        Args:
            duplicate_results: Results dictionary
            output_path: Output JSON file path
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(duplicate_results, f, indent=2, default=str)

            logger.info(f"Exported duplicate report to {output_path}")

        except Exception as e:
            logger.error(f"Error exporting to JSON: {e}")
            raise
