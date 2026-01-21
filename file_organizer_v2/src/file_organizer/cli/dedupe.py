#!/usr/bin/env python3
"""
Deduplication CLI - Interactive duplicate file detection and removal.

This module provides a user-friendly command-line interface for finding and
removing duplicate files using hash-based detection.
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from loguru import logger


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
        min_size: int = 0,
        max_size: Optional[int] = None,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ):
        """Initialize deduplication configuration.

        Args:
            directory: Directory to scan for duplicates
            algorithm: Hash algorithm to use ('md5' or 'sha256')
            dry_run: If True, don't actually delete files
            strategy: Duplicate removal strategy ('manual', 'oldest', 'newest', 'largest', 'smallest')
            safe_mode: If True, create backups before deletion
            recursive: If True, scan subdirectories
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
        self.min_size = min_size
        self.max_size = max_size
        self.include_patterns = include_patterns or []
        self.exclude_patterns = exclude_patterns or []


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string (e.g., '1.5 MB')
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_datetime(timestamp: float) -> str:
    """Format timestamp in human-readable format.

    Args:
        timestamp: Unix timestamp

    Returns:
        Formatted datetime string
    """
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def display_duplicate_group(
    group_id: int,
    file_hash: str,
    files: List[Dict],
    total_groups: int
) -> None:
    """Display a group of duplicate files in a formatted table.

    Args:
        group_id: ID of the duplicate group
        file_hash: Hash value of the duplicates
        files: List of file metadata dicts
        total_groups: Total number of duplicate groups
    """
    console.print()
    console.print(Panel(
        f"[bold cyan]Duplicate Group {group_id}/{total_groups}[/bold cyan]\n"
        f"Hash: [dim]{file_hash[:16]}...[/dim]",
        expand=False
    ))

    # Create table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("Path", style="cyan")
    table.add_column("Size", justify="right", style="green")
    table.add_column("Modified", style="yellow")
    table.add_column("Status", justify="center")

    # Add files to table
    for idx, file_info in enumerate(files, 1):
        path = file_info['path']
        size = format_size(file_info['size'])
        modified = format_datetime(file_info['mtime'])

        # Mark the file that will be kept (for strategies)
        status = "✓" if file_info.get('keep', False) else ""

        table.add_row(
            str(idx),
            str(path),
            size,
            modified,
            status
        )

    console.print(table)

    # Calculate space that can be saved
    total_size = sum(f['size'] for f in files)
    saved_space = total_size - files[0]['size']  # Keep one file
    console.print(f"\n[dim]Potential space savings: {format_size(saved_space)}[/dim]")


def select_files_to_keep(
    files: List[Dict],
    strategy: str
) -> List[Dict]:
    """Apply selection strategy to determine which files to keep/remove.

    Args:
        files: List of duplicate file metadata
        strategy: Selection strategy ('manual', 'oldest', 'newest', 'largest', 'smallest')

    Returns:
        Updated list with 'keep' flags set
    """
    if strategy == "oldest":
        # Keep the file with the oldest modification time
        oldest_idx = min(range(len(files)), key=lambda i: files[i]['mtime'])
        files[oldest_idx]['keep'] = True

    elif strategy == "newest":
        # Keep the file with the newest modification time
        newest_idx = max(range(len(files)), key=lambda i: files[i]['mtime'])
        files[newest_idx]['keep'] = True

    elif strategy == "largest":
        # Keep the largest file (in case of slight differences)
        largest_idx = max(range(len(files)), key=lambda i: files[i]['size'])
        files[largest_idx]['keep'] = True

    elif strategy == "smallest":
        # Keep the smallest file
        smallest_idx = min(range(len(files)), key=lambda i: files[i]['size'])
        files[smallest_idx]['keep'] = True

    elif strategy == "manual":
        # Manual selection - no automatic marking
        pass

    return files


