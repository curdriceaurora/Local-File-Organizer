"""
Pipeline configuration for auto-organization.

Defines the PipelineConfig dataclass that controls how the auto-organization
pipeline behaves, including watch integration, output paths, concurrency,
and dry-run safety defaults.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from file_organizer.watcher import WatcherConfig


# Default file extensions supported by the pipeline
DEFAULT_SUPPORTED_EXTENSIONS: frozenset[str] = frozenset(
    {
        # Text
        ".txt",
        ".md",
        ".docx",
        ".doc",
        ".pdf",
        ".csv",
        ".xlsx",
        ".xls",
        ".ppt",
        ".pptx",
        ".epub",
        # Images
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
        # Video
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".wmv",
        # Audio
        ".mp3",
        ".wav",
        ".flac",
        ".m4a",
        ".ogg",
        # CAD
        ".dwg",
        ".dxf",
        ".step",
        ".stp",
        ".iges",
        ".igs",
    }
)


@dataclass
class PipelineConfig:
    """
    Configuration for the auto-organization pipeline.

    Controls how files are discovered, processed, and organized. Defaults to
    safe operation: dry-run enabled, auto-organize disabled.

    Attributes:
        watch_config: Optional watcher configuration for real-time monitoring.
            When None, the pipeline operates in batch mode only.
        output_directory: Base directory where organized files are placed.
        dry_run: If True, simulate all file operations without moving files.
            Defaults to True for safety.
        auto_organize: If True, automatically move files after processing.
            Requires dry_run=False to take effect.
        notification_callback: Optional callable invoked when processing
            completes for a file. Receives the file path and success status.
        supported_extensions: Set of file extensions to process. Files with
            extensions not in this set are skipped. None means use defaults.
        max_concurrent: Maximum number of files to process concurrently.
            Must be at least 1.
    """

    watch_config: WatcherConfig | None = None
    output_directory: Path = field(default_factory=lambda: Path("organized_files"))
    dry_run: bool = True
    auto_organize: bool = False
    notification_callback: Callable[[Path, bool], None] | None = None
    supported_extensions: set[str] | None = None
    max_concurrent: int = 4

    def __post_init__(self) -> None:
        """Validate and normalize configuration after initialization."""
        # Normalize output_directory to Path
        self.output_directory = Path(self.output_directory)

        # Validate max_concurrent
        if self.max_concurrent < 1:
            raise ValueError(f"max_concurrent must be at least 1, got {self.max_concurrent}")

        # Normalize supported extensions to include leading dots
        if self.supported_extensions is not None:
            self.supported_extensions = {
                ext if ext.startswith(".") else f".{ext}" for ext in self.supported_extensions
            }

    @property
    def effective_extensions(self) -> frozenset[str]:
        """Return the effective set of supported extensions.

        Uses the configured supported_extensions if set, otherwise falls
        back to DEFAULT_SUPPORTED_EXTENSIONS.

        Returns:
            Frozenset of file extensions (with leading dots).
        """
        if self.supported_extensions is not None:
            return frozenset(self.supported_extensions)
        return DEFAULT_SUPPORTED_EXTENSIONS

    @property
    def should_move_files(self) -> bool:
        """Return True if the pipeline should actually move/copy files.

        Files are only moved when both dry_run is False and auto_organize
        is True. This provides a double-safety mechanism.

        Returns:
            True if file moves should be performed.
        """
        return not self.dry_run and self.auto_organize

    def is_supported(self, file_path: Path) -> bool:
        """Check if a file's extension is supported by the pipeline.

        Args:
            file_path: Path to the file to check.

        Returns:
            True if the file's extension is in the supported set.
        """
        return file_path.suffix.lower() in self.effective_extensions
