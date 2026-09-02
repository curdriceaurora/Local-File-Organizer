# pyre-ignore-all-errors
"""Modern Typer-based auto-tagging CLI sub-app.

Replaces the legacy argparse ``autotag`` command with a sub-app
providing ``suggest``, ``apply``, ``popular``, ``recent``, and ``batch`` commands.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from file_organizer.cli.path_validation import resolve_cli_path
from file_organizer.core.path_guard import safe_walk

autotag_app = typer.Typer(
    name="autotag",
    help="Auto-tagging suggestions and management.",
    no_args_is_help=True,
)

console = Console()
logger = logging.getLogger(__name__)


def _walk_error_handler(root: Path) -> Callable[[Path, OSError], None]:
    """Fail for an unreadable root while skipping unreadable descendants."""

    def handle(path: Path, exc: OSError) -> None:
        if path == root:
            console.print("[red]Filesystem traversal failed:[/red]", path, exc)
            raise typer.Exit(code=1) from exc
        console.print("[yellow]Skipping unreadable path:[/yellow]", path, exc)

    return handle


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@autotag_app.command()
def suggest(
    directory: Annotated[Path, typer.Argument(help="Directory containing files to tag.")],
    top_n: Annotated[int, typer.Option("--top-n", "-n", help="Max suggestions per file.")] = 10,
    min_confidence: Annotated[
        float, typer.Option("--min-confidence", help="Minimum confidence %.")
    ] = 40.0,
    style: Annotated[
        str | None,
        typer.Option(
            "--style",
            "-s",
            help="Tagging style preset (e.g. sfx, audio, code, descriptive, hierarchical).",
        ),
    ] = None,
    prompt: Annotated[
        str | None,
        typer.Option(
            "--prompt",
            "-p",
            help="Custom prompt instructions for tag selection.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Suggest tags for files in a directory."""
    from file_organizer.services.auto_tagging import AutoTaggingService

    # A.cli: consolidates the prior inline ``resolve() + is_dir()`` check.
    resolved = resolve_cli_path(directory, must_exist=True, must_be_dir=True)

    try:
        service = AutoTaggingService()
    except Exception as exc:
        console.print(f"[red]Error initializing service: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    files = list(safe_walk(resolved, recursive=False, on_error=_walk_error_handler(resolved)))
    if not files:
        console.print("[dim]No files found in directory.[/dim]")
        raise typer.Exit(code=0)

    all_results: list[dict[str, Any]] = []

    for file_path in files:
        try:
            recommendation = service.suggest_tags(
                file_path,
                top_n=top_n,
                style=style,
                prompt=prompt,
            )
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
    file_path: Annotated[Path, typer.Argument(help="File to tag.")],
    tags: Annotated[list[str], typer.Argument(help="Tags to apply.")],
) -> None:
    """Apply tags to a file."""
    from file_organizer.cli.path_validation import validate_regular_file
    from file_organizer.services.auto_tagging import AutoTaggingService

    # A.cli: file arg — exists + not-dir.
    resolved = resolve_cli_path(file_path, must_exist=True, must_be_dir=False)
    validate_regular_file(resolved, param_name="file_path")

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
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of tags to show.")] = 20,
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
    days: Annotated[int, typer.Option("--days", help="Days to look back.")] = 30,
    limit: Annotated[int, typer.Option("--limit", "-n", help="Number of tags to show.")] = 20,
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
    directory: Annotated[Path, typer.Argument(help="Directory to process.")],
    pattern: Annotated[str, typer.Option(help="File pattern.")] = "*",
    recursive: Annotated[bool, typer.Option("--recursive/--no-recursive")] = True,
    style: Annotated[
        str | None,
        typer.Option(
            "--style",
            "-s",
            help="Tagging style preset (e.g. sfx, audio, code, descriptive, hierarchical).",
        ),
    ] = None,
    prompt: Annotated[
        str | None,
        typer.Option(
            "--prompt",
            "-p",
            help="Custom prompt instructions for tag selection.",
        ),
    ] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Batch tag suggestion for directory."""
    from file_organizer.services.auto_tagging import AutoTaggingService

    resolved = resolve_cli_path(directory, must_exist=True, must_be_dir=True)

    try:
        service = AutoTaggingService()
    except Exception as exc:
        console.print(f"[red]Error initializing service: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    files = list(
        safe_walk(
            resolved,
            pattern=pattern,
            recursive=recursive,
            on_error=_walk_error_handler(resolved),
        )
    )

    if not files:
        console.print(f"[dim]No files found matching pattern: {pattern}[/dim]")
        raise typer.Exit(code=0)

    console.print(f"Processing [bold]{len(files)}[/bold] files...")

    try:
        results = service.recommender.batch_recommend(
            files,
            top_n=5,
            style=style,
            prompt=prompt,
        )
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
