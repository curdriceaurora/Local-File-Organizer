"""CLI sub-commands for auto-update management."""

from __future__ import annotations

import typer
from rich.console import Console

update_app = typer.Typer(
    name="update",
    help="Check for and install application updates.",
)

console = Console()


@update_app.command(name="check")
def update_check(
    repo: str = typer.Option(
        "curdriceaurora/Local-File-Organizer",
        "--repo",
        help="GitHub repository to check.",
    ),
    include_prerelease: bool = typer.Option(
        False,
        "--pre",
        help="Include pre-release versions.",
    ),
) -> None:
    """Check if a newer version is available."""
    from file_organizer.updater import UpdateManager

    mgr = UpdateManager(repo=repo, include_prereleases=include_prerelease)
    status = mgr.check()

    console.print(f"[bold]Current version:[/bold] {status.current_version}")

    if status.available and status.release is not None:
        console.print(f"[green]Update available:[/green] {status.latest_version}")
        console.print(f"  Release: {status.release.html_url}")
        if status.release.body:
            console.print(f"\n[dim]{status.release.body[:300]}[/dim]")
        console.print("\nRun [bold]file-organizer update install[/bold] to update.")
    else:
        console.print("[green]Already up to date.[/green]")


@update_app.command(name="install")
def update_install(
    dry_run: bool = typer.Option(False, "--dry-run", help="Download but don't install."),
    repo: str = typer.Option(
        "curdriceaurora/Local-File-Organizer",
        "--repo",
        help="GitHub repository.",
    ),
    include_prerelease: bool = typer.Option(
        False,
        "--pre",
        help="Include pre-release versions.",
    ),
) -> None:
    """Download and install the latest update."""
    from file_organizer.updater import UpdateManager

    mgr = UpdateManager(repo=repo, include_prereleases=include_prerelease)

    with console.status("[bold]Checking for updates..."):
        status = mgr.update(dry_run=dry_run)

    if not status.available:
        console.print("[green]Already up to date.[/green]")
        return

    if status.install_result is None:
        console.print("[red]Update check failed.[/red]")
        raise typer.Exit(code=1)

    if status.install_result.success:
        console.print(f"[green]{status.install_result.message}[/green]")
        if status.install_result.sha256:
            console.print(f"  SHA256: {status.install_result.sha256[:16]}...")
    else:
        console.print(f"[red]{status.install_result.message}[/red]")
        raise typer.Exit(code=1)


@update_app.command(name="rollback")
def update_rollback() -> None:
    """Rollback to the previous version."""
    from file_organizer.updater import UpdateInstaller

    installer = UpdateInstaller()
    if installer.rollback():
        console.print("[green]Rolled back to previous version.[/green]")
    else:
        console.print("[yellow]No backup found to rollback to.[/yellow]")
        raise typer.Exit(code=1)
