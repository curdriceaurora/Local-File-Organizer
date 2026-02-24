"""Result dataclasses for parallel file processing.

This module defines data structures for tracking individual file processing
results and aggregated batch results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FileResult:
    """Result of processing a single file.

    Attributes:
        path: Path to the file that was processed.
        success: Whether processing completed successfully.
        result: Return value from the processing function.
        error: Error message if processing failed.
        duration_ms: Time taken to process this file in milliseconds.
    """

    path: Path
    success: bool
    result: Any = None
    error: str | None = None
    duration_ms: float = 0.0

    def __str__(self) -> str:
        """String representation of file result."""
        if self.success:
            return f"OK {self.path} ({self.duration_ms:.1f}ms)"
        return f"FAIL {self.path}: {self.error} ({self.duration_ms:.1f}ms)"


@dataclass
class BatchResult:
    """Aggregated result of processing a batch of files.

    Attributes:
        total: Total number of files in the batch.
        succeeded: Number of files that processed successfully.
        failed: Number of files that failed processing.
        results: List of individual file results.
        total_duration_ms: Wall-clock time for the entire batch in milliseconds.
        files_per_second: Throughput metric for the batch.
    """

    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: list[FileResult] = field(default_factory=list)
    total_duration_ms: float = 0.0
    files_per_second: float = 0.0

    def summary(self) -> str:
        """Generate a human-readable summary of the batch result.

        Returns:
            Multi-line summary string with counts, timing, and failure details.
        """
        lines: list[str] = [
            f"Batch complete: {self.total} files in {self.total_duration_ms:.1f}ms",
            f"  Succeeded: {self.succeeded}",
            f"  Failed: {self.failed}",
            f"  Throughput: {self.files_per_second:.2f} files/sec",
        ]

        failures = [r for r in self.results if not r.success]
        if failures:
            lines.append("  Failures:")
            for failure in failures[:5]:
                lines.append(f"    - {failure.path}: {failure.error}")
            if len(failures) > 5:
                lines.append(f"    ... and {len(failures) - 5} more")

        return "\n".join(lines)

    def __str__(self) -> str:
        """String representation of batch result."""
        return self.summary()
