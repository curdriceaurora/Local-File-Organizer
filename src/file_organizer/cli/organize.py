"""Organize and preview CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

import file_organizer.cli._globals as _g

console = Console()


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
    console.print(f"[bold]Organizing[/bold] {input_dir} -> {output_dir}")
    if dry_run or _g.dry_run:
        console.print("[yellow]Dry run mode — no files will be moved.[/yellow]")
    if sequential and max_workers not in (None, 1):
        console.print("[red]Error: --sequential cannot be combined with --max-workers > 1[/red]")
        raise typer.Exit(code=2)

    resolved_workers = 1 if sequential else max_workers
    resolved_prefetch_depth = 0 if sequential else prefetch_depth

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
) -> None:
    """Preview how files would be organized (dry-run)."""
    console.print(f"[bold]Previewing[/bold] {input_dir}")
    try:
        from file_organizer.core.organizer import FileOrganizer

        organizer = FileOrganizer(dry_run=True)
        result = organizer.organize(input_dir, input_dir)
        console.print(f"[green]Preview:[/green] {result.total_files} files would be organized")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc
