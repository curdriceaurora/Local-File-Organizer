"""Organize and preview CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

import file_organizer.cli._globals as _g

console = Console()


def _check_setup_completed() -> bool:
    """Check if the initial setup wizard has been completed.

    Returns:
        True if setup is complete, False otherwise.

    Raises:
        typer.Exit: With code 1 if setup is not completed.
    """
    from file_organizer.config.manager import ConfigManager

    config_manager = ConfigManager()
    config = config_manager.load()

    if not config.setup_completed:
        console.print()
        console.print(
            Panel.fit(
                "[bold yellow]First-time setup required[/bold yellow]\n\n"
                "File Organizer needs to be configured before use.\n"
                "Run the setup wizard to get started:\n\n"
                "  [bold cyan]file-organizer setup[/bold cyan]\n\n"
                "This will detect your system capabilities and configure\n"
                "the optimal AI models for your hardware.",
                border_style="yellow",
            )
        )
        console.print()
        raise typer.Exit(code=1)

    return True


def _resolve_parallel_settings(
    sequential: bool,
    max_workers: int | None,
    prefetch_depth: int,
    no_prefetch: bool = False,
) -> tuple[int | None, int]:
    """Validate and resolve parallel worker/prefetch settings.

    Args:
        sequential: Whether to force single-worker sequential processing.
        max_workers: Requested worker count, or None for auto.
        prefetch_depth: Requested prefetch queue depth.
        no_prefetch: Backward-compatible alias for prefetch_depth=0.

    Returns:
        Tuple of (resolved_workers, resolved_prefetch_depth).

    Raises:
        typer.Exit: With code 2 if --sequential and --max-workers > 1 conflict.
    """
    if sequential and max_workers not in (None, 1):
        console.print("[red]Error: --sequential cannot be combined with --max-workers > 1[/red]")
        raise typer.Exit(code=2)
    return (1 if sequential else max_workers, 0 if (sequential or no_prefetch) else prefetch_depth)


def organize(
    input_dir: Path = typer.Argument(..., help="Directory containing files to organize."),
    output_dir: Path = typer.Argument(..., help="Destination directory for organized files."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without moving files."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
    max_workers: int | None = typer.Option(
        None,
        "--max-workers",
        min=1,
        help="Maximum number of parallel workers for file processing.",
    ),
    sequential: bool = typer.Option(
        False,
        "--sequential",
        help="Force single-worker sequential processing.",
    ),
    no_vision: bool = typer.Option(
        False,
        "--no-vision",
        "--text-only",
        help="Disable vision model usage and organize images by extension fallback.",
    ),
    prefetch_depth: int = typer.Option(
        2,
        "--prefetch-depth",
        min=0,
        help=(
            "Task scheduling prefetch depth per worker (0 disables queue-ahead and "
            "uses strictly sequential submission)."
        ),
    ),
    no_prefetch: bool = typer.Option(
        False,
        "--no-prefetch",
        help="Backward-compatible alias for --prefetch-depth 0.",
    ),
) -> None:
    """Organize files in a directory using AI models."""
    # Check if setup has been completed
    _check_setup_completed()

    console.print(f"[bold]Organizing[/bold] {input_dir} -> {output_dir}")
    if dry_run or _g.dry_run:
        console.print("[yellow]Dry run mode — no files will be moved.[/yellow]")
    resolved_workers, resolved_prefetch_depth = _resolve_parallel_settings(
        sequential, max_workers, prefetch_depth, no_prefetch
    )

    try:
        from file_organizer.core.organizer import FileOrganizer

        organizer = FileOrganizer(
            dry_run=dry_run or _g.dry_run,
            parallel_workers=resolved_workers,
            prefetch_depth=resolved_prefetch_depth,
            enable_vision=not no_vision,
            no_prefetch=no_prefetch,
        )
        result = organizer.organize(input_dir, output_dir)
        console.print(
            f"[green]Done:[/green] {result.processed_files} processed, "
            f"{result.skipped_files} skipped, {result.failed_files} failed"
        )
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc


def preview(
    input_dir: Path = typer.Argument(..., help="Directory to preview."),
    max_workers: int | None = typer.Option(
        None,
        "--max-workers",
        min=1,
        help="Maximum number of parallel workers for file processing.",
    ),
    sequential: bool = typer.Option(
        False,
        "--sequential",
        help="Force single-worker sequential processing.",
    ),
    no_vision: bool = typer.Option(
        False,
        "--no-vision",
        "--text-only",
        help="Disable vision model usage and organize images by extension fallback.",
    ),
    prefetch_depth: int = typer.Option(
        2,
        "--prefetch-depth",
        min=0,
        help=(
            "Task scheduling prefetch depth per worker (0 disables queue-ahead and "
            "uses strictly sequential submission)."
        ),
    ),
    no_prefetch: bool = typer.Option(
        False,
        "--no-prefetch",
        help="Backward-compatible alias for --prefetch-depth 0.",
    ),
) -> None:
    """Preview how files would be organized (dry-run)."""
    # Check if setup has been completed
    _check_setup_completed()

    console.print(f"[bold]Previewing[/bold] {input_dir}")
    resolved_workers, resolved_prefetch_depth = _resolve_parallel_settings(
        sequential, max_workers, prefetch_depth, no_prefetch
    )

    try:
        from file_organizer.core.organizer import FileOrganizer

        organizer = FileOrganizer(
            dry_run=True,
            parallel_workers=resolved_workers,
            prefetch_depth=resolved_prefetch_depth,
            enable_vision=not no_vision,
            no_prefetch=no_prefetch,
        )
        result = organizer.organize(input_dir, input_dir)
        console.print(f"[green]Preview:[/green] {result.total_files} files would be organized")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc
