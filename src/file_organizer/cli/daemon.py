"""Daemon control and pipeline CLI commands.

Provides sub-commands for starting, stopping, and monitoring the
background file organization daemon, plus a one-shot ``process`` command.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

console = Console()

daemon_app = typer.Typer(
    name="daemon",
    help="Background daemon control and file processing pipeline.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)

_DEFAULT_PID_DIR = Path.home() / ".file-organizer"
_DEFAULT_PID_FILE = _DEFAULT_PID_DIR / "daemon.pid"


@daemon_app.command()
def start(
    watch_dir: Optional[Path] = typer.Option(  # noqa: UP045
        None, "--watch-dir", "-w", help="Directory to watch for new files."
    ),
    output_dir: Optional[Path] = typer.Option(  # noqa: UP045
        None, "--output-dir", "-o", help="Destination directory for organized files."
    ),
    foreground: bool = typer.Option(
        False, "--foreground", "-f", help="Run in the foreground (blocking)."
    ),
    poll_interval: float = typer.Option(
        1.0, "--poll-interval", help="Seconds between file-system polls."
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without moving files."),
) -> None:
    """Start the background file organization daemon."""
    from file_organizer.daemon.config import DaemonConfig
    from file_organizer.daemon.service import DaemonService

    watch_dirs = [watch_dir] if watch_dir else []
    out = output_dir or Path("organized_output")

    config = DaemonConfig(
        watch_directories=watch_dirs,
        output_directory=out,
        pid_file=_DEFAULT_PID_FILE,
        dry_run=dry_run,
        poll_interval=poll_interval,
    )

    service = DaemonService(config)

    if foreground:
        console.print(f"[bold]Starting daemon[/bold] (foreground, poll={poll_interval}s)")
        if dry_run:
            console.print("[yellow]Dry-run mode — no files will be moved.[/yellow]")
        try:
            service.start()
        except KeyboardInterrupt:
            console.print("\n[dim]Daemon stopped by user.[/dim]")
    else:
        console.print("[bold]Starting daemon[/bold] in background...")
        if dry_run:
            console.print("[yellow]Dry-run mode — no files will be moved.[/yellow]")
        service.start_background()
        console.print(f"[green]Daemon started.[/green]  PID file: {_DEFAULT_PID_FILE}")


@daemon_app.command()
def stop() -> None:
    """Stop the running daemon."""
    from file_organizer.daemon.pid import PidFileManager

    mgr = PidFileManager()

    if not _DEFAULT_PID_FILE.exists():
        console.print("[yellow]No PID file found — daemon may not be running.[/yellow]")
        raise typer.Exit(code=1)

    pid = mgr.read_pid(_DEFAULT_PID_FILE)
    if pid is None:
        console.print("[yellow]Could not read PID from file.[/yellow]")
        mgr.remove_pid(_DEFAULT_PID_FILE)
        raise typer.Exit(code=1)

    console.print(f"Sending SIGTERM to PID {pid}...")
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        console.print("[yellow]Process not found — cleaning up PID file.[/yellow]")
        mgr.remove_pid(_DEFAULT_PID_FILE)
        raise typer.Exit(code=0) from None
    except PermissionError:
        console.print("[red]Permission denied. Try running with sudo.[/red]")
        raise typer.Exit(code=1) from None

    mgr.remove_pid(_DEFAULT_PID_FILE)
    console.print("[green]Daemon stopped.[/green]")


@daemon_app.command()
def status() -> None:
    """Show the current daemon status."""
    from file_organizer.daemon.pid import PidFileManager

    mgr = PidFileManager()
    running = mgr.is_running(_DEFAULT_PID_FILE)
    pid = mgr.read_pid(_DEFAULT_PID_FILE) if _DEFAULT_PID_FILE.exists() else None

    table = Table(title="Daemon Status")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    table.add_row("State", "[green]Running[/green]" if running else "[dim]Stopped[/dim]")
    table.add_row("PID", str(pid) if pid else "—")
    table.add_row("PID File", str(_DEFAULT_PID_FILE))
    table.add_row(
        "Python",
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    )

    console.print(table)


@daemon_app.command()
def watch(
    watch_dir: Path = typer.Argument(..., help="Directory to watch for file events."),
    poll_interval: float = typer.Option(1.0, "--poll-interval", help="Seconds between polls."),
) -> None:
    """Watch a directory and stream file events (Ctrl+C to stop)."""
    from file_organizer.watcher.config import WatcherConfig
    from file_organizer.watcher.monitor import FileMonitor

    console.print(f"[bold]Watching[/bold] {watch_dir}  (Ctrl+C to stop)")

    config = WatcherConfig(
        watch_directories=[watch_dir],
        debounce_seconds=poll_interval,
    )
    monitor = FileMonitor(config=config)
    monitor.start()

    try:
        while True:
            events = monitor.get_events_blocking(timeout=2.0)
            for event in events:
                event_type = getattr(event, "event_type", "unknown")
                event_path = getattr(event, "path", getattr(event, "src_path", "?"))
                console.print(f"  [{event_type}] {event_path}")
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped watching.[/dim]")
    finally:
        monitor.stop()


@daemon_app.command()
def process(
    input_dir: Path = typer.Argument(..., help="Directory containing files to process."),
    output_dir: Path = typer.Argument(..., help="Destination directory for organized files."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without moving files."),
) -> None:
    """One-shot: organize files and display a summary."""
    from file_organizer.core.organizer import FileOrganizer

    console.print(f"[bold]Processing[/bold] {input_dir} -> {output_dir}")
    if dry_run:
        console.print("[yellow]Dry-run mode — no files will be moved.[/yellow]")

    try:
        organizer = FileOrganizer(dry_run=dry_run)
        result = organizer.organize(input_path=input_dir, output_path=output_dir)

        table = Table(title="Processing Summary")
        table.add_column("Metric", style="bold")
        table.add_column("Count", justify="right")

        table.add_row("Total files", str(result.total_files))
        table.add_row("Processed", str(result.processed_files))
        table.add_row("Skipped", str(result.skipped_files))
        table.add_row("Failed", str(result.failed_files))
        table.add_row("Folders", str(len(result.organized_structure)))

        console.print(table)

        if result.errors:
            console.print("\n[bold red]Errors:[/bold red]")
            for fname, msg in result.errors[:10]:
                console.print(f"  {fname}: {msg}")
            if len(result.errors) > 10:
                console.print(f"  [dim]... and {len(result.errors) - 10} more[/dim]")

    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise typer.Exit(code=1) from exc
