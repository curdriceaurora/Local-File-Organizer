# pyre-ignore-all-errors
"""Modern Typer sub-app for smart file organisation suggestions.

Wraps ``SmartSuggestions`` (``SuggestionEngine``) and ``PatternAnalyzer``
to provide ``files``, ``apply``, and ``patterns`` commands.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

console = Console()

suggest_app = typer.Typer(
    name="suggest",
    help="Generate and apply smart file-organisation suggestions.",
    no_args_is_help=True,
)


def _get_engine() -> Any:
    """Lazily import and return a ``SuggestionEngine``."""
    from file_organizer.services.smart_suggestions import SuggestionEngine

    return SuggestionEngine()


def _get_analyzer() -> Any:
    """Lazily import and return a ``PatternAnalyzer``."""
    from file_organizer.services.pattern_analyzer import PatternAnalyzer

    return PatternAnalyzer()


def _collect_files(directory: Path) -> list[Path]:
    """Recursively collect files under *directory*."""
    return [p for p in directory.rglob("*") if p.is_file()]


# -----------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------


@suggest_app.command()
def files(
    directory: Path = typer.Argument(..., help="Directory to generate suggestions for."),
    min_confidence: float = typer.Option(40.0, help="Minimum confidence threshold (0-100)."),
    max_results: int = typer.Option(50, help="Maximum number of suggestions."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Alias for preview mode."),
) -> None:
    """Generate organisation suggestions for files in a directory."""
    engine = _get_engine()
    analyzer = _get_analyzer()
    file_list = _collect_files(directory)

    if not file_list:
        console.print("[yellow]No files found in directory.[/yellow]")
        raise typer.Exit()

    with console.status("Analyzing patterns…"):
        analysis = analyzer.analyze_directory(directory)

    with console.status("Generating suggestions…"):
        suggestions = engine.generate_suggestions(
            file_list,
            pattern_analysis=analysis,
            max_suggestions=max_results,
        )

    suggestions = [s for s in suggestions if s.confidence >= min_confidence]

    if not suggestions:
        console.print("[green]No suggestions above confidence threshold.[/green]")
        raise typer.Exit()

    if json_output:
        data = [
            {
                "id": s.suggestion_id,
                "type": s.suggestion_type.value,
                "file": str(s.file_path),
                "target": str(s.target_path) if s.target_path else None,
                "confidence": round(s.confidence, 1),
                "reasoning": s.reasoning,
            }
            for s in suggestions
        ]
        console.print_json(json.dumps(data, indent=2))
        raise typer.Exit()

    table = Table(title=f"Suggestions ({len(suggestions)})")
    table.add_column("Type", style="bold")
    table.add_column("File")
    table.add_column("Target")
    table.add_column("Confidence", justify="right")
    table.add_column("Reason")
    for s in suggestions:
        table.add_row(
            s.suggestion_type.value,
            str(s.file_path.name),
            str(s.target_path) if s.target_path else "-",
            f"{s.confidence:.0f}%",
            s.reasoning[:60],
        )
    console.print(table)


@suggest_app.command()
def apply(
    directory: Path = typer.Argument(..., help="Directory to organise."),
    min_confidence: float = typer.Option(60.0, help="Minimum confidence for auto-apply."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without changes."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Generate suggestions and apply them (with confirmation)."""
    from file_organizer.cli.interactive import confirm_action

    engine = _get_engine()
    analyzer = _get_analyzer()
    file_list = _collect_files(directory)

    if not file_list:
        console.print("[yellow]No files found.[/yellow]")
        raise typer.Exit()

    with console.status("Analyzing…"):
        analysis = analyzer.analyze_directory(directory)
    with console.status("Generating suggestions…"):
        suggestions = engine.generate_suggestions(file_list, pattern_analysis=analysis)

    suggestions = [s for s in suggestions if s.confidence >= min_confidence]
    if not suggestions:
        console.print("[green]No suggestions to apply.[/green]")
        raise typer.Exit()

    applied = 0
    for s in suggestions:
        label = f"{s.suggestion_type.value}: {s.file_path.name}"
        if s.target_path:
            label += f" -> {s.target_path}"

        if dry_run:
            console.print(f"  [dim]Would apply:[/dim] {label}")
            continue

        if not confirm_action(f"Apply {label}?"):
            continue

        try:
            if s.suggestion_type.value == "move" and s.target_path:
                s.target_path.parent.mkdir(parents=True, exist_ok=True)
                s.file_path.rename(s.target_path)
                applied += 1
            elif s.suggestion_type.value == "rename" and s.new_name:
                new_path = s.file_path.parent / s.new_name
                s.file_path.rename(new_path)
                applied += 1
            else:
                console.print(f"  [dim]Skipped (unsupported type): {label}[/dim]")
        except OSError as exc:
            console.print(f"  [red]Error: {exc}[/red]")

    if dry_run:
        console.print("\n[yellow]Dry run — no changes made.[/yellow]")
    else:
        console.print(f"\n[green]Applied {applied} suggestions.[/green]")


@suggest_app.command()
def patterns(
    directory: Path = typer.Argument(..., help="Directory to analyze."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Detect and display naming/structure patterns in a directory."""
    analyzer = _get_analyzer()

    with console.status("Detecting patterns…"):
        analysis = analyzer.analyze_directory(directory)

    if json_output:
        data = {
            "total_files": analysis.total_files,
            "naming_patterns": [
                {
                    "pattern": p.pattern,
                    "count": p.count,
                    "confidence": round(p.confidence, 1),
                    "description": p.description,
                    "examples": p.example_files[:3],
                }
                for p in analysis.naming_patterns
            ],
            "file_type_distribution": analysis.file_type_distribution,
        }
        console.print_json(json.dumps(data, indent=2))
        raise typer.Exit()

    console.print(f"[bold]Pattern Analysis[/bold] — {analysis.total_files} files\n")

    if analysis.naming_patterns:
        table = Table(title="Naming Patterns")
        table.add_column("Pattern", style="bold")
        table.add_column("Count", justify="right")
        table.add_column("Confidence", justify="right")
        table.add_column("Description")
        table.add_column("Examples")
        for p in analysis.naming_patterns:
            table.add_row(
                p.pattern,
                str(p.count),
                f"{p.confidence:.0f}%",
                p.description,
                ", ".join(p.example_files[:3]),
            )
        console.print(table)
    else:
        console.print("[dim]No naming patterns detected.[/dim]")

    if analysis.file_type_distribution:
        console.print()
        dist_table = Table(title="File Type Distribution")
        dist_table.add_column("Extension", style="bold")
        dist_table.add_column("Count", justify="right")
        for ext, count in sorted(
            analysis.file_type_distribution.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            dist_table.add_row(ext, str(count))
        console.print(dist_table)
