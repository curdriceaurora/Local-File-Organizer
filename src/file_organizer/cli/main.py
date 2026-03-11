"""Main Typer CLI application for File Organizer.

Provides the unified entry point with all commands and sub-apps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

import file_organizer.cli._globals as _g
from file_organizer.cli.api import api_app
from file_organizer.cli.autotag_v2 import autotag_app
from file_organizer.cli.benchmark import benchmark_app
from file_organizer.cli.config_cli import config_app
from file_organizer.cli.copilot import copilot_app
from file_organizer.cli.daemon import daemon_app
from file_organizer.cli.dedupe_v2 import dedupe_app
from file_organizer.cli.marketplace import marketplace_app
from file_organizer.cli.models_cli import model_app
from file_organizer.cli.organize import organize, preview
from file_organizer.cli.rules import rules_app
from file_organizer.cli.suggest import suggest_app
from file_organizer.cli.update import update_app
from file_organizer.cli.utilities import analyze, search

console = Console()

# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="file-organizer",
    help="AI-powered local file management with privacy-first architecture.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

# ---------------------------------------------------------------------------
# State / callbacks
# ---------------------------------------------------------------------------


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without executing."),
    json_output: bool = typer.Option(False, "--json", help="Output results as JSON."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Auto-confirm all prompts."),
    no_interactive: bool = typer.Option(
        False, "--no-interactive", help="Disable interactive prompts."
    ),
) -> None:
    """Global options applied to all commands."""
    _g.verbose = verbose
    _g.dry_run = dry_run
    _g.json_output = json_output
    _g.yes = yes
    _g.no_interactive = no_interactive

    from file_organizer.cli.interactive import set_flags

    set_flags(yes=yes, no_interactive=no_interactive)


# ---------------------------------------------------------------------------
# Top-level commands (registered from sub-modules)
# ---------------------------------------------------------------------------

app.command()(organize)
app.command()(preview)
app.command()(search)
app.command()(analyze)


@app.command()
def version() -> None:
    """Show the application version."""
    from file_organizer.version import __version__

    console.print(f"file-organizer {__version__}")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind address."),
    port: int = typer.Option(8000, help="Port number."),
    reload: bool = typer.Option(False, help="Auto-reload on code changes."),
    workers: int = typer.Option(1, help="Number of worker processes."),
) -> None:
    """Start the File Organizer web server and API."""
    try:
        import uvicorn
    except ImportError as exc:
        console.print(
            "[red]Error: uvicorn is not installed.[/red]\n"
            "Install it with: [bold]pip install uvicorn[standard][/bold]"
        )
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]Starting File Organizer[/bold] at http://{host}:{port}/ui/")

    try:
        uvicorn.run(
            "file_organizer.api.main:create_app",
            factory=True,
            host=host,
            port=port,
            reload=reload,
            workers=workers,
        )
    except OSError as exc:
        console.print(f"[red]Error: {exc}[/red]")
        if "address already in use" in str(exc).lower():
            console.print(
                f"[yellow]Port {port} is already in use. "
                f"Try a different port: file-organizer serve --port {port + 1}[/yellow]"
            )
        raise typer.Exit(code=1) from exc


@app.command(name="tui")
def launch_tui() -> None:
    """Launch the interactive terminal UI."""
    from file_organizer.tui import run_tui

    run_tui()


@app.command(name="hardware-info")
def hardware_info(
    json_out: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Detect and display hardware capabilities."""
    from file_organizer.core.hardware_profile import detect_hardware

    profile = detect_hardware()

    if json_out or _g.json_output:
        import json

        console.print_json(json.dumps(profile.to_dict()))
    else:
        console.print("[bold]Hardware Profile[/bold]")
        console.print(f"  GPU type:            {profile.gpu_type.value}")
        console.print(f"  GPU name:            {profile.gpu_name or 'N/A'}")
        console.print(f"  VRAM:                {profile.vram_gb} GB")
        console.print(f"  System RAM:          {profile.ram_gb} GB")
        console.print(f"  CPU cores:           {profile.cpu_cores}")
        console.print(f"  OS:                  {profile.os_name}")
        console.print(f"  Architecture:        {profile.arch}")
        console.print()
        console.print("[bold]Recommendations[/bold]")
        console.print(f"  Text model:          {profile.recommended_text_model()}")
        console.print(f"  Parallel workers:    {profile.recommended_workers()}")


