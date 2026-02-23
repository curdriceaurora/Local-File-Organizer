"""Configuration for the background daemon.

Defines the DaemonConfig dataclass that controls daemon behavior
including watch directories, output paths, PID management, logging,
and concurrency settings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DaemonConfig:
    """Configuration for the background daemon service.

    Controls which directories to watch, where organized files are placed,
    daemon lifecycle settings, and processing behavior.

    Attributes:
        watch_directories: List of directory paths to monitor for new files.
        output_directory: Base directory for organized output.
        pid_file: Path to the PID file for daemon tracking. None disables
            PID file management.
        log_file: Path to the daemon log file. None means log to stderr.
        dry_run: If True, simulate file operations without moving files.
            Defaults to True for safety.
        poll_interval: Seconds between event polling cycles. Must be positive.
        max_concurrent: Maximum number of files to process concurrently.
            Must be at least 1.
    """

    watch_directories: list[Path] = field(default_factory=list)
    output_directory: Path = field(default_factory=lambda: Path("organized_files"))
    pid_file: Path | None = None
    log_file: Path | None = None
    dry_run: bool = True
    poll_interval: float = 1.0
    max_concurrent: int = 4

    def __post_init__(self) -> None:
        """Validate and normalize configuration after initialization."""
        # Normalize paths
        self.watch_directories = [Path(p) for p in self.watch_directories]
        self.output_directory = Path(self.output_directory)

        if self.pid_file is not None:
            self.pid_file = Path(self.pid_file)
        if self.log_file is not None:
            self.log_file = Path(self.log_file)

        # Validate poll_interval
        if self.poll_interval <= 0:
            raise ValueError(f"poll_interval must be positive, got {self.poll_interval}")

        # Validate max_concurrent
        if self.max_concurrent < 1:
            raise ValueError(f"max_concurrent must be at least 1, got {self.max_concurrent}")
