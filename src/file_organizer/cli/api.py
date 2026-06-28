# pyre-ignore-all-errors
"""CLI wrapper for the HTTP API client libraries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

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
    token: str | None,
    api_key: str | None,
    timeout: float,
) -> tuple[FileOrganizerClient, type[ClientError]]:
    """Build an API client with the given configuration.

    Lazily imports client libraries to reduce startup latency (~260ms savings).

    Args:
        base_url: Base URL of the API endpoint.
        token: Optional bearer token for authentication.
        api_key: Optional API key for authentication.
        timeout: Request timeout in seconds.

    Returns:
        Tuple of (FileOrganizerClient instance, ClientError exception class).
    """
    # Imported lazily to reduce startup latency (~260ms savings at startup)
    from file_organizer.client.exceptions import ClientError
    from file_organizer.client.sync_client import FileOrganizerClient

    return FileOrganizerClient(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
    ), ClientError


def _print_json(payload: object) -> None:
    """Print a payload as formatted JSON to the console.

    Args:
        payload: Any Python object to serialize and print as JSON.
    """
    console.print(json.dumps(payload, indent=2, default=str))


@api_app.command("health")
def health(
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
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
        console.print(f"[green]Readiness:[/green] {result.readiness}")
    except ClientError as exc:
        console.print(f"[red]API error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        client.close()


@api_app.command("login")
def login(
    username: Annotated[str, typer.Option(prompt=True, help="Username.")],
    password: Annotated[str, typer.Option(prompt=True, hide_input=True, help="Password.")],
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    save_to: Annotated[
        Path | None,
        typer.Option("--save-token", help="Optional path to save token JSON."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Authenticate and print/store access tokens."""
    client, ClientError = _build_client(
        base_url=base_url, token=None, api_key=None, timeout=timeout
    )
    try:
        tokens = client.login(username, password)
        payload = tokens.model_dump()
        if save_to is not None:
            from file_organizer.cli.path_validation import resolve_cli_path

            save_to = resolve_cli_path(save_to, must_exist=False, must_be_dir=False)
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
    token: Annotated[str, typer.Option("--token", help="Bearer token.")],
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
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
    token: Annotated[str, typer.Option("--token", help="Bearer token.")],
    refresh_token: Annotated[str, typer.Option("--refresh-token", help="Refresh token to revoke.")],
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
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
    path: Annotated[str, typer.Argument(help="Directory to list.")],
    token: Annotated[str, typer.Option("--token", help="Bearer token.")],
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    recursive: Annotated[bool, typer.Option(help="Include nested files.")] = False,
    include_hidden: Annotated[bool, typer.Option(help="Include hidden files.")] = False,
    limit: Annotated[int, typer.Option(min=1, max=500, help="Maximum rows.")] = 100,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
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
    token: Annotated[str, typer.Option("--token", help="Bearer token.")],
    path: Annotated[str, typer.Argument(help="Path to inspect.")] = ".",
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
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
    token: Annotated[str, typer.Option("--token", help="Bearer token.")],
    path: Annotated[str, typer.Argument(help="Directory to analyze.")] = ".",
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    max_depth: Annotated[int | None, typer.Option(min=1, help="Optional max depth.")] = None,
    use_cache: Annotated[bool, typer.Option(help="Use server-side cache.")] = True,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
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