# ---------------------------------------------------------------------------
# Sub-apps (config, model, and third-party integrations)
# ---------------------------------------------------------------------------

app.add_typer(config_app, name="config")
app.add_typer(model_app, name="model")
app.add_typer(autotag_app, name="autotag")
app.add_typer(benchmark_app, name="benchmark")
app.add_typer(copilot_app, name="copilot")
app.add_typer(daemon_app, name="daemon")
app.add_typer(dedupe_app, name="dedupe")
app.add_typer(api_app, name="api")
app.add_typer(marketplace_app, name="marketplace")
app.add_typer(rules_app, name="rules")
app.add_typer(suggest_app, name="suggest")
app.add_typer(update_app, name="update")


# ---------------------------------------------------------------------------
# Operation history / undo / redo commands
# ---------------------------------------------------------------------------


@app.command()
def undo(
    operation_id: Optional[int] = typer.Option(None, help="Specific operation ID to undo."),
    transaction_id: Optional[str] = typer.Option(None, help="Transaction ID to undo."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without executing."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
) -> None:
    """Undo file operations."""
    from file_organizer.cli.undo_redo import undo_command as _undo

    code = _undo(
        operation_id=operation_id,
        transaction_id=transaction_id,
        dry_run=dry_run or _g.dry_run,
        verbose=verbose or _g.verbose,
    )
    raise typer.Exit(code=code)


@app.command()
def redo(
    operation_id: Optional[int] = typer.Option(None, help="Specific operation ID to redo."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without executing."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
) -> None:
    """Redo file operations."""
    from file_organizer.cli.undo_redo import redo_command as _redo

    code = _redo(
        operation_id=operation_id,
        dry_run=dry_run or _g.dry_run,
        verbose=verbose or _g.verbose,
    )
    raise typer.Exit(code=code)


@app.command()
def history(
    limit: int = typer.Option(10, help="Maximum number of operations to show."),
    operation_type: Optional[str] = typer.Option(None, "--type", help="Filter by type."),
    status: Optional[str] = typer.Option(None, help="Filter by status."),
    stats: bool = typer.Option(False, help="Show statistics."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
) -> None:
    """View operation history."""
    from file_organizer.cli.undo_redo import history_command as _history

    code = _history(
        limit=limit,
        operation_type=operation_type,
        status=status,
        stats=stats,
        verbose=verbose or _g.verbose,
    )
    raise typer.Exit(code=code)


@app.command()
def analytics(
    directory: Optional[Path] = typer.Argument(None, help="Directory to analyze."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
) -> None:
    """Display storage analytics dashboard."""
    from file_organizer.cli.analytics import analytics_command

    args: list[str] = []
    if directory is not None:
        args.append(str(directory))
    if verbose or _g.verbose:
        args.append("--verbose")

    code = analytics_command(args)
    raise typer.Exit(code=code)


# ---------------------------------------------------------------------------
# Profile sub-app — Click interop (deferred to reduce startup latency)
# ---------------------------------------------------------------------------

# NOTE: profile_command registration is deferred to main() to avoid loading
# file_organizer.cli.profile (and its heavy intelligence service chain) at
# module import time.  Typer wraps Click, so we register it just before app().


def _register_profile_command() -> None:
    """Lazily register the Click-based profile sub-command."""
    try:
        from file_organizer.cli.profile import profile_command as _profile_click_group

        typer_click_object = typer.main.get_group(app)
        typer_click_object.add_command(_profile_click_group, "profile")
    except ImportError:
        # Profile module may fail to import if intelligence services
        # are not installed; we degrade gracefully.
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``file-organizer`` / ``fo`` console scripts."""
    _register_profile_command()
    app()


if __name__ == "__main__":
    main()
