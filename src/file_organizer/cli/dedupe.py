#!/usr/bin/env python3
"""Deduplication CLI - Interactive duplicate file detection and removal.

This module provides a user-friendly command-line interface for finding and
removing duplicate files using hash-based detection.

``dedupe_command`` is the public API for the deduplication workflow. It
delegates to extracted modules for specific concerns:

- ``cli.dedupe_hash``: Hash computation and duplicate scanning
- ``cli.dedupe_strategy``: File selection strategy logic
- ``cli.dedupe_display``: Rich UI output (tables, panels, formatting)
- ``cli.dedupe_removal``: File deletion and backup operations
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from loguru import logger
from rich.console import Console

from file_organizer.cli import dedupe_display, dedupe_removal
from file_organizer.cli.dedupe_display import format_datetime, format_size  # noqa: F401
from file_organizer.cli.dedupe_hash import (
    ProgressTracker,
    create_scan_options,
    initialize_hash_detector,
    scan_for_duplicates,
)
from file_organizer.cli.dedupe_strategy import (  # noqa: F401
    get_user_selection,
    select_files_to_keep,
)

console = Console()


class DedupeConfig:
    """Configuration for deduplication operation."""

    def __init__(
        self,
        directory: Path,
        algorithm: str = "sha256",
        dry_run: bool = False,
        strategy: str = "manual",
        safe_mode: bool = True,
        recursive: bool = True,
        batch: bool = False,
        min_size: int = 0,
        max_size: int | None = None,
        include_patterns: list[str] | None = None,
        exclude_patterns: list[str] | None = None,
    ):
        """Initialize deduplication configuration.

        Args:
            directory: Directory to scan for duplicates
            algorithm: Hash algorithm to use ('md5' or 'sha256')
            dry_run: If True, don't actually delete files
            strategy: Duplicate removal strategy ('manual', 'oldest', 'newest', 'largest', 'smallest')
            safe_mode: If True, create backups before deletion
            recursive: If True, scan subdirectories
            batch: If True, apply strategy automatically without per-group confirmation
            min_size: Minimum file size to consider (bytes)
            max_size: Maximum file size to consider (bytes, None for unlimited)
            include_patterns: File patterns to include (e.g., ['*.jpg', '*.png'])
            exclude_patterns: File patterns to exclude
        """
        self.directory = directory
        self.algorithm = algorithm
        self.dry_run = dry_run
        self.strategy = strategy
        self.safe_mode = safe_mode
        self.recursive = recursive
        self.batch = batch
        self.min_size = min_size
        self.max_size = max_size
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []


def dedupe_command(args: list[str] | None = None) -> int:
    """Execute the dedupe command.

    Args:
        args: Command-line arguments (None to use sys.argv)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="Find and remove duplicate files using hash-based detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Find duplicates in current directory (dry run)
  python -m file_organizer.cli.dedupe . --dry-run

  # Remove duplicates interactively
  python -m file_organizer.cli.dedupe ~/Documents --strategy manual

  # Auto-remove duplicates, keeping oldest files
  python -m file_organizer.cli.dedupe ~/Downloads --strategy oldest

  # Find duplicates with SHA256, non-recursive
  python -m file_organizer.cli.dedupe . --algorithm sha256 --no-recursive

  # Find large duplicate files only (>10MB)
  python -m file_organizer.cli.dedupe ~/Videos --min-size 10485760
        """,
    )

    parser.add_argument("directory", type=str, help="Directory to scan for duplicate files")

    parser.add_argument(
        "--algorithm",
        type=str,
        choices=["md5", "sha256"],
        default="sha256",
        help="Hash algorithm to use (default: sha256)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without actually deleting files",
    )

    parser.add_argument(
        "--strategy",
        type=str,
        choices=["manual", "oldest", "newest", "largest", "smallest"],
        default="manual",
        help="Strategy for selecting which duplicates to keep (default: manual)",
    )

    parser.add_argument(
        "--batch",
        action="store_true",
        help="Batch mode: automatically apply strategy without confirmation for each group",
    )

    parser.add_argument(
        "--no-safe-mode",
        action="store_true",
        help="Disable automatic backups before deletion (not recommended)",
    )

    parser.add_argument("--no-recursive", action="store_true", help="Don't scan subdirectories")

    parser.add_argument(
        "--min-size",
        type=int,
        default=0,
        help="Minimum file size to consider in bytes (default: 0)",
    )

    parser.add_argument(
        "--max-size",
        type=int,
        default=None,
        help="Maximum file size to consider in bytes (default: unlimited)",
    )

    parser.add_argument(
        "--include",
        type=str,
        action="append",
        help="File patterns to include (e.g., '*.jpg'). Can be specified multiple times.",
    )

    parser.add_argument(
        "--exclude",
        type=str,
        action="append",
        help="File patterns to exclude (e.g., '*.tmp'). Can be specified multiple times.",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    parsed_args = parser.parse_args(args)

    # Configure logging
    if parsed_args.verbose:
        logger.remove()
        logger.add(sys.stderr, level="DEBUG")
    else:
        logger.remove()
        logger.add(sys.stderr, level="INFO", format="<level>{level: <8}</level> | {message}")

    # Validate directory
    directory = Path(parsed_args.directory).resolve()
    if not directory.exists():
        console.print(f"[red]Error: Directory not found: {directory}[/red]")
        return 1

    if not directory.is_dir():
        console.print(f"[red]Error: Not a directory: {directory}[/red]")
        return 1

    # Create configuration
    config = DedupeConfig(
        directory=directory,
        algorithm=parsed_args.algorithm,
        dry_run=parsed_args.dry_run,
        strategy=parsed_args.strategy,
        safe_mode=not parsed_args.no_safe_mode,
        recursive=not parsed_args.no_recursive,
        batch=parsed_args.batch,
        min_size=parsed_args.min_size,
        max_size=parsed_args.max_size,
        include_patterns=parsed_args.include or [],
        exclude_patterns=parsed_args.exclude or [],
    )

    # Display banner and configuration
    dedupe_display.display_banner(console)
    dedupe_display.display_config(
        console,
        str(config.directory),
        config.algorithm,
        config.strategy,
        config.recursive,
        config.safe_mode,
        config.dry_run,
        config.batch,
    )

    try:
        # Import deduplication services
        from file_organizer.services.deduplication.backup import BackupManager
        from file_organizer.services.deduplication.hasher import HashAlgorithm

        # Initialize detector and backup manager
        detector = initialize_hash_detector()
        backup_manager = BackupManager(config.directory) if config.safe_mode else None

        console.print("[bold]Step 1: Scanning for files...[/bold]")

        # Create progress tracker and scan options
        progress_tracker = ProgressTracker(console)
        scan_options = create_scan_options(
            algorithm=cast("HashAlgorithm", config.algorithm),
            recursive=config.recursive,
            min_file_size=config.min_size,
            max_file_size=config.max_size,
            file_patterns=config.include_patterns if config.include_patterns else None,
            exclude_patterns=config.exclude_patterns if config.exclude_patterns else None,
            progress_callback=progress_tracker.callback if progress_tracker.has_tqdm else None,
        )

        # Scan directory for duplicates
        duplicate_groups = scan_for_duplicates(
            config.directory, detector, scan_options, console, progress_tracker
        )

        if not duplicate_groups:
            return 0

        # Calculate totals
        total_groups = len(duplicate_groups)
        total_duplicates = sum(group.count for group in duplicate_groups.values())
        total_removed = 0
        space_saved = 0

        # Process each duplicate group
        for group_id, (file_hash, group) in enumerate(duplicate_groups.items(), 1):
            removed, saved = dedupe_removal.process_duplicate_group(
                group_id=group_id,
                file_hash=file_hash,
                group=group,
                total_groups=total_groups,
                strategy=config.strategy,
                batch=config.batch,
                backup_manager=backup_manager,
                dry_run=config.dry_run,
                console=console,
            )
            total_removed += removed
            space_saved += saved

        # Display summary
        dedupe_display.display_summary(
            console,
            total_groups,
            total_duplicates,
            total_removed,
            space_saved,
            config.dry_run,
        )

        # Display backup information
        if config.safe_mode and not config.dry_run and total_removed > 0:
            dedupe_display.display_backup_info(console)

        return 0

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Operation cancelled by user[/yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.exception("Deduplication failed")
        return 1


def main() -> None:
    """Main entry point for standalone execution."""
    sys.exit(dedupe_command())


if __name__ == "__main__":
    main()
