"""Display and formatting utilities for deduplication CLI.

Provides Rich-based UI components for displaying duplicate groups, summaries,
and formatting utilities for file sizes and timestamps.
Extracted from ``dedupe.py`` to separate display concerns from orchestration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Formatted size string (e.g., '1.5 MB')
    """
    value: float = size_bytes
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if value < 1024.0:
            return f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{value:.1f} PB"


def format_datetime(timestamp: float) -> str:
    """Format timestamp in human-readable format.

    Args:
        timestamp: Unix timestamp

    Returns:
        Formatted datetime string
    """
    dt = datetime.fromtimestamp(timestamp, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def display_banner(console: Console) -> None:
    """Display tool banner.

    Args:
        console: Rich console for output
    """
    console.print()
    console.print("=" * 70, style="bold blue")
    console.print("File Deduplication Tool", style="bold blue", justify="center")
    console.print("Hash-based duplicate file detection and removal", style="dim", justify="center")
    console.print("=" * 70, style="bold blue")
    console.print()


def display_config(
    console: Console,
    directory: str,
    algorithm: str,
    strategy: str,
    recursive: bool,
    safe_mode: bool,
    dry_run: bool,
    batch: bool = False,
) -> None:
    """Display configuration panel.

    Args:
        console: Rich console for output
        directory: Directory being scanned
        algorithm: Hash algorithm name
        strategy: Selection strategy
        recursive: Whether scanning recursively
        safe_mode: Whether safe mode is enabled
        dry_run: Whether in dry-run mode
        batch: Whether batch mode is enabled
    """
    config_text = (
        f"[bold]Directory:[/bold] {directory}\n"
        f"[bold]Algorithm:[/bold] {algorithm.upper()}\n"
        f"[bold]Strategy:[/bold] {strategy}\n"
        f"[bold]Recursive:[/bold] {'Yes' if recursive else 'No'}\n"
        f"[bold]Safe Mode:[/bold] {'Enabled' if safe_mode else 'Disabled'}\n"
        f"[bold]Mode:[/bold] {'DRY RUN' if dry_run else 'LIVE'}"
    )

    if batch and strategy != "manual":
        config_text += "\n[bold]Batch Mode:[/bold] Enabled (auto-apply strategy)"

    console.print(Panel(config_text, title="Configuration", expand=False))

    if dry_run:
        console.print("[yellow]⚠ DRY RUN MODE: No files will be deleted[/yellow]\n")
    elif not safe_mode:
        console.print("[red]⚠ WARNING: Safe mode disabled - no backups will be created![/red]\n")


def display_duplicate_group(
    console: Console,
    group_id: int,
    file_hash: str,
    files: list[dict[str, Any]],
    total_groups: int,
) -> None:
    """Display a group of duplicate files in a formatted table.

    Args:
        console: Rich console for output
        group_id: ID of the duplicate group
        file_hash: Hash value of the duplicates
        files: List of file metadata dicts
        total_groups: Total number of duplicate groups
    """
    console.print()
    console.print(
        Panel(
            f"[bold cyan]Duplicate Group {group_id}/{total_groups}[/bold cyan]\n"
            f"Hash: [dim]{file_hash[:16]}...[/dim]",
            expand=False,
        )
    )

    # Create table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=3)
    table.add_column("Path", style="cyan")
    table.add_column("Size", justify="right", style="green")
    table.add_column("Modified", style="yellow")
    table.add_column("Status", justify="center")

    # Add files to table
    for idx, file_info in enumerate(files, 1):
        path = file_info["path"]
        size = format_size(file_info["size"])
        modified = format_datetime(file_info["mtime"])

        # Mark the file that will be kept (for strategies)
        status = "✓" if file_info.get("keep", False) else ""

        table.add_row(str(idx), str(path), size, modified, status)

    console.print(table)

    # Calculate space that can be saved
    total_size = sum(f["size"] for f in files)
    saved_space = total_size - files[0]["size"]  # Keep one file
    console.print(f"\n[dim]Potential space savings: {format_size(saved_space)}[/dim]")


def display_summary(
    console: Console,
    total_groups: int,
    total_duplicates: int,
    total_removed: int,
    space_saved: int,
    dry_run: bool,
) -> None:
    """Display summary of deduplication operation.

    Args:
        console: Rich console for output
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
        console.print(
            Panel(
                "[bold yellow]DRY RUN SUMMARY[/bold yellow]\n\n"
                f"Duplicate groups found: [cyan]{total_groups}[/cyan]\n"
                f"Total duplicate files: [cyan]{total_duplicates}[/cyan]\n"
                f"Files that would be removed: [cyan]{total_removed}[/cyan]\n"
                f"Space that would be saved: [green]{format_size(space_saved)}[/green]\n\n"
                "[dim]Run without --dry-run to actually remove files.[/dim]",
                title="Summary",
                expand=False,
            )
        )
    else:
        console.print(
            Panel(
                "[bold green]DEDUPLICATION COMPLETE[/bold green]\n\n"
                f"Duplicate groups found: [cyan]{total_groups}[/cyan]\n"
                f"Total duplicate files: [cyan]{total_duplicates}[/cyan]\n"
                f"Files removed: [cyan]{total_removed}[/cyan]\n"
                f"Space saved: [green]{format_size(space_saved)}[/green]",
                title="Summary",
                expand=False,
            )
        )


def display_backup_info(console: Console) -> None:
    """Display backup information message.

    Args:
        console: Rich console for output
    """
    console.print("\n[dim]Backups are stored in: .file_organizer_backups/[/dim]")
    console.print("[dim]Use the restore command to recover deleted files if needed.[/dim]")
