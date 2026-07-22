"""Thin CLI adapters for canonical organization preview and execution."""

from __future__ import annotations

import json
from contextlib import nullcontext, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Annotated, Any

import click
import typer
from click.core import ParameterSource
from rich.console import Console
from rich.panel import Panel

from file_organizer.cli.path_validation import (
    resolve_cli_path,
    validate_pair,
    validate_regular_file,
)
from file_organizer.cli.state import _get_state
from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.organization_service import OrganizationScan, OrganizationService
from file_organizer.core.organize_options import OrganizeOptions, OrganizeRequest
from file_organizer.core.plan import OrganizationPlan, PlanValidationError
from file_organizer.core.types import OrganizationResult
from file_organizer.utils.atomic_write import atomic_write_text

console = Console()
_JSON_SCHEMA_VERSION = 1
_PLAN_PARAMETER_FIELDS: dict[str, tuple[str, ...]] = {
    "recursive": ("recursive",),
    "include_hidden": ("include_hidden",),
    "skip_existing": ("skip_existing",),
    "transfer_mode": ("transfer_mode",),
    "methodology": ("methodology",),
    "max_workers": ("parallel_workers",),
    "sequential": ("parallel_workers", "prefetch_depth"),
    "no_vision": ("enable_vision",),
    "prefetch_depth": ("prefetch_depth",),
    "no_prefetch": ("prefetch_depth",),
    "transcribe_audio": ("transcribe_audio",),
    "max_transcribe_seconds": ("max_transcribe_seconds",),
    "whisper_model": ("whisper_model",),
    "text_model": ("text_model",),
    "vision_model": ("vision_model",),
    "text_provider": ("text_provider",),
    "vision_provider": ("vision_provider",),
}


def _check_setup_completed() -> bool:
    """Check if the initial setup wizard has been completed."""
    from file_organizer.config.manager import ConfigManager

    config = ConfigManager().load()
    if not config.setup_completed:
        if _get_state().json_output:
            context = click.get_current_context(silent=True)
            _emit_json(
                {
                    "schema_version": _JSON_SCHEMA_VERSION,
                    "outcome": "error",
                    "command": context.invoked_subcommand if context is not None else None,
                    "error": {
                        "code": "setup_required",
                        "message": "First-time setup is required. Run `fo setup` to continue.",
                        "retryable": False,
                        "details": {"action": "fo setup"},
                    },
                }
            )
            raise typer.Exit(code=1)
        console.print()
        console.print(
            Panel.fit(
                "[bold yellow]First-time setup required[/bold yellow]\n\n"
                "File Organizer needs to be configured before use.\n"
                "Run the setup wizard to get started:\n\n"
                "  [bold cyan]fo setup[/bold cyan]\n\n"
                "This will detect your system capabilities and configure\n"
                "the optimal AI models for your hardware.",
                border_style="yellow",
            )
        )
        console.print()
        raise typer.Exit(code=1)
    return True


def _create_service() -> OrganizationService:
    """Create the application service; kept as an adapter test seam."""
    return OrganizationService()


def _resolve_parallel_settings(
    sequential: bool,
    max_workers: int | None,
    prefetch_depth: int,
    no_prefetch: bool = False,
) -> tuple[int | None, int]:
    """Validate and normalize CLI performance aliases."""
    if sequential and max_workers not in (None, 1):
        raise typer.BadParameter("--sequential cannot be combined with --max-workers > 1")
    return (1 if sequential else max_workers, 0 if (sequential or no_prefetch) else prefetch_depth)


