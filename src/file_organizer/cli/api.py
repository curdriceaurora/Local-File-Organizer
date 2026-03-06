"""CLI wrapper for the HTTP API client libraries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from file_organizer.client.exceptions import ClientError
    from file_organizer.client.sync_client import FileOrganizerClient

import typer
from rich.console import Console
from rich.table import Table

api_app = typer.Typer(
    help="Remote API operations via the official Python client.",
    no_args_is_help=True,
)
console = Console()


def _build_client(
    *,
    base_url: str,
    token: Optional[str],
    api_key: Optional[str],
    timeout: float,
) -> tuple[FileOrganizerClient, type[ClientError]]:
    # Imported lazily to reduce startup latency (~260ms savings at startup)
    from file_organizer.client.exceptions import ClientError
    from file_organizer.client.sync_client import FileOrganizerClient

    return FileOrganizerClient(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
    ), ClientError


def _print_json(payload: object) -> None:
    console.print(json.dumps(payload, indent=2, default=str))


@api_app.command("health")
def health(
    base_url: str = typer.Option("http://localhost:8000", help="API base URL."),
    timeout: float = typer.Option(30.0, help="Request timeout in seconds."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Check API health."""
    client, ClientError = _build_client(
        base_url=base_url, token=None, api_key=None, timeout=timeout
    )
    try:
        result = client.health()
        if as_json:
            _print_json(result.model_dump())
            return
        console.print(f"[green]Status:[/green] {result.status}")
        console.print(f"[green]Version:[/green] {result.version}")
        console.print(f"[green]Environment:[/green] {result.environment}")
    except ClientError as exc:
        console.print(f"[red]API error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()


@api_app.command("login")
def login(
    username: str = typer.Option(..., prompt=True, help="Username."),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="Password."),
    base_url: str = typer.Option("http://localhost:8000", help="API base URL."),
    timeout: float = typer.Option(30.0, help="Request timeout in seconds."),
    save_to: Optional[Path] = typer.Option(
        None,
        "--save-token",
        help="Optional path to save token JSON.",
    ),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Authenticate and print/store access tokens."""
    client, ClientError = _build_client(
        base_url=base_url, token=None, api_key=None, timeout=timeout
    )
    try:
        tokens = client.login(username, password)
        payload = tokens.model_dump()
        if save_to is not None:
            save_to.parent.mkdir(parents=True, exist_ok=True)
            save_to.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            console.print(f"[green]Saved tokens to[/green] {save_to}")
        if as_json:
            _print_json(payload)
        else:
            console.print("[green]Login successful[/green]")
            console.print("Use --json to print token payload.")
    except ClientError as exc:
        console.print(f"[red]Login failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()


@api_app.command("me")
def me(
    token: str = typer.Option(..., "--token", help="Bearer token."),
    base_url: str = typer.Option("http://localhost:8000", help="API base URL."),
    timeout: float = typer.Option(30.0, help="Request timeout in seconds."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Show authenticated user info."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=None, timeout=timeout
    )
    try:
        user = client.me()
        if as_json:
            _print_json(user.model_dump())
            return
        console.print(f"[green]User:[/green] {user.username}")
        console.print(f"[green]Email:[/green] {user.email}")
        console.print(f"[green]Admin:[/green] {user.is_admin}")
    except ClientError as exc:
        console.print(f"[red]Request failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()


@api_app.command("logout")
def logout(
    token: str = typer.Option(..., "--token", help="Bearer token."),
    refresh_token: str = typer.Option(..., "--refresh-token", help="Refresh token to revoke."),
    base_url: str = typer.Option("http://localhost:8000", help="API base URL."),
    timeout: float = typer.Option(30.0, help="Request timeout in seconds."),
) -> None:
    """Revoke the current access/refresh token pair."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=None, timeout=timeout
    )
    try:
        client.logout(refresh_token)
        console.print("[green]Logout successful[/green]")
    except ClientError as exc:
        console.print(f"[red]Logout failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()


@api_app.command("files")
def files_list(
    path: str = typer.Argument(..., help="Directory to list."),
    token: str = typer.Option(..., "--token", help="Bearer token."),
    base_url: str = typer.Option("http://localhost:8000", help="API base URL."),
    recursive: bool = typer.Option(False, help="Include nested files."),
    include_hidden: bool = typer.Option(False, help="Include hidden files."),
    limit: int = typer.Option(100, min=1, max=500, help="Maximum rows."),
    timeout: float = typer.Option(30.0, help="Request timeout in seconds."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """List files via the API client."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=None, timeout=timeout
    )
    try:
        result = client.list_files(
            path,
            recursive=recursive,
            include_hidden=include_hidden,
            limit=limit,
        )
        if as_json:
            _print_json(result.model_dump())
            return
        table = Table(title=f"Files ({result.total})")
        table.add_column("Name")
        table.add_column("Type")
        table.add_column("Size", justify="right")
        for item in result.items:
            table.add_row(item.name, item.file_type, str(item.size))
        console.print(table)
    except ClientError as exc:
        console.print(f"[red]Request failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()


@api_app.command("system-status")
def system_status(
    path: str = typer.Argument(".", help="Path to inspect."),
    token: str = typer.Option(..., "--token", help="Bearer token."),
    base_url: str = typer.Option("http://localhost:8000", help="API base URL."),
    timeout: float = typer.Option(30.0, help="Request timeout in seconds."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Show system status from the API."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=None, timeout=timeout
    )
    try:
        result = client.system_status(path)
        if as_json:
            _print_json(result.model_dump())
            return
        console.print(f"[green]Disk free:[/green] {result.disk_free}")
        console.print(f"[green]Disk used:[/green] {result.disk_used}")
        console.print(f"[green]Active jobs:[/green] {result.active_jobs}")
    except ClientError as exc:
        console.print(f"[red]Request failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()


@api_app.command("system-stats")
def system_stats(
    path: str = typer.Argument(".", help="Directory to analyze."),
    token: str = typer.Option(..., "--token", help="Bearer token."),
    base_url: str = typer.Option("http://localhost:8000", help="API base URL."),
    max_depth: Optional[int] = typer.Option(None, min=1, help="Optional max depth."),
    use_cache: bool = typer.Option(True, help="Use server-side cache."),
    timeout: float = typer.Option(30.0, help="Request timeout in seconds."),
    as_json: bool = typer.Option(False, "--json", help="Print JSON output."),
) -> None:
    """Show storage analytics stats from the API."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=None, timeout=timeout
    )
    try:
        stats = client.system_stats(path=path, max_depth=max_depth, use_cache=use_cache)
        if as_json:
            _print_json(stats.model_dump())
            return
        console.print(f"[green]File count:[/green] {stats.file_count}")
        console.print(f"[green]Directory count:[/green] {stats.directory_count}")
        console.print(f"[green]Total size:[/green] {stats.total_size}")
    except ClientError as exc:
        console.print(f"[red]Request failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()