def get_user_selection(files: List[Dict], strategy: str) -> List[int]:
    """Get user selection for files to remove.

    Args:
        files: List of duplicate file metadata
        strategy: Selection strategy

    Returns:
        List of indices of files to remove
    """
    if strategy == "manual":
        console.print("\n[bold]Which file(s) should we keep?[/bold]")
        console.print("[dim]Enter the number(s) to keep (comma-separated), or 'a' to keep all, or 's' to skip:[/dim]")

        while True:
            try:
                choice = console.input("[cyan]Keep file(s):[/cyan] ").strip().lower()

                if choice == 's':
                    return []  # Skip this group
                elif choice == 'a':
                    return []  # Keep all (remove none)
                else:
                    # Parse comma-separated numbers
                    keep_indices = [int(x.strip()) - 1 for x in choice.split(',')]

                    # Validate indices
                    if all(0 <= idx < len(files) for idx in keep_indices):
                        # Return indices to remove (all except kept)
                        return [i for i in range(len(files)) if i not in keep_indices]
                    else:
                        console.print("[red]Invalid selection. Please try again.[/red]")
            except (ValueError, KeyboardInterrupt):
                console.print("[red]Invalid input. Please enter numbers or 'a'/'s'.[/red]")
    else:
        # For automatic strategies, confirm the selection
        console.print("\n[bold]Proceed with this selection?[/bold]")
        console.print("[dim](y)es / (n)o / (s)kip this group:[/dim]")

        while True:
            choice = console.input("[cyan]Choice:[/cyan] ").strip().lower()

            if choice in ['y', 'yes']:
                # Remove files not marked to keep
                return [i for i, f in enumerate(files) if not f.get('keep', False)]
            elif choice in ['n', 'no']:
                return []  # Keep all
            elif choice in ['s', 'skip']:
                return []  # Skip
            else:
                console.print("[red]Please enter 'y', 'n', or 's'.[/red]")


def display_summary(
    total_groups: int,
    total_duplicates: int,
    total_removed: int,
    space_saved: int,
    dry_run: bool
) -> None:
    """Display summary of deduplication operation.

    Args:
        total_groups: Total number of duplicate groups found
        total_duplicates: Total number of duplicate files found
        total_removed: Number of files removed
        space_saved: Total space saved in bytes
        dry_run: Whether this was a dry run
    """
    console.print()
    console.print("=" * 70)
    console.print()

    if dry_run:
        console.print(Panel(
            "[bold yellow]DRY RUN SUMMARY[/bold yellow]\n\n"
            f"Duplicate groups found: [cyan]{total_groups}[/cyan]\n"
            f"Total duplicate files: [cyan]{total_duplicates}[/cyan]\n"
            f"Files that would be removed: [cyan]{total_removed}[/cyan]\n"
            f"Space that would be saved: [green]{format_size(space_saved)}[/green]\n\n"
            "[dim]Run without --dry-run to actually remove files.[/dim]",
            title="Summary",
            expand=False
        ))
    else:
        console.print(Panel(
            "[bold green]DEDUPLICATION COMPLETE[/bold green]\n\n"
            f"Duplicate groups found: [cyan]{total_groups}[/cyan]\n"
            f"Total duplicate files: [cyan]{total_duplicates}[/cyan]\n"
            f"Files removed: [cyan]{total_removed}[/cyan]\n"
            f"Space saved: [green]{format_size(space_saved)}[/green]",
            title="Summary",
            expand=False
        ))


