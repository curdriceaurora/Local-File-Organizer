"""Main Typer CLI application for File Organizer.

Provides the unified entry point with all commands and sub-apps.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from file_organizer.cli.api import api_app
from file_organizer.cli.autotag_v2 import autotag_app
from file_organizer.cli.benchmark import benchmark_app
from file_organizer.cli.copilot import copilot_app
from file_organizer.cli.daemon import daemon_app
from file_organizer.cli.dedupe_v2 import dedupe_app
from file_organizer.cli.marketplace import marketplace_app
from file_organizer.cli.rules import rules_app
from file_organizer.cli.suggest import suggest_app
from file_organizer.cli.update import update_app

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

_verbose = False
_dry_run = False
_json_output = False
_yes = False
_no_interactive = False


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
    global _verbose, _dry_run, _json_output, _yes, _no_interactive
    _verbose = verbose
    _dry_run = dry_run
    _json_output = json_output
    _yes = yes
    _no_interactive = no_interactive

    from file_organizer.cli.interactive import set_flags

    set_flags(yes=yes, no_interactive=no_interactive)


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


@app.command()
def version() -> None:
    """Show the application version."""
    from file_organizer.version import __version__

    console.print(f"file-organizer {__version__}")


@app.command()
def organize(
    input_dir: Path = typer.Argument(..., help="Directory containing files to organize."),
    output_dir: Path = typer.Argument(..., help="Destination directory for organized files."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without moving files."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output."),
) -> None:
    """Organize files in a directory using AI models."""
    console.print(f"[bold]Organizing[/bold] {input_dir} -> {output_dir}")
    if dry_run or _dry_run:
        console.print("[yellow]Dry run mode — no files will be moved.[/yellow]")

    try:
        from file_organizer.core.organizer import FileOrganizer

        organizer = FileOrganizer(dry_run=dry_run or _dry_run)
        result = organizer.organize(input_dir, output_dir)
        console.print(
            f"[green]Done:[/green] {result.processed_files} processed, "
            f"{result.skipped_files} skipped, {result.failed_files} failed"
        )
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc


@app.command()
def preview(
    input_dir: Path = typer.Argument(..., help="Directory to preview."),
) -> None:
    """Preview how files would be organized (dry-run)."""
    console.print(f"[bold]Previewing[/bold] {input_dir}")
    try:
        from file_organizer.core.organizer import FileOrganizer

        organizer = FileOrganizer(dry_run=True)
        result = organizer.organize(input_dir, input_dir)
        console.print(
            f"[green]Preview:[/green] {result.total_files} files would be organized"
        )
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc


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

    console.print(
        f"[bold]Starting File Organizer[/bold] at http://{host}:{port}/ui/"
    )

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


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (glob pattern or keyword)."),
    directory: Path = typer.Argument(
        ".", help="Directory to search in.", exists=False
    ),
    type_filter: Optional[str] = typer.Option(
        None,
        "--type",
        "-t",
        help="Filter by type: text, image, video, audio, archive.",
    ),
    limit: int = typer.Option(50, "--limit", "-n", help="Max results to show."),
    recursive: bool = typer.Option(True, help="Search subdirectories."),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON array."),
) -> None:
    """Search for files by name pattern with optional type filtering."""
    import json as json_mod
    from datetime import UTC, datetime

    # File type extension mappings
    type_extensions: dict[str, set[str]] = {
        "text": {
            ".txt", ".md", ".pdf", ".docx", ".doc", ".csv", ".xlsx", ".xls",
            ".ppt", ".pptx", ".epub", ".py", ".js", ".ts", ".html", ".css",
            ".json", ".yaml", ".yml", ".xml", ".rst", ".tex", ".log", ".cfg",
            ".ini", ".toml",
        },
        "image": {
            ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
            ".webp", ".svg", ".ico",
        },
        "video": {
            ".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm",
        },
        "audio": {
            ".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".wma",
        },
        "archive": {
            ".zip", ".7z", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".rar",
            ".gz", ".bz2",
        },
    }

    # Validate directory exists
    search_dir = directory.resolve()
    if not search_dir.is_dir():
        console.print(f"[red]Error: Directory '{directory}' does not exist.[/red]")
        raise typer.Exit(code=1)

    # Validate type filter
    if type_filter is not None and type_filter not in type_extensions:
        console.print(
            f"[red]Error: Unknown type '{type_filter}'. "
            f"Choose from: {', '.join(sorted(type_extensions))}[/red]"
        )
        raise typer.Exit(code=1)

    # Determine if query is a glob pattern or keyword
    is_glob = any(c in query for c in ("*", "?", "["))

    # Collect matching files
    matches: list[Path] = []

    if is_glob:
        # Use the glob pattern directly
        if recursive:
            candidates = search_dir.rglob(query)
        else:
            candidates = search_dir.glob(query)
    else:
        # For keyword search, enumerate all files and filter by name
        # This ensures case-insensitive matching across all platforms
        if recursive:
            candidates = search_dir.rglob("*")
        else:
            candidates = search_dir.glob("*")

    query_lower = query.lower()

    for path in candidates:
        if not path.is_file():
            continue

        # Case-insensitive substring matching for non-glob keyword queries
        if not is_glob:
            if query_lower not in path.name.lower():
                continue

        # Apply type filter
        if type_filter is not None:
            suffix = path.suffix.lower()
            # Handle compound extensions like .tar.gz
            if suffix == ".gz" and path.stem.endswith(".tar"):
                suffix = ".tar.gz"
            elif suffix == ".bz2" and path.stem.endswith(".tar"):
                suffix = ".tar.bz2"
            if suffix not in type_extensions[type_filter]:
                continue

        matches.append(path)
        if len(matches) >= limit:
            break

    # Output results
    if not matches:
        if json_out:
            typer.echo("[]")
        else:
            console.print("[dim]No files found matching the query.[/dim]")
        raise typer.Exit(code=0)

    if json_out:
        records = []
        for p in matches:
            stat = p.stat()
            records.append({
                "path": str(p),
                "size": stat.st_size,
                "modified": datetime.fromtimestamp(
                    stat.st_mtime, tz=UTC
                ).isoformat(),
            })
        typer.echo(json_mod.dumps(records, indent=2))
    else:
        typer.echo(f"Found {len(matches)} file(s):")
        for p in matches:
            stat = p.stat()
            size = stat.st_size
            if size < 1024:
                size_str = f"{size} B"
            elif size < 1024 * 1024:
                size_str = f"{size / 1024:.1f} KB"
            else:
                size_str = f"{size / (1024 * 1024):.1f} MB"

            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
            typer.echo(f"  {p}  {size_str}  {mtime.strftime('%Y-%m-%d %H:%M')}")


@app.command()
def analyze(
    file_path: Path = typer.Argument(..., help="File to analyze."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show additional details."),
    json_output: bool = typer.Option(False, "--json", help="Output as JSON."),
) -> None:
    """Analyze a file using AI and show description, category, and confidence."""
    import json as json_mod
    import time

    from file_organizer.services.analyzer import (
        calculate_confidence,
        generate_category,
        generate_description,
        truncate_content,
    )

    # Check file exists
    if not file_path.exists():
        console.print(f"[red]Error: File '{file_path}' not found.[/red]")
        raise typer.Exit(code=1)

    # Read file content
    try:
        content = file_path.read_text(errors="ignore")
    except Exception:
        content = ""

    content_length = len(content)
    content = truncate_content(content)

    # Initialize model
    try:
        from file_organizer.models.text_model import TextModel

        config = TextModel.get_default_config()
        model = TextModel(config)
        model.initialize()
    except ImportError as exc:
        console.print(
            "[red]Error: Ollama is not available. "
            "Please install Ollama to use AI analysis.[/red]"
        )
        raise typer.Exit(code=1) from exc

    # Run analysis
    start = time.monotonic()
    try:
        category = generate_category(model, content)
        description = generate_description(model, content)
        confidence = calculate_confidence(content, description)
    except RuntimeError as exc:
        console.print(f"[red]Error: AI analysis failed: {exc}[/red]")
        raise typer.Exit(code=1) from exc

    elapsed = time.monotonic() - start

    # Output
    if json_output or _json_output:
        typer.echo(
            json_mod.dumps(
                {
                    "description": description,
                    "category": category,
                    "confidence": confidence,
                },
                indent=2,
            )
        )
    else:
        console.print(f"[bold]Category:[/bold] {category}")
        console.print(f"[bold]Description:[/bold] {description}")
        console.print(f"[bold]Confidence:[/bold] {confidence:.0%}")

        if verbose or _verbose:
            console.print(f"[bold]Model:[/bold] {config.name}")
            console.print(f"[bold]Processing time:[/bold] {elapsed:.2f}s")
            console.print(f"[bold]Content length:[/bold] {content_length} chars")


@app.command(name="tui")
def launch_tui() -> None:
    """Launch the interactive terminal UI."""
    from file_organizer.tui import run_tui

    run_tui()


# ---------------------------------------------------------------------------
# Config sub-app
# ---------------------------------------------------------------------------

config_app = typer.Typer(help="Configuration management.")
app.add_typer(config_app, name="config")


@config_app.command(name="show")
def config_show(
    profile: str = typer.Option("default", help="Profile name."),
) -> None:
    """Show current configuration."""
    from file_organizer.config import ConfigManager

    mgr = ConfigManager()
    cfg = mgr.load(profile=profile)
    console.print(f"[bold]Profile:[/bold] {cfg.profile_name}")
    console.print(f"[bold]Methodology:[/bold] {cfg.default_methodology}")
    console.print(f"[bold]Text model:[/bold] {cfg.models.text_model}")
    console.print(f"[bold]Vision model:[/bold] {cfg.models.vision_model}")
    console.print(f"[bold]Temperature:[/bold] {cfg.models.temperature}")
    console.print(f"[bold]Device:[/bold] {cfg.models.device}")
    console.print(
        f"[bold]Update checks:[/bold] {'enabled' if cfg.updates.check_on_startup else 'disabled'}"
    )
    console.print(f"[bold]Update interval (hrs):[/bold] {cfg.updates.interval_hours}")
    console.print(f"[bold]Update repo:[/bold] {cfg.updates.repo}")
    console.print(f"[bold]Include prereleases:[/bold] {cfg.updates.include_prereleases}")


@config_app.command(name="list")
def config_list() -> None:
    """List available configuration profiles."""
    from file_organizer.config import ConfigManager

    mgr = ConfigManager()
    profiles = mgr.list_profiles()
    if not profiles:
        console.print("No profiles found. Run [bold]config edit[/bold] to create one.")
        return
    for name in profiles:
        console.print(f"  {name}")


@config_app.command(name="edit")
def config_edit(
    profile: str = typer.Option("default", help="Profile name to edit."),
    text_model: Optional[str] = typer.Option(None, help="Set text model name."),
    vision_model: Optional[str] = typer.Option(None, help="Set vision model name."),
    temperature: Optional[float] = typer.Option(None, help="Set temperature (0.0-1.0)."),
    device: Optional[str] = typer.Option(None, help="Set device (auto, cpu, cuda, mps, metal)."),
    methodology: Optional[str] = typer.Option(
        None, help="Set default methodology (none, para, jd)."
    ),
) -> None:
    """Edit a configuration profile."""
    from file_organizer.config import ConfigManager

    mgr = ConfigManager()
    cfg = mgr.load(profile=profile)

    if text_model is not None:
        cfg.models.text_model = text_model
    if vision_model is not None:
        cfg.models.vision_model = vision_model
    if temperature is not None:
        cfg.models.temperature = temperature
    if device is not None:
        cfg.models.device = device
    if methodology is not None:
        cfg.default_methodology = methodology

    mgr.save(cfg, profile=profile)
    console.print(f"[green]Saved profile '{profile}'[/green]")


# ---------------------------------------------------------------------------
# Model sub-app
# ---------------------------------------------------------------------------

model_app = typer.Typer(help="AI model management.")
app.add_typer(model_app, name="model")


@model_app.command(name="list")
def model_list(
    type_filter: Optional[str] = typer.Option(
        None, "--type", help="Filter by model type (text, vision, audio)."
    ),
) -> None:
    """List available AI models with install status."""
    from file_organizer.models.model_manager import ModelManager

    mgr = ModelManager(console=console)
    mgr.display_models(type_filter=type_filter)


@model_app.command(name="pull")
def model_pull(
    name: str = typer.Argument(
        ..., help="Model name to download (e.g. qwen2.5:3b-instruct-q4_K_M)."
    ),
) -> None:
    """Download an AI model via Ollama."""
    from file_organizer.models.model_manager import ModelManager

    mgr = ModelManager(console=console)
    success = mgr.pull_model(name)
    if not success:
        raise typer.Exit(code=1)


@model_app.command(name="cache")
def model_cache() -> None:
    """Show model cache statistics."""
    from file_organizer.models.model_manager import ModelManager

    mgr = ModelManager(console=console)
    info = mgr.cache_info()
    if not info:
        console.print("[dim]No cache data available.[/dim]")
        return
    for key, value in info.items():
        console.print(f"[bold]{key}:[/bold] {value}")


# ---------------------------------------------------------------------------
# Legacy command wrappers
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Dedupe & Suggest sub-apps
# ---------------------------------------------------------------------------

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
        dry_run=dry_run or _dry_run,
        verbose=verbose or _verbose,
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
        dry_run=dry_run or _dry_run,
        verbose=verbose or _verbose,
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
        verbose=verbose or _verbose,
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
    if verbose or _verbose:
        args.append("--verbose")

    code = analytics_command(args)
    raise typer.Exit(code=code)


# ---------------------------------------------------------------------------
# Profile sub-app — Click interop
# ---------------------------------------------------------------------------

# The existing profile module uses Click. Typer is built on Click,
# so we can attach the Click group directly as a sub-command.

try:
    from file_organizer.cli.profile import profile_command as _profile_click_group

    typer_click_object = typer.main.get_group(app)
    typer_click_object.add_command(_profile_click_group, "profile")
except Exception:
    # Profile module may fail to import if intelligence services
    # are not installed; we degrade gracefully.
    pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for ``file-organizer`` / ``fo`` console scripts."""
    app()
