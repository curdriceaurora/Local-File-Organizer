"""File removal operations for deduplication.

Handles the actual file deletion process including backup creation
and error handling during deduplication operations.
Extracted from ``dedupe.py`` to separate removal concerns from orchestration.
"""

from __future__ import annotations

from typing import Any

from loguru import logger
from rich.console import Console

from file_organizer.services.deduplication.backup import BackupManager
from file_organizer.services.deduplication.index import DuplicateGroup


def remove_files(
    files: list[dict[str, Any]],
    remove_indices: list[int],
    backup_manager: BackupManager | None,
    dry_run: bool,
    console: Console,
) -> tuple[int, int]:
    """Remove selected duplicate files with optional backup.

    Args:
        files: List of file metadata dicts
        remove_indices: Indices of files to remove
        backup_manager: Optional backup manager for safe mode
        dry_run: If True, simulate removal without actual deletion
        console: Rich console for user feedback

    Returns:
        Tuple of (files_removed, space_saved)
    """
    files_removed = 0
    space_saved = 0

    for idx in remove_indices:
        file_to_remove = files[idx]["path"]

        try:
            # Create backup if safe mode is enabled
            if backup_manager and not dry_run:
                backup_path = backup_manager.create_backup(file_to_remove)
                logger.debug(f"Created backup: {backup_path}")

            # Delete the file (unless dry run)
            if not dry_run:
                file_to_remove.unlink()
                logger.info(f"Removed: {file_to_remove}")

            # Update counters
            space_saved += files[idx]["size"]
            files_removed += 1

        except OSError as e:
            console.print(f"[red]Error removing {file_to_remove}: {e}[/red]")
            logger.exception(f"Failed to remove {file_to_remove}")

    # Display feedback
    if not dry_run:
        console.print(f"\n[green]✓ Removed {files_removed} file(s)[/green]")
    else:
        console.print(f"\n[yellow]✓ Would remove {files_removed} file(s)[/yellow]")

    return files_removed, space_saved


def process_duplicate_group(
    group_id: int,
    file_hash: str,
    group: DuplicateGroup,
    total_groups: int,
    strategy: str,
    batch: bool,
    backup_manager: BackupManager | None,
    dry_run: bool,
    console: Console,
) -> tuple[int, int]:
    """Process a single duplicate group with removal.

    Args:
        group_id: ID of the duplicate group
        file_hash: Hash value of the duplicates
        group: DuplicateGroup instance
        total_groups: Total number of duplicate groups
        strategy: Selection strategy
        batch: Whether batch mode is enabled
        backup_manager: Optional backup manager for safe mode
        dry_run: If True, simulate operations
        console: Rich console for user feedback

    Returns:
        Tuple of (files_removed, space_saved)
    """
    from file_organizer.cli.dedupe_display import display_duplicate_group
    from file_organizer.cli.dedupe_strategy import get_user_selection, select_files_to_keep

    # Convert to dictionary format for display
    files = [
        {
            "path": file_meta.path,
            "size": file_meta.size,
            "mtime": file_meta.modified_time.timestamp(),
        }
        for file_meta in group.files
    ]

    # Apply selection strategy
    files = select_files_to_keep(files, strategy)

    # Display the group
    display_duplicate_group(console, group_id, file_hash, files, total_groups)

    # Get user confirmation/selection
    remove_indices = get_user_selection(files, strategy, batch, console)

    if remove_indices:
        return remove_files(files, remove_indices, backup_manager, dry_run, console)
    else:
        console.print("\n[dim]Skipped this group[/dim]")
        return 0, 0
