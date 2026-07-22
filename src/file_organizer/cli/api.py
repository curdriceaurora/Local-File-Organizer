# pyre-ignore-all-errors
"""CLI wrapper for the HTTP API client libraries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

if TYPE_CHECKING:
    from file_organizer.client.exceptions import ClientError
    from file_organizer.client.models import OrganizationOptionsPayload, OrganizationPlanPayload
    from file_organizer.client.sync_client import FileOrganizerClient

import typer
from click.core import ParameterSource
from rich.console import Console
from rich.table import Table

from file_organizer.utils.atomic_write import atomic_write_text

api_app = typer.Typer(
    help="Remote API operations via the official Python client.",
    no_args_is_help=True,
)
console = Console()
_REMOTE_PLAN_OPTION_NAMES = (
    "recursive",
    "include_hidden",
    "skip_existing",
    "transfer_mode",
    "methodology",
    "max_workers",
    "sequential",
    "no_vision",
    "prefetch_depth",
    "no_prefetch",
    "transcribe_audio",
    "max_transcribe_seconds",
    "whisper_model",
    "text_model",
    "vision_model",
    "text_provider",
    "vision_provider",
)


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
    """Print one deterministic JSON document without terminal wrapping.

    Args:
        payload: Any Python object to serialize and print as JSON.
    """
    typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str))


def _client_error_payload(exc: ClientError) -> dict[str, Any]:
    """Return the official SDK error without changing its domain meaning."""
    return {
        "error": getattr(exc, "error_code", "") or "client_error",
        "message": getattr(exc, "detail", "") or str(exc),
        "retryable": bool(getattr(exc, "retryable", False)),
        "details": getattr(exc, "details", None) or {},
        "status_code": int(getattr(exc, "status_code", 0)),
    }


def _raise_client_error(label: str, exc: ClientError, *, as_json: bool) -> None:
    """Render one remote failure consistently and terminate the command."""
    if as_json:
        _print_json(_client_error_payload(exc))
    else:
        console.print(f"[red]{label}:[/red] {getattr(exc, 'detail', '') or exc}")
    raise typer.Exit(code=1) from exc


def _raise_request_error(exc: Exception, *, as_json: bool) -> None:
    """Render local option/plan validation failures before any remote request."""
    if as_json:
        _print_json(
            {
                "error": "invalid_request",
                "message": str(exc),
                "retryable": False,
                "details": {},
                "status_code": 0,
            }
        )
        raise typer.Exit(code=2) from exc
    if isinstance(exc, typer.BadParameter):
        raise exc
    raise typer.BadParameter(str(exc)) from exc


def _organization_options(
    *,
    recursive: bool,
    include_hidden: bool,
    skip_existing: bool,
    transfer_mode: str,
    methodology: str,
    no_vision: bool,
    transcribe_audio: bool,
    max_transcribe_seconds: float,
    whisper_model: str,
    sequential: bool,
    max_workers: int | None,
    prefetch_depth: int,
    no_prefetch: bool,
    text_model: str | None,
    vision_model: str | None,
    text_provider: str | None,
    vision_provider: str | None,
) -> OrganizationOptionsPayload:
    """Build the SDK payload from the same canonical CLI mapper as local runs."""
    from file_organizer.cli.organize import _build_options
    from file_organizer.client.models import OrganizationOptionsPayload

    options = _build_options(
        recursive=recursive,
        include_hidden=include_hidden,
        skip_existing=skip_existing,
        transfer_mode=transfer_mode,
        methodology=methodology,
        no_vision=no_vision,
        transcribe_audio=transcribe_audio,
        max_transcribe_seconds=max_transcribe_seconds,
        whisper_model=whisper_model,
        sequential=sequential,
        max_workers=max_workers,
        prefetch_depth=prefetch_depth,
        no_prefetch=no_prefetch,
        text_model=text_model,
        vision_model=vision_model,
        text_provider=text_provider,
        vision_provider=vision_provider,
    )
    return OrganizationOptionsPayload.model_validate(options.to_dict())


def _load_remote_plan(path: Path) -> OrganizationPlanPayload:
    """Load and validate a canonical plan for remote execution."""
    from file_organizer.cli.path_validation import resolve_cli_path, validate_regular_file
    from file_organizer.client.models import OrganizationPlanPayload

    validated = resolve_cli_path(path, must_exist=True, must_be_dir=False)
    validate_regular_file(validated, "plan file")
    return OrganizationPlanPayload.model_validate_json(validated.read_text(encoding="utf-8"))


def _save_remote_plan(path: Path, payload: object) -> Path:
    """Persist a reviewed remote plan atomically."""
    from file_organizer.cli.path_validation import resolve_cli_path

    destination = resolve_cli_path(path, must_exist=False, must_be_dir=False)
    if destination.exists() and not destination.is_file():
        raise typer.BadParameter(f"Plan output path is not a regular file: {destination!s}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(destination, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return destination


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
        _raise_client_error("API error", exc, as_json=as_json)
    finally:
        client.close()


@api_app.command("capabilities")
def remote_capabilities(
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Show which remote capabilities have a fo api command or SDK-only access."""
    from file_organizer.core.capabilities import (
        ExecutionScope,
        ImplementationStatus,
        Surface,
        get_capability_registry,
    )

    rows: list[dict[str, Any]] = []
    for capability in get_capability_registry().capabilities:
        if ExecutionScope.REMOTE not in capability.execution_scopes:
            continue
        cli = capability.support_for(Surface.CLI)
        sdk = capability.support_for(Surface.PYTHON_SDK)
        commands = [entry for entry in cli.entry_points if entry.startswith("fo api ")]
        if commands:
            availability = "available"
        elif sdk.implementation_status is ImplementationStatus.IMPLEMENTED:
            availability = "sdk-only"
        else:
            availability = "unavailable"
        rows.append(
            {
                "capability_id": capability.capability_id,
                "availability": availability,
                "auth_gated": ExecutionScope.AUTH_GATED in capability.execution_scopes,
                "commands": commands,
            }
        )
    if as_json:
        _print_json(rows)
        return
    table = Table(title="Remote capability availability")
    table.add_column("Capability")
    table.add_column("Availability")
    table.add_column("fo api commands")
    for row in rows:
        table.add_row(
            str(row["capability_id"]),
            str(row["availability"]),
            ", ".join(row["commands"]),
        )
    console.print(table)


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
            if save_to.exists() and not save_to.is_file():
                raise typer.BadParameter(f"Token output path is not a regular file: {save_to!s}")
            save_to.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_text(save_to, json.dumps(payload, indent=2) + "\n")
            if not as_json:
                console.print(f"[green]Saved tokens to[/green] {save_to}")
        if as_json:
            _print_json(payload)
        else:
            console.print("[green]Login successful[/green]")
            console.print("Use --json to print token payload.")
    except ClientError as exc:
        _raise_client_error("Login failed", exc, as_json=as_json)
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
        _raise_client_error("Request failed", exc, as_json=as_json)
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
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    recursive: Annotated[bool, typer.Option(help="Include nested files.")] = False,
    include_hidden: Annotated[bool, typer.Option(help="Include hidden files.")] = False,
    limit: Annotated[int, typer.Option(min=1, max=500, help="Maximum rows.")] = 100,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """List files via the API client."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
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
        _raise_client_error("Request failed", exc, as_json=as_json)
    finally:
        client.close()


@api_app.command("scan")
def organization_scan(
    input_dir: Annotated[str, typer.Argument(help="Server-side directory to scan.")],
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    recursive: Annotated[
        bool, typer.Option("--recursive/--no-recursive", help="Include nested files.")
    ] = True,
    include_hidden: Annotated[
        bool, typer.Option("--include-hidden/--exclude-hidden", help="Include hidden files.")
    ] = False,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Scan a remote directory with canonical traversal semantics."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
    )
    try:
        result = client.scan(
            input_dir,
            recursive=recursive,
            include_hidden=include_hidden,
        )
        payload = result.model_dump(mode="json")
        if as_json:
            _print_json(payload)
            return
        console.print(f"[green]Scanned:[/green] {result.total_files} files")
        for category, count in sorted(result.counts.items()):
            console.print(f"  {category}: {count}")
    except ClientError as exc:
        _raise_client_error("Remote scan failed", exc, as_json=as_json)
    finally:
        client.close()


@api_app.command("preview")
def organization_preview(
    input_dir: Annotated[str, typer.Argument(help="Server-side source directory.")],
    output_dir: Annotated[str, typer.Argument(help="Server-side destination directory.")],
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    save_plan: Annotated[
        Path | None, typer.Option("--save-plan", help="Write the reviewed plan as JSON.")
    ] = None,
    recursive: Annotated[bool, typer.Option("--recursive/--no-recursive")] = True,
    include_hidden: Annotated[bool, typer.Option("--include-hidden/--exclude-hidden")] = False,
    skip_existing: Annotated[bool, typer.Option("--skip-existing/--overwrite-existing")] = True,
    transfer_mode: Annotated[str, typer.Option("--transfer-mode")] = "hardlink",
    methodology: Annotated[str, typer.Option("--methodology")] = "none",
    max_workers: Annotated[int | None, typer.Option("--max-workers", min=1)] = None,
    sequential: Annotated[bool, typer.Option("--sequential")] = False,
    no_vision: Annotated[bool, typer.Option("--no-vision", "--text-only")] = False,
    prefetch_depth: Annotated[int, typer.Option("--prefetch-depth", min=0)] = 2,
    no_prefetch: Annotated[bool, typer.Option("--no-prefetch")] = False,
    transcribe_audio: Annotated[bool, typer.Option("--transcribe-audio")] = False,
    max_transcribe_seconds: Annotated[
        float, typer.Option("--max-transcribe-seconds", min=0.0)
    ] = 600.0,
    whisper_model: Annotated[str, typer.Option("--whisper-model")] = "tiny",
    text_model: Annotated[str | None, typer.Option("--text-model")] = None,
    vision_model: Annotated[str | None, typer.Option("--vision-model")] = None,
    text_provider: Annotated[str | None, typer.Option("--text-provider")] = None,
    vision_provider: Annotated[str | None, typer.Option("--vision-provider")] = None,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Build a canonical remote plan without applying it."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
    )
    try:
        if save_plan is not None:
            from file_organizer.cli.path_validation import resolve_cli_path

            save_plan = resolve_cli_path(save_plan, must_exist=False, must_be_dir=False)
        options = _organization_options(
            recursive=recursive,
            include_hidden=include_hidden,
            skip_existing=skip_existing,
            transfer_mode=transfer_mode,
            methodology=methodology,
            no_vision=no_vision,
            transcribe_audio=transcribe_audio,
            max_transcribe_seconds=max_transcribe_seconds,
            whisper_model=whisper_model,
            sequential=sequential,
            max_workers=max_workers,
            prefetch_depth=prefetch_depth,
            no_prefetch=no_prefetch,
            text_model=text_model,
            vision_model=vision_model,
            text_provider=text_provider,
            vision_provider=vision_provider,
        )
        result = client.preview_organize(input_dir, output_dir, options=options)
        payload = result.model_dump(mode="json")
        if save_plan is not None:
            if result.plan is None:
                raise typer.BadParameter("Remote preview did not return an executable plan.")
            destination = _save_remote_plan(save_plan, result.plan.model_dump(mode="json"))
        else:
            destination = None
        if as_json:
            _print_json(payload)
            return
        console.print(f"[green]Preview:[/green] {result.total_files} files")
        if destination is not None:
            console.print(f"[green]Plan saved:[/green] {destination}")
    except ClientError as exc:
        _raise_client_error("Remote preview failed", exc, as_json=as_json)
    except (OSError, ValueError, typer.BadParameter) as exc:
        _raise_request_error(exc, as_json=as_json)
    finally:
        client.close()


@api_app.command("organize")
def organization_execute(
    ctx: typer.Context,
    input_dir: Annotated[str, typer.Argument(help="Server-side source directory.")],
    output_dir: Annotated[str, typer.Argument(help="Server-side destination directory.")],
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    plan_path: Annotated[
        Path | None, typer.Option("--plan", help="Execute a reviewed canonical plan JSON file.")
    ] = None,
    background: Annotated[
        bool,
        typer.Option(
            "--background/--foreground",
            help="Queue the job or wait for its result.",
        ),
    ] = True,
    idempotency_key: Annotated[
        str | None, typer.Option("--idempotency-key", help="Deduplicate background submission.")
    ] = None,
    recursive: Annotated[bool, typer.Option("--recursive/--no-recursive")] = True,
    include_hidden: Annotated[bool, typer.Option("--include-hidden/--exclude-hidden")] = False,
    skip_existing: Annotated[bool, typer.Option("--skip-existing/--overwrite-existing")] = True,
    transfer_mode: Annotated[str, typer.Option("--transfer-mode")] = "hardlink",
    methodology: Annotated[str, typer.Option("--methodology")] = "none",
    max_workers: Annotated[int | None, typer.Option("--max-workers", min=1)] = None,
    sequential: Annotated[bool, typer.Option("--sequential")] = False,
    no_vision: Annotated[bool, typer.Option("--no-vision", "--text-only")] = False,
    prefetch_depth: Annotated[int, typer.Option("--prefetch-depth", min=0)] = 2,
    no_prefetch: Annotated[bool, typer.Option("--no-prefetch")] = False,
    transcribe_audio: Annotated[bool, typer.Option("--transcribe-audio")] = False,
    max_transcribe_seconds: Annotated[
        float, typer.Option("--max-transcribe-seconds", min=0.0)
    ] = 600.0,
    whisper_model: Annotated[str, typer.Option("--whisper-model")] = "tiny",
    text_model: Annotated[str | None, typer.Option("--text-model")] = None,
    vision_model: Annotated[str | None, typer.Option("--vision-model")] = None,
    text_provider: Annotated[str | None, typer.Option("--text-provider")] = None,
    vision_provider: Annotated[str | None, typer.Option("--vision-provider")] = None,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Execute a canonical organization request through the official SDK."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
    )
    try:
        if plan_path is not None:
            from file_organizer.cli.path_validation import resolve_cli_path

            plan_path = resolve_cli_path(plan_path, must_exist=False, must_be_dir=False)
        plan = _load_remote_plan(plan_path) if plan_path is not None else None
        options = None
        has_explicit_options = any(
            ctx.get_parameter_source(name) == ParameterSource.COMMANDLINE
            for name in _REMOTE_PLAN_OPTION_NAMES
        )
        if plan is None or has_explicit_options:
            options = _organization_options(
                recursive=recursive,
                include_hidden=include_hidden,
                skip_existing=skip_existing,
                transfer_mode=transfer_mode,
                methodology=methodology,
                no_vision=no_vision,
                transcribe_audio=transcribe_audio,
                max_transcribe_seconds=max_transcribe_seconds,
                whisper_model=whisper_model,
                sequential=sequential,
                max_workers=max_workers,
                prefetch_depth=prefetch_depth,
                no_prefetch=no_prefetch,
                text_model=text_model,
                vision_model=vision_model,
                text_provider=text_provider,
                vision_provider=vision_provider,
            )
        result = client.organize(
            input_dir,
            output_dir,
            options=options,
            plan=plan,
            run_in_background=background,
            idempotency_key=idempotency_key,
        )
        payload = result.model_dump(mode="json")
        if as_json:
            _print_json(payload)
            return
        if result.job_id is not None:
            console.print(f"[green]Queued job:[/green] {result.job_id}")
        elif result.result is not None:
            console.print(
                f"[green]Done:[/green] {result.result.processed_files} processed, "
                f"{result.result.skipped_files} skipped, {result.result.failed_files} failed"
            )
        else:
            console.print(f"[yellow]Remote status:[/yellow] {result.status}")
    except ClientError as exc:
        _raise_client_error("Remote organization failed", exc, as_json=as_json)
    except (OSError, ValueError, typer.BadParameter) as exc:
        _raise_request_error(exc, as_json=as_json)
    finally:
        client.close()


@api_app.command("job")
def organization_job(
    job_id: Annotated[str, typer.Argument(help="Organization job identifier.")],
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Inspect one remote organization job."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
    )
    try:
        job = client.get_job(job_id)
        if as_json:
            _print_json(job.model_dump(mode="json"))
            return
        console.print(f"[green]Job:[/green] {job.job_id}")
        console.print(f"[green]Status:[/green] {job.status}")
        console.print(f"[green]Revision:[/green] {job.revision}")
    except ClientError as exc:
        _raise_client_error("Remote job lookup failed", exc, as_json=as_json)
    finally:
        client.close()


@api_app.command("jobs")
def organization_jobs(
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    status: Annotated[str | None, typer.Option("--status", help="Filter by job status.")] = None,
    limit: Annotated[int, typer.Option(min=1, max=500, help="Maximum rows.")] = 100,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """List remote organization jobs."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
    )
    try:
        jobs = client.list_jobs(status=status, limit=limit)
        if as_json:
            _print_json([job.model_dump(mode="json") for job in jobs])
            return
        table = Table(title=f"Organization jobs ({len(jobs)})")
        table.add_column("Job")
        table.add_column("Status")
        table.add_column("Revision", justify="right")
        for job in jobs:
            table.add_row(job.job_id, job.status, str(job.revision))
        console.print(table)
    except ClientError as exc:
        _raise_client_error("Remote job listing failed", exc, as_json=as_json)
    finally:
        client.close()


