"""
Metrics calculation module for quality scoring and efficiency analysis.
"""

from typing import Dict, List, Optional
from pathlib import Path
import logging

from ...models.analytics import QualityMetrics, TimeSavings

logger = logging.getLogger(__name__)


class MetricsCalculator:
    """Calculates quality metrics and efficiency gains."""

    def __init__(self):
        """Initialize the metrics calculator."""
        pass

    def calculate_quality_score(
        self,
        total_files: int,
        organized_files: int,
        naming_compliance: float,
        structure_consistency: float
    ) -> float:
        """
        Calculate overall organization quality score (0-100).

        Args:
            total_files: Total number of files
            organized_files: Number of organized files
            naming_compliance: Naming compliance score (0-1)
            structure_consistency: Structure consistency score (0-1)

        Returns:
            Quality score from 0-100
        """
        if total_files == 0:
            return 0.0

        organization_rate = organized_files / total_files

        # Weighted average
        score = (
            organization_rate * 0.4 +
            naming_compliance * 0.3 +
            structure_consistency * 0.3
        ) * 100

        return min(100.0, max(0.0, score))

    def measure_naming_compliance(
        self,
        files: List[Path],
        pattern: Optional[Dict] = None
    ) -> float:
        """
        Measure naming convention compliance.

        Args:
            files: List of file paths
            pattern: Expected naming pattern

        Returns:
            Compliance score (0-1)
        """
        if not files:
            return 1.0

        compliant = 0

        for file_path in files:
            # Simple heuristic: lowercase, no spaces, proper delimiter
            name = file_path.stem
            if name.islower() or '_' in name or '-' in name:
                if ' ' not in name:
                    compliant += 1

        return compliant / len(files)

    def calculate_efficiency_gain(
        self,
        before_operations: int,
        after_operations: int
    ) -> float:
        """
        Calculate efficiency gain percentage.

        Args:
            before_operations: Operations before optimization
            after_operations: Operations after optimization

        Returns:
            Efficiency gain percentage
        """
        if before_operations == 0:
            return 0.0

        gain = ((before_operations - after_operations) / before_operations) * 100
        return max(0.0, gain)

    def estimate_time_saved(
        self,
        automated_ops: int,
        avg_manual_time_per_op: int = 30
    ) -> int:
        """
        Estimate time saved through automation.

        Args:
            automated_ops: Number of automated operations
            avg_manual_time_per_op: Average manual time per operation (seconds)

        Returns:
            Estimated time saved in seconds
        """
        return automated_ops * avg_manual_time_per_op

    def calculate_improvement_metrics(
        self,
        current_score: float,
        previous_score: Optional[float] = None
    ) -> Dict:
        """
        Calculate improvement metrics.

        Args:
            current_score: Current quality score
            previous_score: Previous quality score

        Returns:
            Dictionary with improvement metrics
        """
        metrics = {
            'current_score': current_score,
            'improvement': 0.0,
            'trend': 'stable'
        }

        if previous_score is not None:
            metrics['improvement'] = current_score - previous_score
            if metrics['improvement'] > 1:
                metrics['trend'] = 'improving'
            elif metrics['improvement'] < -1:
                metrics['trend'] = 'declining'

        return metrics