def _print_organize_advanced_help() -> None:
    """Print advanced tuning options for ``fo organize`` and exit."""
    console.print(
        Panel.fit(
            "[bold]Advanced tuning options for `fo organize`[/bold]\n"
            "Use these only when you need tighter control over performance, "
            "media processing, or deterministic execution.",
            border_style="cyan",
        )
    )
    console.print(
        "\n".join(
            [
                "[bold]`--max-workers INTEGER`[/bold] — Cap parallel worker count.",
                "[bold]`--sequential`[/bold] — Force single-worker sequential processing.",
                "[bold]`--prefetch-depth INTEGER`[/bold] — Tune queue-ahead depth per worker.",
                "[bold]`--no-prefetch`[/bold] — Backward-compatible alias for `--prefetch-depth 0`.",
                "[bold]`--no-vision`, `--text-only`[/bold] — Disable image vision processing.",
                "[bold]`--transcribe-audio`[/bold] — Enable audio transcription.",
                "[bold]`--max-transcribe-seconds FLOAT`[/bold] — Set `0` for no cap.",
            ]
        )
    )


def _advanced_help_callback(value: bool) -> None:
    """Print advanced help and stop eager option processing when requested."""
    if value:
        _print_organize_advanced_help()
        raise typer.Exit()


def _build_options(
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
) -> OrganizeOptions:
    """Map every behavior-affecting CLI flag to the canonical contract."""
    workers, resolved_prefetch = _resolve_parallel_settings(
        sequential, max_workers, prefetch_depth, no_prefetch
    )
    try:
        return OrganizeOptions(
            recursive=recursive,
            include_hidden=include_hidden,
            skip_existing=skip_existing,
            transfer_mode=transfer_mode,
            methodology=methodology,
            enable_vision=not no_vision,
            transcribe_audio=transcribe_audio,
            max_transcribe_seconds=(max_transcribe_seconds if max_transcribe_seconds > 0 else None),
            whisper_model=whisper_model,
            parallel_workers=workers,
            prefetch_depth=resolved_prefetch,
            text_model=text_model,
            vision_model=vision_model,
            text_provider=text_provider,  # type: ignore[arg-type]
            vision_provider=vision_provider,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def _merge_explicit_plan_options(
    ctx: typer.Context,
    plan_options: OrganizeOptions,
    cli_options: OrganizeOptions,
) -> OrganizeOptions:
    """Overlay only explicit CLI option fields onto reviewed plan options."""
    merged = plan_options.to_dict()
    explicit = cli_options.to_dict()
    for parameter, fields in _PLAN_PARAMETER_FIELDS.items():
        if ctx.get_parameter_source(parameter) != ParameterSource.COMMANDLINE:
            continue
        for field in fields:
            merged[field] = explicit[field]
    return OrganizeOptions.from_dict(merged)


def _result_payload(result: OrganizationResult) -> dict[str, Any]:
    """Serialize an organization result without its separately emitted plan."""
    return {
        "total_files": result.total_files,
        "processed_files": result.processed_files,
        "skipped_files": result.skipped_files,
        "failed_files": result.failed_files,
        "deduplicated_files": result.deduplicated_files,
        "processing_time": result.processing_time,
        "organized_structure": result.organized_structure,
        "errors": [list(error) for error in result.errors],
        "transaction_id": result.transaction_id,
    }


def _scan_payload(scan: OrganizationScan) -> dict[str, Any]:
    """Serialize a canonical scan into JSON-compatible primitives."""
    return {
        "input_path": str(scan.input_path),
        "files": [str(path) for path in scan.files],
        "counts": scan.counts,
        "total_files": scan.total_files,
    }


def _success_payload(
    command: str,
    request: OrganizeRequest,
    result: OrganizationResult,
    *,
    mode: str,
    scan: OrganizationScan | None = None,
) -> dict[str, Any]:
    """Build the versioned success envelope shared by both CLI commands."""
    return _json_success_payload(
        command,
        mode=mode,
        request={
            "input_path": str(request.input_path),
            "output_path": str(request.output_path),
            "options": request.options.to_dict(),
        },
        scan=_scan_payload(scan) if scan is not None else None,
        result=_result_payload(result),
        plan=result.plan.to_dict() if isinstance(result.plan, OrganizationPlan) else None,
    )


def _json_success_payload(
    command: str,
    *,
    mode: str,
    result: Any,
    request: dict[str, Any] | None = None,
    scan: dict[str, Any] | None = None,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the shared versioned success envelope for CLI adapters."""
    return {
        "schema_version": _JSON_SCHEMA_VERSION,
        "outcome": "ok",
        "command": command,
        "mode": mode,
        "request": request,
        "scan": scan,
        "result": result,
        "plan": plan,
    }


def _emit_json(payload: dict[str, Any]) -> None:
    """Emit exactly one deterministic compact JSON document to stdout."""
    typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":")))


def _save_plan(path: Path, plan: OrganizationPlan) -> Path:
    """Atomically persist a canonical reviewed plan and return its resolved path."""
    resolved = resolve_cli_path(path, must_exist=False, must_be_dir=False)
    validate_regular_file(resolved, "plan output")
    if not resolved.parent.is_dir():
        raise typer.BadParameter(f"Plan output parent does not exist: {resolved.parent}")
    atomic_write_text(resolved, json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n")
    return resolved


def _load_plan(path: Path) -> OrganizationPlan:
    """Load and validate a canonical serialized plan from the CLI boundary."""
    resolved = resolve_cli_path(path, must_exist=True, must_be_dir=False)
    validate_regular_file(resolved, "plan")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("plan document must be a JSON object")
        return OrganizationPlan.from_dict(payload)
    except (OSError, json.JSONDecodeError, ValueError, KeyError, TypeError) as exc:
        raise typer.BadParameter(f"Invalid organization plan {resolved}: {exc}") from exc


def _error_exit_code(exc: Exception) -> int:
    """Map stable domain failure categories onto documented CLI exit codes."""
    if isinstance(exc, DomainError):
        return _error_code_exit_code(exc.code.value)
    return 1


def _error_code_exit_code(code: str) -> int:
    """Map one stable error identifier onto the shared CLI exit categories."""
    if code in {DomainErrorCode.INVALID_REQUEST.value, DomainErrorCode.NOT_FOUND.value}:
        return 2
    if code in {
        DomainErrorCode.CONFLICT.value,
        DomainErrorCode.PLAN_MISMATCH.value,
        DomainErrorCode.RECOVERY_REQUIRED.value,
    }:
        return 3
    return 1


def _raise_cli_contract_error(
    command: str,
    error: dict[str, Any],
    *,
    json_output: bool,
    exit_code: int,
    cause: Exception,
) -> None:
    """Render a normalized CLI error envelope shared by local and remote adapters."""
    if json_output:
        _emit_json(
            {
                "schema_version": _JSON_SCHEMA_VERSION,
                "outcome": "error",
                "command": command,
                "error": error,
            }
        )
    else:
        console.print(f"[red]Error: {error['message']}[/red]")
        if _get_state().debug:
            console.print_exception(show_locals=False)
    raise typer.Exit(code=exit_code) from cause


def _raise_cli_error(command: str, exc: Exception, *, json_output: bool) -> None:
    """Render one normalized failure and terminate with its stable exit code."""
    code = _error_exit_code(exc)
    if isinstance(exc, DomainError):
        error = exc.to_dict()
    elif isinstance(exc, PlanValidationError):
        error = {
            "error_type": type(exc).__name__,
            "message": str(exc),
            "conflicts": [
                {"conflict_type": conflict.conflict_type.value, "path": conflict.path}
                for conflict in exc.validation.conflicts
            ],
        }
    else:
        error = {
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    _raise_cli_contract_error(
        command,
        error,
        json_output=json_output,
        exit_code=code,
        cause=exc,
    )


def _raise_usage_error(command: str, exc: typer.BadParameter, *, json_output: bool) -> None:
    """Keep Typer usage rendering for humans and normalize JSON-mode errors."""
    if json_output:
        code = (
            DomainErrorCode.NOT_FOUND
            if str(exc).startswith("Path does not exist:")
            else DomainErrorCode.INVALID_REQUEST
        )
        _raise_cli_error(
            command,
            DomainError(code, str(exc)),
            json_output=True,
        )
    raise exc


def organize(
    ctx: typer.Context,
    input_dir: Annotated[Path, typer.Argument(help="Directory containing files to organize.")],
    output_dir: Annotated[Path, typer.Argument(help="Destination directory for organized files.")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without applying files.")
    ] = False,
    verbose: Annotated[
        bool,
        typer.Option(
            "--verbose",
            "-v",
            help="Compatibility flag; canonical organization progress is already detailed.",
        ),
    ] = False,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON output.")] = False,
    plan_path: Annotated[
        Path | None, typer.Option("--plan", help="Apply a canonical plan JSON file.")
    ] = None,
    save_plan: Annotated[
        Path | None, typer.Option("--save-plan", help="Write the generated plan as JSON.")
    ] = None,
    recursive: Annotated[
        bool, typer.Option("--recursive/--no-recursive", help="Recurse into subdirectories.")
    ] = True,
    include_hidden: Annotated[
        bool, typer.Option("--include-hidden/--exclude-hidden", help="Include hidden files.")
    ] = False,
    skip_existing: Annotated[
        bool, typer.Option("--skip-existing/--overwrite-existing", help="Skip existing targets.")
    ] = True,
    transfer_mode: Annotated[
        str, typer.Option("--transfer-mode", help="Transfer mode: copy or hardlink.")
    ] = "hardlink",
    methodology: Annotated[
        str, typer.Option("--methodology", help="Layout policy: none, para, or jd.")
    ] = "none",
    advanced_help: Annotated[
        bool,
        typer.Option(
            "--advanced-help",
            callback=_advanced_help_callback,
            is_eager=True,
            help="Show advanced tuning options and exit.",
        ),
    ] = False,
    max_workers: Annotated[int | None, typer.Option("--max-workers", min=1, hidden=True)] = None,
    sequential: Annotated[bool, typer.Option("--sequential", hidden=True)] = False,
    no_vision: Annotated[bool, typer.Option("--no-vision", "--text-only", hidden=True)] = False,
    prefetch_depth: Annotated[int, typer.Option("--prefetch-depth", min=0, hidden=True)] = 2,
    no_prefetch: Annotated[bool, typer.Option("--no-prefetch", hidden=True)] = False,
    transcribe_audio: Annotated[bool, typer.Option("--transcribe-audio", hidden=True)] = False,
    max_transcribe_seconds: Annotated[
        float, typer.Option("--max-transcribe-seconds", min=0.0, hidden=True)
    ] = 600.0,
    whisper_model: Annotated[str, typer.Option("--whisper-model", hidden=True)] = "tiny",
    text_model: Annotated[str | None, typer.Option("--text-model", hidden=True)] = None,
    vision_model: Annotated[str | None, typer.Option("--vision-model", hidden=True)] = None,
    text_provider: Annotated[str | None, typer.Option("--text-provider", hidden=True)] = None,
    vision_provider: Annotated[str | None, typer.Option("--vision-provider", hidden=True)] = None,
) -> None:
    """Preview or apply organization through the canonical application service."""
    _ = (advanced_help, verbose)
    json_output = json_output or _get_state().json_output
    is_preview = dry_run or _get_state().dry_run

    try:
        input_dir = resolve_cli_path(
            input_dir, must_exist=False, must_be_dir=True, reject_symlink=True
        )
        if not input_dir.exists():
            raise DomainError(
                DomainErrorCode.NOT_FOUND,
                f"Input path does not exist: {input_dir}",
                details={"path": str(input_dir)},
            )
        output_dir = resolve_cli_path(output_dir, must_exist=False, must_be_dir=True)
        validate_pair(input_dir, output_dir)
        plan = _load_plan(plan_path) if plan_path is not None else None
        if plan is not None and is_preview:
            raise typer.BadParameter(
                "--plan applies a reviewed plan and cannot be used with --dry-run"
            )
        has_explicit_options = any(
            ctx.get_parameter_source(name) == ParameterSource.COMMANDLINE
            for name in _PLAN_PARAMETER_FIELDS
        )
        if plan is not None and not has_explicit_options:
            options = plan.options
        else:
            cli_options = _build_options(
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
            options = (
                _merge_explicit_plan_options(ctx, plan.options, cli_options)
                if plan is not None
                else cli_options
            )
        request = OrganizeRequest(input_dir, output_dir, options)
        if not json_output:
            console.print(f"[bold]Organizing[/bold] {input_dir} -> {output_dir}")
            if is_preview:
                console.print("[yellow]Dry run mode — no files will be applied.[/yellow]")
        service = _create_service()
        output_guard = redirect_stdout(StringIO()) if json_output else nullcontext()
        with output_guard:
            result = service.preview(request) if is_preview else service.execute(request, plan)
        if save_plan is not None:
            if not isinstance(result.plan, OrganizationPlan):
                raise DomainError(
                    DomainErrorCode.EXECUTION_FAILED,
                    "Organization result did not include a serializable plan.",
                )
            saved_path = _save_plan(save_plan, result.plan)
        else:
            saved_path = None
    except typer.BadParameter as exc:
        _raise_usage_error("organize", exc, json_output=json_output)
    except typer.Exit:
        raise
    except Exception as exc:
        _raise_cli_error("organize", exc, json_output=json_output)

    if json_output:
        _emit_json(
            _success_payload(
                "organize", request, result, mode="preview" if is_preview else "execute"
            )
        )
        return
    if is_preview:
        console.print(f"[green]Preview:[/green] {result.total_files} files would be organized")
    else:
        console.print(
            f"[green]Done:[/green] {result.processed_files} processed, "
            f"{result.skipped_files} skipped, {result.failed_files} failed"
        )
    if saved_path is not None:
        console.print(f"[green]Plan saved:[/green] {saved_path}")


def preview(
    input_dir: Annotated[Path, typer.Argument(help="Directory to preview.")],
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", help="Destination root represented by the plan."),
    ] = None,
    save_plan: Annotated[Path | None, typer.Option("--save-plan", help="Write plan JSON.")] = None,
    json_output: Annotated[bool, typer.Option("--json", help="Emit stable JSON output.")] = False,
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
) -> None:
    """Build a canonical plan without applying filesystem changes."""
    json_output = json_output or _get_state().json_output
    try:
        input_dir = resolve_cli_path(
            input_dir, must_exist=False, must_be_dir=True, reject_symlink=True
        )
        if not input_dir.exists():
            raise DomainError(
                DomainErrorCode.NOT_FOUND,
                f"Input path does not exist: {input_dir}",
                details={"path": str(input_dir)},
            )
        output_dir = (
            resolve_cli_path(output_dir, must_exist=False, must_be_dir=True)
            if output_dir is not None
            else input_dir
        )
        if output_dir != input_dir:
            validate_pair(input_dir, output_dir)
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
        request = OrganizeRequest(input_dir, output_dir, options)
        if not json_output:
            console.print(f"[bold]Previewing[/bold] {input_dir} -> {output_dir}")
        service = _create_service()
        output_guard = redirect_stdout(StringIO()) if json_output else nullcontext()
        with output_guard:
            scan = service.scan(request)
            result = service.preview(request)
        if save_plan is not None:
            if not isinstance(result.plan, OrganizationPlan):
                raise DomainError(
                    DomainErrorCode.EXECUTION_FAILED,
                    "Organization preview did not include a serializable plan.",
                )
            saved_path = _save_plan(save_plan, result.plan)
        else:
            saved_path = None
    except typer.BadParameter as exc:
        _raise_usage_error("preview", exc, json_output=json_output)
    except typer.Exit:
        raise
    except Exception as exc:
        _raise_cli_error("preview", exc, json_output=json_output)

    if json_output:
        _emit_json(_success_payload("preview", request, result, mode="preview", scan=scan))
        return
    console.print(f"[green]Preview:[/green] {result.total_files} files would be organized")
    if saved_path is not None:
        console.print(f"[green]Plan saved:[/green] {saved_path}")
