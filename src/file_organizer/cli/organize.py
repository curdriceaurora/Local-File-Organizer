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
    no_prefetch: bool = typer.Option(
        False,
        "--no-prefetch",
        help=(
            "Reserved for future stage-based pipeline debugging. "
            "Currently has no effect for this command (uses ParallelProcessor, not PipelineOrchestrator)."
        ),
    ),
) -> None:
    """Organize files in a directory using AI models."""
    console.print(f"[bold]Organizing[/bold] {input_dir} -> {output_dir}")
    if dry_run or _g.dry_run:
        console.print("[yellow]Dry run mode — no files will be moved.[/yellow]")

    try:
        from file_organizer.core.organizer import FileOrganizer

        organizer = FileOrganizer(dry_run=dry_run or _g.dry_run, no_prefetch=no_prefetch)
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
