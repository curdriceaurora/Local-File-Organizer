"""
Configuration for parallel file processing.

This module defines the configuration dataclass controlling parallelism,
timeouts, retry behavior, and progress reporting.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from file_organizer._compat import StrEnum


class ExecutorType(StrEnum):
    """Type of executor to use for parallel processing."""

    PROCESS = "process"
    THREAD = "thread"


@dataclass
class ParallelConfig:
    """
    Configuration for the parallel processor.

    Attributes:
        max_workers: Maximum number of worker threads/processes.
            None means use os.cpu_count().
        executor_type: Whether to use process or thread pool.
            Use "process" for CPU-bound work, "thread" for IO-bound work.
        chunk_size: Number of files to submit per scheduling round.
        timeout_per_file: Maximum seconds allowed per file before timeout.
        retry_count: Number of retry attempts for failed files.
        progress_callback: Optional callback invoked after each file completes.
            Signature: callback(completed: int, total: int, result: FileResult) -> None.
    """

    max_workers: int | None = None
    executor_type: ExecutorType = ExecutorType.THREAD
    chunk_size: int = 10
    timeout_per_file: float = 60.0
    retry_count: int = 2
    progress_callback: Callable[..., Any] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Validate configuration values after initialization."""
        if self.max_workers is not None and self.max_workers < 1:
            raise ValueError(f"max_workers must be >= 1, got {self.max_workers}")
        if self.chunk_size < 1:
            raise ValueError(f"chunk_size must be >= 1, got {self.chunk_size}")
        if self.timeout_per_file <= 0:
            raise ValueError(f"timeout_per_file must be > 0, got {self.timeout_per_file}")
        if self.retry_count < 0:
            raise ValueError(f"retry_count must be >= 0, got {self.retry_count}")
