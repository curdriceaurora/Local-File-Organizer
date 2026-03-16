"""Modern Typer-based auto-tagging CLI sub-app.

Replaces the legacy argparse ``autotag`` command with a sub-app
providing ``suggest``, ``apply``, ``popular``, ``recent``, and ``batch`` commands.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

autotag_app = typer.Typer(
    name="autotag",
    help="Auto-tagging suggestions and management.",
    no_args_is_help=True,
)

console = Console()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@autotag_app.command()
def suggest(
    directory: Path = typer.Argument(..., help="Directory containing files to tag."),
    top_n: int = typer.Option(10, "--top-n", "-n", help="Max suggestions per file."),
    min_confidence: float = typer.Option(40.0, "--min-confidence", help="Minimum confidence %."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Suggest tags for files in a directory."""
    from file_organizer.services.auto_tagging import AutoTaggingService

    resolved = directory.resolve()
    if not resolved.is_dir():
        console.print(f"[red]Error: Directory not found: {directory}[/red]")
        raise typer.Exit(code=1)

    try:
        service = AutoTaggingService()
    except Exception as exc:
        console.print(f"[red]Error initializing service: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    files = [f for f in resolved.iterdir() if f.is_file()]
    if not files:
        console.print("[dim]No files found in directory.[/dim]")
        raise typer.Exit(code=0)

    all_results: list[dict[str, Any]] = []

    for file_path in files:
        try:
            recommendation = service.suggest_tags(file_path, top_n=top_n)
        except Exception:
            logger.debug(
                "Skipping file during auto-tag suggest due to inference error: %s",
                file_path,
                exc_info=True,
            )
            continue

        filtered = [s for s in recommendation.suggestions if s.confidence >= min_confidence]

        if json_output:
            all_results.append(
                {
                    "file": str(file_path),
                    "suggestions": [
                        {
                            "tag": s.tag,
                            "confidence": s.confidence,
                            "source": s.source,
                            "reasoning": s.reasoning,
                        }
                        for s in filtered
                    ],
                }
            )
        else:
            table = Table(title=f"Tags for {file_path.name}")
            table.add_column("#", style="dim", width=3)
            table.add_column("Tag", style="cyan")
            table.add_column("Confidence", justify="right")
            table.add_column("Source")
            table.add_column("Reasoning")

            for idx, s in enumerate(filtered, 1):
                table.add_row(
                    str(idx),
                    s.tag,
                    f"{s.confidence:.1f}%",
                    s.source,
                    s.reasoning,
                )
            console.print(table)

    if json_output:
        typer.echo(json.dumps(all_results, indent=2))


@autotag_app.command()
def apply(
    file_path: Path = typer.Argument(..., help="File to tag."),
    tags: list[str] = typer.Argument(..., help="Tags to apply."),
) -> None:
    """Apply tags to a file."""
    from file_organizer.services.auto_tagging import AutoTaggingService

    resolved = file_path.resolve()
    if not resolved.exists():
        console.print(f"[red]Error: File not found: {file_path}[/red]")
        raise typer.Exit(code=1)

    try:
        service = AutoTaggingService()
        service.record_tag_usage(resolved, list(tags))
    except Exception as exc:
        console.print(f"[red]Error applying tags: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[green]Applied tags to {resolved.name}:[/green]")
    for tag in tags:
        console.print(f"  - {tag}")


@autotag_app.command()
def popular(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of tags to show."),
) -> None:
    """Show most popular tags."""
    from file_organizer.services.auto_tagging import AutoTaggingService

    try:
        service = AutoTaggingService()
        results = service.get_popular_tags(limit=limit)
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not results:
        console.print("[dim]No tag usage data yet.[/dim]")
        raise typer.Exit(code=0)

    table = Table(title=f"Popular Tags (Top {limit})")
    table.add_column("#", style="dim", width=4)
    table.add_column("Tag", style="cyan")
    table.add_column("Count", justify="right")

    for idx, (tag, count) in enumerate(results, 1):
        table.add_row(str(idx), tag, str(count))

    console.print(table)


@autotag_app.command()
def recent(
    days: int = typer.Option(30, "--days", help="Days to look back."),
    limit: int = typer.Option(20, "--limit", "-n", help="Number of tags to show."),
) -> None:
    """Show recently used tags."""
    from file_organizer.services.auto_tagging import AutoTaggingService

    try:
        service = AutoTaggingService()
        results = service.get_recent_tags(days=days, limit=limit)
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    if not results:
        console.print(f"[dim]No tags used in the last {days} days.[/dim]")
        raise typer.Exit(code=0)

    table = Table(title=f"Recent Tags (Last {days} days)")
    table.add_column("#", style="dim", width=4)
    table.add_column("Tag", style="cyan")

    for idx, tag in enumerate(results, 1):
        table.add_row(str(idx), tag)

    console.print(table)


@autotag_app.command()
def batch(
    directory: Path = typer.Argument(..., help="Directory to process."),
    pattern: str = typer.Option("*", help="File pattern."),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive"),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Batch tag suggestion for directory."""
    from file_organizer.services.auto_tagging import AutoTaggingService

    resolved = directory.resolve()
    if not resolved.is_dir():
        console.print(f"[red]Error: Directory not found: {directory}[/red]")
        raise typer.Exit(code=1)

    try:
        service = AutoTaggingService()
    except Exception as exc:
        console.print(f"[red]Error initializing service: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    glob_pattern = f"**/{pattern}" if recursive else pattern
    files = [f for f in resolved.glob(glob_pattern) if f.is_file()]

    if not files:
        console.print(f"[dim]No files found matching pattern: {pattern}[/dim]")
        raise typer.Exit(code=0)

    console.print(f"Processing [bold]{len(files)}[/bold] files...")

    try:
        results = service.recommender.batch_recommend(files, top_n=5)
    except Exception as exc:
        console.print(f"[red]Error during batch processing: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    output_data: list[dict[str, Any]] = []
    for fpath, recommendation in results.items():
        output_data.append(
            {
                "file": str(fpath),
                "suggestions": [
                    {
                        "tag": s.tag,
                        "confidence": s.confidence,
                        "source": s.source,
                    }
                    for s in recommendation.suggestions
                ],
            }
        )

    if json_output:
        typer.echo(json.dumps(output_data, indent=2))
    else:
        for item in output_data:
            table = Table(title=f"Tags for {Path(item['file']).name}")
            table.add_column("Tag", style="cyan")
            table.add_column("Confidence", justify="right")
            table.add_column("Source")
            for s in item["suggestions"]:
                table.add_row(s["tag"], f"{s['confidence']:.1f}%", s["source"])
            console.print(table)
