"""Rich UI display helpers for the file organizer.

Provides progress bar creation, file-type breakdown tables, and
summary output. Extracted from ``organizer.py`` to separate
presentation concerns from orchestration logic.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from file_organizer.core.types import OrganizationResult


def show_file_breakdown(
    console: Console,
    *,
    text_files: list[Path],
    image_files: list[Path],
    video_files: list[Path],
    audio_files: list[Path],
    cad_files: list[Path],
    other_files: list[Path],
) -> None:
    """Show a Rich table with file type counts."""
    table = Table(title="File Type Breakdown", show_header=True)
    table.add_column("Type", style="cyan")
    table.add_column("Count", justify="right", style="green")
    table.add_column("Status", style="yellow")

    table.add_row("Text files", str(len(text_files)), "✓ Will process")
    table.add_row("Images", str(len(image_files)), "✓ Will process")
    table.add_row("Videos", str(len(video_files)), "✓ Will process (metadata)")
    table.add_row("Audio", str(len(audio_files)), "✓ Will process (metadata)")
    table.add_row("CAD files", str(len(cad_files)), "✓ Will process")
    table.add_row("Other", str(len(other_files)), "⊘ Skip (unsupported)")

    console.print(table)


def show_summary(
    console: Console,
    result: OrganizationResult,
    output_path: Path,
    *,
    dry_run: bool,
) -> None:
    """Show final organization summary."""
    console.print("\n" + "=" * 70)
    console.print("[bold green]Organization Complete![/bold green]")
    console.print("=" * 70)

    console.print("\n[bold]Statistics:[/bold]")
    console.print(f"  Total files scanned: {result.total_files}")
    console.print(f"  [green]Processed: {result.processed_files}[/green]")
    console.print(f"  [yellow]Skipped: {result.skipped_files}[/yellow]")
    console.print(f"  [red]Failed: {result.failed_files}[/red]")
    if result.errors:
        for file_str, err in result.errors[:10]:
            file_name = Path(file_str).name
            console.print(f"    [red]✗[/red] {file_name}: {err}")
        if len(result.errors) > 10:
            console.print(f"    ... and {len(result.errors) - 10} more")
    console.print(f"  Processing time: {result.processing_time:.2f}s")

    if result.organized_structure:
        console.print("\n[bold]Organized Structure:[/bold]")
        console.print(f"[cyan]{output_path}/[/cyan]")

        for folder, files in sorted(result.organized_structure.items()):
            console.print(f"  [cyan]├── {folder}/[/cyan]")
            for i, filename in enumerate(sorted(files)):
                prefix = "└──" if i == len(files) - 1 else "├──"
                console.print(f"       {prefix} {filename}")

    if dry_run:
        console.print("\n[yellow]⚠️  DRY RUN - No files were actually moved[/yellow]")
        console.print("[dim]Run without --dry-run to perform actual organization[/dim]")
    else:
        console.print(f"\n[green]✓ Files organized in: {output_path}[/green]")


def create_progress(console: Console) -> Progress:
    """Create a standard Rich progress bar."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    )
