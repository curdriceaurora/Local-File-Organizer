"""Organize and preview CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel

from file_organizer.cli.path_validation import resolve_cli_path, validate_pair
from file_organizer.cli.state import _get_state

console = Console()


def _check_setup_completed() -> bool:
    """Check if the initial setup wizard has been completed.

    Returns:
        True if setup is complete, False otherwise.

    Raises:
        typer.Exit: With code 1 if setup is not completed.
    """
    from file_organizer.config.manager import ConfigManager

    config_manager = ConfigManager()
    config = config_manager.load()

    if not config.setup_completed:
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


def _resolve_parallel_settings(
    sequential: bool,
    max_workers: int | None,
    prefetch_depth: int,
    no_prefetch: bool = False,
) -> tuple[int | None, int]:
    """Validate and resolve parallel worker/prefetch settings.

    Args:
        sequential: Whether to force single-worker sequential processing.
        max_workers: Requested worker count, or None for auto.
        prefetch_depth: Requested prefetch queue depth.
        no_prefetch: Backward-compatible alias for prefetch_depth=0.

    Returns:
        Tuple of (resolved_workers, resolved_prefetch_depth).

    Raises:
        typer.Exit: With code 2 if --sequential and --max-workers > 1 conflict.
    """
    if sequential and max_workers not in (None, 1):
        console.print("[red]Error: --sequential cannot be combined with --max-workers > 1[/red]")
        raise typer.Exit(code=2)
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
                "[bold]`--prefetch-depth INTEGER`[/bold] — Tune queue-ahead depth per worker (`0` disables prefetch).",
                "[bold]`--no-prefetch`[/bold] — Backward-compatible alias for `--prefetch-depth 0`.",
                "[bold]`--no-vision`, `--text-only`[/bold] — Disable vision model processing for images.",
                "[bold]`--transcribe-audio`[/bold] — Enable transcription-based audio categorization.",
                "[bold]`--max-transcribe-seconds FLOAT`[/bold] — Skip transcription for long audio files (`0` disables cap).",
            ]
        )
    )
    console.print(
        "\n[bold]Example:[/bold] [cyan]fo organize INPUT_DIR OUTPUT_DIR "
        "--max-workers 2 --prefetch-depth 1[/cyan]"
    )


def _advanced_help_callback(value: bool) -> None:
    """Eager callback for ``--advanced-help``."""
    if not value:
        return
    _print_organize_advanced_help()
    raise typer.Exit()


def organize(
    input_dir: Annotated[Path, typer.Argument(help="Directory containing files to organize.")],
    output_dir: Annotated[Path, typer.Argument(help="Destination directory for organized files.")],
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Preview without moving files.")
    ] = False,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output.")] = False,
    advanced_help: Annotated[
        bool,
        typer.Option(
            "--advanced-help",
            callback=_advanced_help_callback,
            is_eager=True,
            help="Show advanced tuning options and exit.",
        ),
    ] = False,
    max_workers: Annotated[
        int | None,
        typer.Option(
            "--max-workers",
            min=1,
            help="Maximum number of parallel workers for file processing.",
            hidden=True,
        ),
    ] = None,
    sequential: Annotated[
        bool,
        typer.Option(
            "--sequential", help="Force single-worker sequential processing.", hidden=True
        ),
    ] = False,
    no_vision: Annotated[
        bool,
        typer.Option(
            "--no-vision",
            "--text-only",
            help="Disable vision model usage and organize images by extension fallback.",
            hidden=True,
        ),
    ] = False,
    prefetch_depth: Annotated[
        int,
        typer.Option(
            "--prefetch-depth",
            min=0,
            help=(
                "Task scheduling prefetch depth per worker (0 disables queue-ahead and "
                "uses strictly sequential submission)."
            ),
            hidden=True,
        ),
    ] = 2,
    no_prefetch: Annotated[
        bool,
        typer.Option(
            "--no-prefetch",
            help="Backward-compatible alias for --prefetch-depth 0.",
            hidden=True,
        ),
    ] = False,
    transcribe_audio: Annotated[
        bool,
        typer.Option(
            "--transcribe-audio",
            help=(
                "Transcribe audio files (requires the [media] extra) and use the "
                "transcript for content-aware categorization. Off by default — "
                "transcription is the expensive operation in the audio pipeline."
            ),
            hidden=True,
        ),
    ] = False,
    max_transcribe_seconds: Annotated[
        float,
        typer.Option(
            "--max-transcribe-seconds",
            min=0.0,
            help=(
                "Skip transcription for audio files longer than this (seconds). "
                "Default: 600 (10 min). Set to 0 to disable the cap entirely."
            ),
            hidden=True,
        ),
    ] = 600.0,
) -> None:
    """Organize files in a directory using AI models."""
    _ = advanced_help
    # First-run setup gate now lives in `cli.main.main_callback` and runs
    # for every non-allowlisted command. The previous inline call here
    # is removed (Step 3); leaving both would double-print the panel.

    # A.cli: resolve + validate both path args before any filesystem work.
    # Input must exist and be a dir; output may not exist yet (the
    # organizer creates it), but when it does exist it must be a dir.
    input_dir = resolve_cli_path(input_dir, must_exist=True, must_be_dir=True, reject_symlink=True)
    output_dir = resolve_cli_path(output_dir, must_exist=False, must_be_dir=True)
    validate_pair(input_dir, output_dir)

    console.print(f"[bold]Organizing[/bold] {input_dir} -> {output_dir}")
    if dry_run or _get_state().dry_run:
        console.print("[yellow]Dry run mode — no files will be moved.[/yellow]")
    resolved_workers, resolved_prefetch_depth = _resolve_parallel_settings(
        sequential, max_workers, prefetch_depth, no_prefetch
    )

    try:
        from file_organizer.core.organizer import FileOrganizer

        organizer = FileOrganizer(
            dry_run=dry_run or _get_state().dry_run,
            parallel_workers=resolved_workers,
            prefetch_depth=resolved_prefetch_depth,
            enable_vision=not no_vision,
            no_prefetch=no_prefetch,
            transcribe_audio=transcribe_audio,
            # `--max-transcribe-seconds 0` is the documented "disable the cap"
            # value; convert to None for the organizer (None means uncapped).
            max_transcribe_seconds=max_transcribe_seconds if max_transcribe_seconds > 0 else None,
        )
        result = organizer.organize(input_dir, output_dir)
        console.print(
            f"[green]Done:[/green] {result.processed_files} processed, "
            f"{result.skipped_files} skipped, {result.failed_files} failed"
        )
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        # Step 3: surface the full Rich traceback when --debug is set so
        # beta testers can attach actionable repro info to bug reports.
        # Without --debug, only the red one-liner shows (current behavior).
        if _get_state().debug:
            console.print_exception(show_locals=False)
        raise typer.Exit(code=1) from exc


def preview(
    input_dir: Annotated[Path, typer.Argument(help="Directory to preview.")],
    max_workers: Annotated[
        int | None,
        typer.Option(
            "--max-workers",
            min=1,
            help="Maximum number of parallel workers for file processing.",
        ),
    ] = None,
    sequential: Annotated[
        bool,
        typer.Option("--sequential", help="Force single-worker sequential processing."),
    ] = False,
    no_vision: Annotated[
        bool,
        typer.Option(
            "--no-vision",
            "--text-only",
            help="Disable vision model usage and organize images by extension fallback.",
        ),
    ] = False,
    prefetch_depth: Annotated[
        int,
        typer.Option(
            "--prefetch-depth",
            min=0,
            help=(
                "Task scheduling prefetch depth per worker (0 disables queue-ahead and "
                "uses strictly sequential submission)."
            ),
        ),
    ] = 2,
    no_prefetch: Annotated[
        bool,
        typer.Option("--no-prefetch", help="Backward-compatible alias for --prefetch-depth 0."),
    ] = False,
    transcribe_audio: Annotated[
        bool,
        typer.Option(
            "--transcribe-audio",
            help=(
                "Transcribe audio files (requires the [media] extra) and use the "
                "transcript for content-aware categorization. Off by default."
            ),
        ),
    ] = False,
    max_transcribe_seconds: Annotated[
        float,
        typer.Option(
            "--max-transcribe-seconds",
            min=0.0,
            help=(
                "Skip transcription for audio files longer than this (seconds). "
                "Default: 600 (10 min). Set to 0 to disable the cap entirely."
            ),
        ),
    ] = 600.0,
) -> None:
    """Preview how files would be organized (dry-run)."""
    # Setup gate moved to `cli.main.main_callback` (Step 3).

    # A.cli: single-path validation — preview never writes, so no
    # output-dir pair check needed.
    input_dir = resolve_cli_path(input_dir, must_exist=True, must_be_dir=True, reject_symlink=True)

    console.print(f"[bold]Previewing[/bold] {input_dir}")
    resolved_workers, resolved_prefetch_depth = _resolve_parallel_settings(
        sequential, max_workers, prefetch_depth, no_prefetch
    )

    try:
        from file_organizer.core.organizer import FileOrganizer

        organizer = FileOrganizer(
            dry_run=True,
            parallel_workers=resolved_workers,
            prefetch_depth=resolved_prefetch_depth,
            enable_vision=not no_vision,
            no_prefetch=no_prefetch,
            transcribe_audio=transcribe_audio,
            max_transcribe_seconds=max_transcribe_seconds if max_transcribe_seconds > 0 else None,
        )
        result = organizer.organize(input_dir, input_dir)
        console.print(f"[green]Preview:[/green] {result.total_files} files would be organized")
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        if _get_state().debug:
            console.print_exception(show_locals=False)
        raise typer.Exit(code=1) from exc