def _mutate_organization_job(
    action: str,
    job_id: str,
    *,
    expected_revision: int | None,
    token: str | None,
    api_key: str | None,
    base_url: str,
    timeout: float,
    as_json: bool,
) -> None:
    """Apply one revision-guarded remote lifecycle action."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
    )
    try:
        operation = client.cancel_job if action == "cancel" else client.rollback_job
        job = operation(job_id, expected_revision=expected_revision)
        if as_json:
            _print_json(job.model_dump(mode="json"))
            return
        console.print(f"[green]Job {action} accepted:[/green] {job.job_id} ({job.status})")
    except ClientError as exc:
        _raise_client_error(f"Remote job {action} failed", exc, as_json=as_json)
    finally:
        client.close()


@api_app.command("cancel")
def organization_cancel(
    job_id: Annotated[str, typer.Argument(help="Organization job identifier.")],
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    expected_revision: Annotated[
        int | None, typer.Option("--expected-revision", min=0, help="Optimistic revision guard.")
    ] = None,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Cancel a queued or scheduled remote organization job."""
    _mutate_organization_job(
        "cancel",
        job_id,
        expected_revision=expected_revision,
        token=token,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        as_json=as_json,
    )


@api_app.command("rollback")
def organization_rollback(
    job_id: Annotated[str, typer.Argument(help="Organization job identifier.")],
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    expected_revision: Annotated[
        int | None, typer.Option("--expected-revision", min=0, help="Optimistic revision guard.")
    ] = None,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Roll back a completed remote organization job."""
    _mutate_organization_job(
        "rollback",
        job_id,
        expected_revision=expected_revision,
        token=token,
        api_key=api_key,
        base_url=base_url,
        timeout=timeout,
        as_json=as_json,
    )


@api_app.command("suggest")
def organization_suggest(
    filename: Annotated[str, typer.Argument(help="File name to classify remotely.")],
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    folder_suggestion: Annotated[
        str | None, typer.Option("--folder-suggestion", help="Optional suggested folder hint.")
    ] = None,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Request a non-mutating remote organization suggestion."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
    )
    try:
        payload = client.suggest_organization(
            filename,
            folder_suggestion=folder_suggestion,
        )
        if as_json:
            _print_json(payload)
            return
        console.print(f"[green]File:[/green] {payload.get('filename', filename)}")
        console.print(f"[green]Folder:[/green] {payload.get('folder_suggestion', '')}")
    except ClientError as exc:
        _raise_client_error("Remote suggestion failed", exc, as_json=as_json)
    finally:
        client.close()


@api_app.command("system-status")
def system_status(
    path: Annotated[str, typer.Argument(help="Path to inspect.")] = ".",
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Show system status from the API."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
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
        _raise_client_error("Request failed", exc, as_json=as_json)
    finally:
        client.close()


@api_app.command("system-stats")
def system_stats(
    path: Annotated[str, typer.Argument(help="Directory to analyze.")] = ".",
    token: Annotated[str | None, typer.Option("--token", help="Bearer token.")] = None,
    api_key: Annotated[str | None, typer.Option("--api-key", help="API key.")] = None,
    base_url: Annotated[str, typer.Option(help="API base URL.")] = "http://localhost:8000",
    max_depth: Annotated[int | None, typer.Option(min=1, help="Optional max depth.")] = None,
    use_cache: Annotated[bool, typer.Option(help="Use server-side cache.")] = True,
    timeout: Annotated[float, typer.Option(help="Request timeout in seconds.")] = 30.0,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON output.")] = False,
) -> None:
    """Show storage analytics stats from the API."""
    client, ClientError = _build_client(
        base_url=base_url, token=token, api_key=api_key, timeout=timeout
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
        _raise_client_error("Request failed", exc, as_json=as_json)
    finally:
        client.close()
