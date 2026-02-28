"""CLI commands for the plugin marketplace."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from file_organizer.plugins.marketplace import MarketplaceService, PluginPackage

import typer
from rich.console import Console
from rich.table import Table

marketplace_app = typer.Typer(help="Browse and manage marketplace plugins.")
console = Console()


def _service() -> MarketplaceService:
    # Imported lazily to reduce startup latency
    from file_organizer.plugins.marketplace import MarketplaceService

    return MarketplaceService()


def _render_plugins(items: list[PluginPackage]) -> None:
    table = Table(title="Marketplace Plugins", show_lines=False)
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Author")
    table.add_column("Category")
    table.add_column("Rating", justify="right")
    table.add_column("Downloads", justify="right")
    for item in items:
        table.add_row(
            item.name,
            item.version,
            item.author,
            item.category,
            f"{item.rating:.1f}",
            str(item.downloads),
        )
    console.print(table)


@marketplace_app.command("list")
def list_plugins(
    page: int = typer.Option(1, "--page", "-p", min=1, help="Page number."),
    per_page: int = typer.Option(20, "--per-page", min=1, max=100, help="Results per page."),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category."),
    tags: Optional[list[str]] = typer.Option(None, "--tag", "-t", help="Filter by tags."),
) -> None:
    """List available plugins."""
    from file_organizer.plugins.marketplace import MarketplaceError

    try:
        items, total = _service().list_plugins(
            page=page,
            per_page=per_page,
            category=category,
            tags=tags,
        )
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    _render_plugins(items)
    console.print(f"[dim]Showing {len(items)} of {total} plugins.[/dim]")


@marketplace_app.command("search")
def search_plugins(
    query: str = typer.Argument(..., help="Search query."),
    category: Optional[str] = typer.Option(None, "--category", "-c", help="Filter by category."),
    tags: Optional[list[str]] = typer.Option(None, "--tag", "-t", help="Filter by tags."),
) -> None:
    """Search marketplace plugins."""
    from file_organizer.plugins.marketplace import MarketplaceError

    try:
        items, total = _service().list_plugins(
            query=query,
            page=1,
            per_page=200,
            category=category,
            tags=tags,
        )
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    _render_plugins(items)
    console.print(f"[dim]Found {total} matching plugins.[/dim]")


@marketplace_app.command("info")
def plugin_info(
    name: str = typer.Argument(..., help="Plugin name."),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Specific version."),
) -> None:
    """Show detailed plugin metadata."""
    from file_organizer.plugins.marketplace import MarketplaceError

    try:
        package = _service().get_plugin(name, version=version)
        avg_rating = _service().get_average_rating(package.name)
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]{package.name}[/bold] {package.version}")
    console.print(package.description)
    console.print(f"Author: {package.author}")
    console.print(f"Category: {package.category}")
    console.print(f"Tags: {', '.join(package.tags) if package.tags else '-'}")
    console.print(
        f"Dependencies: {', '.join(package.dependencies) if package.dependencies else '-'}"
    )
    console.print(f"Repository rating: {package.rating:.1f} ({package.reviews_count} reviews)")
    console.print(f"Local rating: {avg_rating:.1f}")
    console.print(f"Downloads: {package.downloads}")
    console.print(f"Homepage: {package.homepage or '-'}")


@marketplace_app.command("install")
def install_plugin(
    name: str = typer.Argument(..., help="Plugin name."),
    version: Optional[str] = typer.Option(None, "--version", "-v", help="Specific version."),
) -> None:
    """Install a plugin from marketplace."""
    from file_organizer.plugins.marketplace import MarketplaceError

    try:
        installed = _service().install(name, version=version)
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Installed[/green] {installed.name} {installed.version}")


@marketplace_app.command("uninstall")
def uninstall_plugin(
    name: str = typer.Argument(..., help="Plugin name."),
) -> None:
    """Uninstall a marketplace plugin."""
    from file_organizer.plugins.marketplace import MarketplaceError

    try:
        _service().uninstall(name)
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Uninstalled[/green] {name}")


@marketplace_app.command("update")
def update_plugin(
    name: str = typer.Argument(..., help="Plugin name."),
) -> None:
    """Update an installed plugin."""
    from file_organizer.plugins.marketplace import MarketplaceError

    try:
        result = _service().update(name)
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if result is None:
        console.print(f"[yellow]{name} is already up to date.[/yellow]")
        return
    console.print(f"[green]Updated[/green] {result.name} to {result.version}")


@marketplace_app.command("installed")
def list_installed() -> None:
    """List locally installed marketplace plugins."""
    from file_organizer.plugins.marketplace import MarketplaceError

    try:
        items = _service().list_installed()
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    table = Table(title="Installed Plugins")
    table.add_column("Name", style="cyan")
    table.add_column("Version", style="green")
    table.add_column("Installed At")
    for item in items:
        table.add_row(item.name, item.version, item.installed_at)
    console.print(table)
    console.print(f"[dim]Total installed: {len(items)}[/dim]")


@marketplace_app.command("updates")
def available_updates() -> None:
    """List installed plugins with updates available."""
    from file_organizer.plugins.marketplace import MarketplaceError

    try:
        updates = _service().check_updates()
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if not updates:
        console.print("[green]All installed plugins are up to date.[/green]")
        return
    console.print("[bold]Updates available:[/bold]")
    for item in updates:
        console.print(f"- {item}")


@marketplace_app.command("review")
def add_review(
    name: str = typer.Argument(..., help="Plugin name.", metavar="PLUGIN_NAME"),
    user: str = typer.Option(..., "--user", help="Reviewer ID."),
    rating: int = typer.Option(..., "--rating", min=1, max=5, help="Rating from 1 to 5."),
    title: str = typer.Option(..., "--title", help="Review title."),
    content: str = typer.Option(..., "--content", help="Review text."),
) -> None:
    """Add or update a plugin review."""
    from file_organizer.plugins.marketplace import MarketplaceError, PluginReview

    try:
        _service().add_review(
            PluginReview(
                plugin_name=name,
                user_id=user,
                rating=rating,
                title=title,
                content=content,
            )
        )
    except MarketplaceError as exc:
        console.print(f"[red]Marketplace error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Saved review for[/green] {name}")