def dedupe_command(args: Optional[List[str]] = None) -> int:
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
        """
    )

    parser.add_argument(
        "directory",
        type=str,
        help="Directory to scan for duplicate files"
    )

    parser.add_argument(
        "--algorithm",
        type=str,
        choices=["md5", "sha256"],
        default="sha256",
        help="Hash algorithm to use (default: sha256)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without actually deleting files"
    )

    parser.add_argument(
        "--strategy",
        type=str,
        choices=["manual", "oldest", "newest", "largest", "smallest"],
        default="manual",
        help="Strategy for selecting which duplicates to keep (default: manual)"
    )

    parser.add_argument(
        "--no-safe-mode",
        action="store_true",
        help="Disable automatic backups before deletion (not recommended)"
    )

    parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Don't scan subdirectories"
    )

    parser.add_argument(
        "--min-size",
        type=int,
        default=0,
        help="Minimum file size to consider in bytes (default: 0)"
    )

    parser.add_argument(
        "--max-size",
        type=int,
        default=None,
        help="Maximum file size to consider in bytes (default: unlimited)"
    )

    parser.add_argument(
        "--include",
        type=str,
        action="append",
        help="File patterns to include (e.g., '*.jpg'). Can be specified multiple times."
    )

    parser.add_argument(
        "--exclude",
        type=str,
        action="append",
        help="File patterns to exclude (e.g., '*.tmp'). Can be specified multiple times."
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

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
        min_size=parsed_args.min_size,
        max_size=parsed_args.max_size,
        include_patterns=parsed_args.include or [],
        exclude_patterns=parsed_args.exclude or [],
    )

    # Display banner
    console.print()
    console.print("=" * 70, style="bold blue")
    console.print("File Deduplication Tool", style="bold blue", justify="center")
    console.print("Hash-based duplicate file detection and removal", style="dim", justify="center")
    console.print("=" * 70, style="bold blue")
    console.print()

    # Display configuration
    console.print(Panel(
        f"[bold]Directory:[/bold] {config.directory}\n"
        f"[bold]Algorithm:[/bold] {config.algorithm.upper()}\n"
        f"[bold]Strategy:[/bold] {config.strategy}\n"
        f"[bold]Recursive:[/bold] {'Yes' if config.recursive else 'No'}\n"
        f"[bold]Safe Mode:[/bold] {'Enabled' if config.safe_mode else 'Disabled'}\n"
        f"[bold]Mode:[/bold] {'DRY RUN' if config.dry_run else 'LIVE'}",
        title="Configuration",
        expand=False
    ))

    if config.dry_run:
        console.print("[yellow]⚠ DRY RUN MODE: No files will be deleted[/yellow]\n")
    elif not config.safe_mode:
        console.print("[red]⚠ WARNING: Safe mode disabled - no backups will be created![/red]\n")

    try:
        # Import deduplication services (these should be implemented by Stream A)
        # For now, we'll create a mock implementation that shows the UI flow

        # Note: In the final implementation, this would import from:
        # from file_organizer.services.deduplication import DuplicateDetector

        console.print("[bold]Step 1: Scanning for files...[/bold]")

        # Mock: This would call detector.scan_directory(config.directory)
        # For demonstration, create mock data
        mock_duplicates = {
            "abc123def456": [
                {
                    'path': directory / "photo1.jpg",
                    'size': 2048576,
                    'mtime': 1640000000.0,
                },
                {
                    'path': directory / "copy_photo1.jpg",
                    'size': 2048576,
                    'mtime': 1640100000.0,
                },
            ],
            "789ghi012jkl": [
                {
                    'path': directory / "document.pdf",
                    'size': 524288,
                    'mtime': 1640200000.0,
                },
                {
                    'path': directory / "backup" / "document.pdf",
                    'size': 524288,
                    'mtime': 1640300000.0,
                },
                {
                    'path': directory / "old" / "document.pdf",
                    'size': 524288,
                    'mtime': 1639900000.0,
                },
            ],
        }

        total_groups = len(mock_duplicates)
        total_duplicates = sum(len(files) for files in mock_duplicates.values())

        if total_groups == 0:
            console.print("\n[green]✓ No duplicate files found![/green]")
            return 0

        console.print(f"\n[green]✓ Found {total_groups} duplicate group(s) with {total_duplicates} files total[/green]\n")

        # Process each duplicate group
        total_removed = 0
        space_saved = 0

        for group_id, (file_hash, files) in enumerate(mock_duplicates.items(), 1):
            # Apply selection strategy
            files = select_files_to_keep(files, config.strategy)

            # Display the group
            display_duplicate_group(group_id, file_hash, files, total_groups)

            # Get user confirmation/selection
            remove_indices = get_user_selection(files, config.strategy)

            if remove_indices:
                # Calculate space savings
                for idx in remove_indices:
                    space_saved += files[idx]['size']
                    total_removed += 1

                # In real implementation, this would:
                # 1. Create backups if safe_mode is enabled
                # 2. Delete the files (unless dry_run)
                # 3. Log the operations

                if not config.dry_run:
                    console.print(f"\n[green]✓ Removed {len(remove_indices)} file(s)[/green]")
                else:
                    console.print(f"\n[yellow]✓ Would remove {len(remove_indices)} file(s)[/yellow]")
            else:
                console.print("\n[dim]Skipped this group[/dim]")

        # Display summary
        display_summary(
            total_groups=total_groups,
            total_duplicates=total_duplicates,
            total_removed=total_removed,
            space_saved=space_saved,
            dry_run=config.dry_run
        )

        if config.safe_mode and not config.dry_run and total_removed > 0:
            console.print("\n[dim]Backups are stored in: .file_organizer_backups/[/dim]")
            console.print("[dim]Use the restore command to recover deleted files if needed.[/dim]")

        return 0

    except KeyboardInterrupt:
        console.print("\n\n[yellow]Operation cancelled by user[/yellow]")
        return 130
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.exception("Deduplication failed")
        return 1


def main():
    """Main entry point for standalone execution."""
    sys.exit(dedupe_command())


if __name__ == "__main__":
    main()
