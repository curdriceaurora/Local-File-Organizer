# pyre-ignore-all-errors
"""Modern Typer sub-app for duplicate file detection and resolution.

Replaces the legacy argparse ``dedupe`` command with a sub-app
providing ``scan``, ``resolve``, and ``report`` commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import typer
from rich.console import Console
from rich.table import Table

console = Console()

dedupe_app = typer.Typer(
    name="dedupe",
    help="Find and manage duplicate files.",
    no_args_is_help=True,
)


def _get_detector() -> Any:
    """Lazily import and return a fresh ``DuplicateDetector``."""
    from file_organizer.services.deduplication.detector import DuplicateDetector

    return DuplicateDetector()


def _build_scan_options(
    directory: Path,
    algorithm: str,
    recursive: bool,
    min_size: int,
    max_size: int | None,
    include: str | None,
    exclude: str | None,
) -> Any:
    """Build ``ScanOptions`` from CLI flags."""
    from file_organizer.services.deduplication.detector import ScanOptions
    from file_organizer.services.deduplication.hasher import HashAlgorithm

    include_patterns = include.split(",") if include else None
    exclude_patterns = exclude.split(",") if exclude else None
    return ScanOptions(
        algorithm=cast("HashAlgorithm", algorithm),
        recursive=recursive,
        min_file_size=min_size,
        max_file_size=max_size,
        file_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )


def _display_groups_table(
    groups: dict,  # type: ignore[type-arg]
    *,
    json_output: bool = False,
) -> None:
    """Render duplicate groups as a Rich table or JSON."""
    if json_output:
        data = []
        for hash_val, group in groups.items():
            data.append(
                {
                    "hash": hash_val,
                    "count": group.count,
                    "total_size": group.total_size,
                    "wasted_space": group.wasted_space,
                    "files": [str(f.path) for f in group.files],
                }
            )
        console.print_json(json.dumps(data, indent=2))
        return

    for hash_val, group in groups.items():
        table = Table(title=f"Group {hash_val[:12]}…", show_lines=True)
        table.add_column("#", style="dim", width=3)
        table.add_column("Path")
        table.add_column("Size", justify="right")
        table.add_column("Modified")
        for idx, fmeta in enumerate(group.files, 1):
            table.add_row(
                str(idx),
                str(fmeta.path),
                _format_size(fmeta.size),
                fmeta.modified_time.strftime("%Y-%m-%d %H:%M"),
            )
        console.print(table)
        console.print(f"  [dim]Wasted space: {_format_size(group.wasted_space)}[/dim]\n")


def _format_size(size: int) -> str:
    """Format file size in human-readable units.

    Args:
        size: File size in bytes.

    Returns:
        Formatted size string (e.g., "1.5 MB").
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f} PB"


# -----------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------


@dedupe_app.command()
def scan(
    directory: Path = typer.Argument(..., help="Directory to scan for duplicates."),
    algorithm: str = typer.Option("sha256", help="Hash algorithm (md5, sha256)."),
    recursive: bool = typer.Option(True, help="Scan subdirectories."),
    min_size: int = typer.Option(0, help="Minimum file size in bytes."),
    max_size: int | None = typer.Option(None, help="Maximum file size in bytes."),
    include: str | None = typer.Option(None, help="Comma-separated glob include patterns."),
    exclude: str | None = typer.Option(None, help="Comma-separated glob exclude patterns."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Scan a directory and display duplicate file groups."""
    detector = _get_detector()
    options = _build_scan_options(
        directory, algorithm, recursive, min_size, max_size, include, exclude
    )

    with console.status("Scanning for duplicates…"):
        detector.scan_directory(directory, options)

    groups = detector.get_duplicate_groups()
    if not groups:
        console.print("[green]No duplicates found.[/green]")
        raise typer.Exit()

    console.print(f"Found [bold]{len(groups)}[/bold] duplicate groups.\n")
    _display_groups_table(groups, json_output=json_output)


@dedupe_app.command()
def resolve(
    directory: Path = typer.Argument(..., help="Directory to scan for duplicates."),
    strategy: str = typer.Option(
        "manual",
        help="Resolution strategy (manual, oldest, newest, largest, smallest).",
    ),
    algorithm: str = typer.Option("sha256", help="Hash algorithm."),
    recursive: bool = typer.Option(True, help="Scan subdirectories."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without deleting."),
    min_size: int = typer.Option(0, help="Minimum file size in bytes."),
    max_size: int | None = typer.Option(None, help="Maximum file size in bytes."),
    include: str | None = typer.Option(None, help="Comma-separated include patterns."),
    exclude: str | None = typer.Option(None, help="Comma-separated exclude patterns."),
) -> None:
    """Scan and resolve duplicates using a strategy."""
    detector = _get_detector()
    options = _build_scan_options(
        directory, algorithm, recursive, min_size, max_size, include, exclude
    )

    with console.status("Scanning for duplicates…"):
        detector.scan_directory(directory, options)

    groups = detector.get_duplicate_groups()
    if not groups:
        console.print("[green]No duplicates found.[/green]")
        raise typer.Exit()

    removed = 0
    for hash_val, group in groups.items():
        files = sorted(group.files, key=lambda f: f.modified_time)
        if strategy == "oldest":
            keep = files[-1]
        elif strategy == "newest":
            keep = files[0]
        elif strategy == "largest":
            keep = max(files, key=lambda f: f.size)
        elif strategy == "smallest":
            keep = min(files, key=lambda f: f.size)
        else:
            # Manual: show table, skip automatic resolution
            _display_groups_table({hash_val: group})
            console.print("[yellow]Manual mode — skipping automatic resolution.[/yellow]")
            continue

        to_remove = [f for f in files if f.path != keep.path]
        for fmeta in to_remove:
            if dry_run:
                console.print(f"  [dim]Would remove:[/dim] {fmeta.path}")
            else:
                try:
                    fmeta.path.unlink()
                    console.print(f"  [red]Removed:[/red] {fmeta.path}")
                    removed += 1
                except OSError as exc:
                    console.print(f"  [red]Error removing {fmeta.path}: {exc}[/red]")

    if dry_run:
        console.print("\n[yellow]Dry run — no files were removed.[/yellow]")
    else:
        console.print(f"\n[green]Removed {removed} duplicate files.[/green]")


@dedupe_app.command()
def report(
    directory: Path = typer.Argument(..., help="Directory to scan."),
    algorithm: str = typer.Option("sha256", help="Hash algorithm."),
    recursive: bool = typer.Option(True, help="Scan subdirectories."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Scan and display a summary report of duplicates."""
    detector = _get_detector()
    from file_organizer.services.deduplication.detector import ScanOptions
    from file_organizer.services.deduplication.hasher import HashAlgorithm

    options = ScanOptions(algorithm=cast("HashAlgorithm", algorithm), recursive=recursive)

    with console.status("Scanning…"):
        detector.scan_directory(directory, options)

    stats = detector.get_statistics()
    groups = detector.get_duplicate_groups()

    if json_output:
        console.print_json(json.dumps(stats, indent=2, default=str))
        raise typer.Exit()

    table = Table(title="Duplicate Report")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_row("Duplicate groups", str(len(groups)))
    table.add_row("Total files scanned", str(stats.get("total_files", "?")))
    table.add_row("Total duplicate files", str(stats.get("duplicate_files", "?")))
    total_wasted = sum(g.wasted_space for g in groups.values())
    table.add_row("Wasted space", _format_size(total_wasted))
    console.print(table)
