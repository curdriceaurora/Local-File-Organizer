"""File selection strategies for deduplication.

Handles file selection logic for determining which duplicate files to keep
or remove based on various strategies (manual, oldest, newest, largest, smallest).
Extracted from ``dedupe.py`` to separate selection concerns from orchestration.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console


def _resolve_console(console: Console | None) -> Console:
    """Resolve the console used for prompts and feedback."""
    if console is not None:
        return console

    try:
        from file_organizer.cli import dedupe as dedupe_module
    except ImportError:
        return Console()
    else:
        return dedupe_module.console


def select_files_to_keep(files: list[dict[str, Any]], strategy: str) -> list[dict[str, Any]]:
    """Apply selection strategy to determine which files to keep/remove.

    Args:
        files: List of duplicate file metadata dicts with 'path', 'size', and 'mtime' keys.
        strategy: Selection strategy ('manual', 'oldest', 'newest', 'largest', 'smallest').

    Returns:
        Updated list with 'keep' flags set for files to preserve.
    """
    updated_files = [dict(file_info) for file_info in files]
    if not updated_files:
        return updated_files

    if strategy == "oldest":
        # Keep the file with the oldest modification time
        oldest_idx = min(range(len(updated_files)), key=lambda i: updated_files[i]["mtime"])
        updated_files[oldest_idx]["keep"] = True

    elif strategy == "newest":
        # Keep the file with the newest modification time
        newest_idx = max(range(len(updated_files)), key=lambda i: updated_files[i]["mtime"])
        updated_files[newest_idx]["keep"] = True

    elif strategy == "largest":
        # Keep the largest file (in case of slight differences)
        largest_idx = max(range(len(updated_files)), key=lambda i: updated_files[i]["size"])
        updated_files[largest_idx]["keep"] = True

    elif strategy == "smallest":
        # Keep the smallest file
        smallest_idx = min(range(len(updated_files)), key=lambda i: updated_files[i]["size"])
        updated_files[smallest_idx]["keep"] = True

    elif strategy == "manual":
        # Manual selection - no automatic marking
        pass

    return updated_files


def get_user_selection(
    files: list[dict[str, Any]],
    strategy: str,
    batch: bool = False,
    console: Console | None = None,
) -> list[int]:
    """Get user selection for files to remove.

    Args:
        files: List of duplicate file metadata dicts.
        strategy: Selection strategy ('manual' for interactive, others for automatic).
        batch: If True, skip confirmation for automatic strategies.
        console: Rich console to use for prompts and feedback.

    Returns:
        List of indices of files to remove.
    """
    console = _resolve_console(console)

    if strategy == "manual":
        console.print("\n[bold]Which file(s) should we keep?[/bold]")
        console.print(
            "[dim]Enter the number(s) to keep (comma-separated), or 'a' to keep all, or 's' to skip:[/dim]"
        )

        while True:
            try:
                choice = console.input("[cyan]Keep file(s):[/cyan] ").strip().lower()

                if choice == "s":
                    return []  # Skip this group
                elif choice == "a":
                    return []  # Keep all (remove none)
                else:
                    # Parse comma-separated numbers
                    keep_indices = [int(x.strip()) - 1 for x in choice.split(",")]

                    # Validate indices
                    if all(0 <= idx < len(files) for idx in keep_indices):
                        # Return indices to remove (all except kept)
                        return [i for i in range(len(files)) if i not in keep_indices]
                    else:
                        console.print("[red]Invalid selection. Please try again.[/red]")
            except KeyboardInterrupt:
                # Re-raise KeyboardInterrupt to allow clean exit
                raise
            except ValueError:
                console.print("[red]Invalid input. Please enter numbers or 'a'/'s'.[/red]")
    else:
        # For automatic strategies
        if batch:
            # Batch mode: automatically remove without confirmation
            return [i for i, f in enumerate(files) if not f.get("keep", False)]
        else:
            # Confirm the selection
            console.print("\n[bold]Proceed with this selection?[/bold]")
            console.print("[dim](y)es / (n)o / (s)kip this group:[/dim]")

            while True:
                try:
                    choice = console.input("[cyan]Choice:[/cyan] ").strip().lower()
                except KeyboardInterrupt:
                    raise

                if choice in ["y", "yes"]:
                    # Remove files not marked to keep
                    return [i for i, f in enumerate(files) if not f.get("keep", False)]
                elif choice in ["n", "no"]:
                    return []  # Keep all
                elif choice in ["s", "skip"]:
                    return []  # Skip
                else:
                    console.print("[red]Please enter 'y', 'n', or 's'.[/red]")
