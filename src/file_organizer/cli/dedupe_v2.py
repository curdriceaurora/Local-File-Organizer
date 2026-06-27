# pyre-ignore-all-errors
"""Modern Typer sub-app for duplicate file detection and resolution.

Replaces the legacy argparse ``dedupe`` command with a sub-app
providing ``scan``, ``resolve``, and ``report`` commands.

Output format is selected via ``--format={rich|json|plain}`` and routed
through the :class:`cli.dedupe_renderer.Renderer` Protocol (issue #157,
Epic D / D4).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any, cast

import typer
from rich.console import Console

from file_organizer.cli.dedupe_renderer import Renderer, make_renderer
from file_organizer.cli.interactive import confirm_action
from file_organizer.cli.path_validation import resolve_cli_path

# Module-level Console retained only for the user-confirmation prompt
# (``confirm_action``), which is interactive and not routed through the
# Renderer. All command output goes through the Renderer.
console = Console()

dedupe_app = typer.Typer(
    name="dedupe",
    help="Find and manage duplicate files.",
    no_args_is_help=True,
)

_FORMAT_HELP = "Output format: rich (default), json, plain"


def _validate_format(value: str) -> str:
    """Typer callback: convert ``ValueError`` from :func:`make_renderer` into ``BadParameter``.

    Without this the user sees an unhandled ``ValueError`` traceback for
    ``--format=xml`` instead of a Typer/Click usage error with the
    accepted alternatives listed.
    """
    try:
        make_renderer(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    return value.lower()


def _get_detector() -> Any:
    """Lazily import and return a fresh ``DuplicateDetector``."""
    from file_organizer.services.deduplication.detector import DuplicateDetector

    return DuplicateDetector()


def _build_scan_options(
    directory: Path,
    algorithm: str,
    recursive: bool,
    min_size: int,
    max_size: int | None,
    include: str | None,
    exclude: str | None,
    include_hidden: bool = False,
) -> Any:
    """Build ``ScanOptions`` from CLI flags."""
    del directory  # signature retained for future per-directory options
    from file_organizer.services.deduplication.detector import ScanOptions
    from file_organizer.services.deduplication.hasher import HashAlgorithm

    include_patterns = include.split(",") if include else None
    exclude_patterns = exclude.split(",") if exclude else None
    return ScanOptions(
        algorithm=cast("HashAlgorithm", algorithm),
        recursive=recursive,
        include_hidden=include_hidden,
        min_file_size=min_size,
        max_file_size=max_size,
        file_patterns=include_patterns,
        exclude_patterns=exclude_patterns,
    )


# #170: shown to the user when they pass ``--include-hidden`` to
# ``fo dedupe resolve``. The resolve path can DELETE files; opting into
# hidden-file inclusion means dotfiles like ``.env`` / ``.ssh/id_rsa`` enter
# the hash index, so a backup-directory duplicate could cascade into a
# credential deletion. The prompt forces a conscious second-click.
_HIDDEN_RESOLVE_WARNING = (
    "You are about to [bold]dedupe resolve[/bold] a scan that includes hidden "
    "files ([yellow].env[/yellow], [yellow].ssh/*[/yellow], "
    "[yellow].config/*[/yellow], etc.). These will be hashed and may be "
    "deleted as duplicates — including potentially sensitive credentials. "
    "Continue?"
)


def _hidden_files_will_be_scanned(directory: Path, *, include_hidden: bool) -> bool:
    """Return True when the scan is likely to touch hidden files.

    The `resolve` confirmation gate must fire not only when ``--include-hidden``
    is set, but also when the scan *root itself* is a hidden directory
    (`fo dedupe resolve ~/.ssh --strategy oldest`). ``safe_walk``'s hidden
    filter is relative to `root`: a root of `~/.ssh` means `id_rsa` has no
    hidden component *under* the root, and would be scanned even with
    `include_hidden=False`. Either condition is enough to warrant the prompt.
    """
    if include_hidden:
        return True
    resolved = directory.resolve()
    return any(part.startswith(".") and part not in (".", "..") for part in resolved.parts)


# -----------------------------------------------------------------------
# Commands
# -----------------------------------------------------------------------


@dedupe_app.command()
def scan(
    directory: Annotated[Path, typer.Argument(help="Directory to scan for duplicates.")],
    algorithm: Annotated[str, typer.Option(help="Hash algorithm (md5, sha256).")] = "sha256",
    recursive: Annotated[bool, typer.Option(help="Scan subdirectories.")] = True,
    min_size: Annotated[int, typer.Option(help="Minimum file size in bytes.")] = 0,
    max_size: Annotated[int | None, typer.Option(help="Maximum file size in bytes.")] = None,
    include: Annotated[
        str | None, typer.Option(help="Comma-separated glob include patterns.")
    ] = None,
    exclude: Annotated[
        str | None, typer.Option(help="Comma-separated glob exclude patterns.")
    ] = None,
    include_hidden: Annotated[
        bool,
        typer.Option(
            "--include-hidden",
            help=(
                "Include dotfiles and files under hidden directories "
                "(.env, .ssh, .config). Off by default — hidden paths often "
                "contain credentials."
            ),
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help=_FORMAT_HELP,
            case_sensitive=False,
            callback=_validate_format,
        ),
    ] = "rich",
) -> None:
    """Scan a directory and display duplicate file groups."""
    directory = resolve_cli_path(directory, must_exist=True, must_be_dir=True)
    renderer: Renderer = make_renderer(output_format)
    renderer.begin("scan")

    detector = _get_detector()
    options = _build_scan_options(
        directory,
        algorithm,
        recursive,
        min_size,
        max_size,
        include,
        exclude,
        include_hidden=include_hidden,
    )

    with renderer.status("Scanning for duplicates…"):
        detector.scan_directory(directory, options)

    groups = detector.get_duplicate_groups()
    if not groups:
        renderer.render_message("success", "No duplicates found.")
        renderer.end()
        raise typer.Exit()

    renderer.render_groups_header(len(groups))
    renderer.render_groups(groups)
    renderer.end()


@dedupe_app.command()
def resolve(
    directory: Annotated[Path, typer.Argument(help="Directory to scan for duplicates.")],
    strategy: Annotated[
        str,
        typer.Option(help="Resolution strategy (manual, oldest, newest, largest, smallest)."),
    ] = "manual",
    algorithm: Annotated[str, typer.Option(help="Hash algorithm.")] = "sha256",
    recursive: Annotated[bool, typer.Option(help="Scan subdirectories.")] = True,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without deleting.")] = False,
    min_size: Annotated[int, typer.Option(help="Minimum file size in bytes.")] = 0,
    max_size: Annotated[int | None, typer.Option(help="Maximum file size in bytes.")] = None,
    include: Annotated[str | None, typer.Option(help="Comma-separated include patterns.")] = None,
    exclude: Annotated[str | None, typer.Option(help="Comma-separated exclude patterns.")] = None,
    include_hidden: Annotated[
        bool,
        typer.Option(
            "--include-hidden",
            help=(
                "Include dotfiles / hidden directories. Off by default; when "
                "on, a confirmation prompt appears before any deletion."
            ),
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help=_FORMAT_HELP,
            case_sensitive=False,
            callback=_validate_format,
        ),
    ] = "rich",
) -> None:
    """Scan and resolve duplicates using a strategy."""
    directory = resolve_cli_path(directory, must_exist=True, must_be_dir=True)
    renderer: Renderer = make_renderer(output_format)
    # #170: any `resolve` that will actually traverse hidden files (either via
    # ``--include-hidden`` OR because the scan root itself is a hidden dir
    # like ``~/.ssh``) requires an explicit credential-risk confirmation.
    # ``--yes`` / ``--no-interactive`` still honour their usual semantics via
    # ``confirm_action``. User-cancellation exits with code 1 so shell scripts
    # and ``&&`` chains can distinguish "aborted" from "no duplicates found".
    #
    # Confirmation runs BEFORE ``renderer.begin()`` so an aborted
    # ``--format=json`` invocation prints only the plain "Aborted."
    # message to stderr and emits no envelope at all (consumers piping
    # to ``jq`` won't get a stub envelope claiming a command was run).
    if _hidden_files_will_be_scanned(
        directory, include_hidden=include_hidden
    ) and not confirm_action(_HIDDEN_RESOLVE_WARNING, default=False):
        renderer.render_message("warning", "Aborted.")
        raise typer.Exit(code=1)
    renderer.begin("resolve")
    detector = _get_detector()
    options = _build_scan_options(
        directory,
        algorithm,
        recursive,
        min_size,
        max_size,
        include,
        exclude,
        include_hidden=include_hidden,
    )

    with renderer.status("Scanning for duplicates…"):
        detector.scan_directory(directory, options)

    groups = detector.get_duplicate_groups()
    if not groups:
        renderer.render_message("success", "No duplicates found.")
        renderer.end()
        raise typer.Exit()

    removed = 0
    for hash_val, group in groups.items():
        files = sorted(group.files, key=lambda f: f.modified_time)
        if strategy == "oldest":
            keep = files[-1]
        elif strategy == "newest":
            keep = files[0]
        elif strategy == "largest":
            keep = max(files, key=lambda f: f.size)
        elif strategy == "smallest":
            keep = min(files, key=lambda f: f.size)
        else:
            # Manual: show the group, skip automatic resolution
            renderer.render_groups({hash_val: group})
            renderer.render_message("warning", "Manual mode — skipping automatic resolution.")
            continue

        to_remove = [f for f in files if f.path != keep.path]
        for fmeta in to_remove:
            if dry_run:
                renderer.render_resolve_action("would_remove", fmeta.path)
            else:
                try:
                    fmeta.path.unlink()
                except OSError as exc:
                    renderer.render_resolve_action("error", fmeta.path, error=str(exc))
                else:
                    renderer.render_resolve_action("removed", fmeta.path)
                    removed += 1

    renderer.render_resolve_summary(removed_count=removed, dry_run=dry_run)
    renderer.end()


@dedupe_app.command()
def report(
    directory: Annotated[Path, typer.Argument(help="Directory to scan.")],
    algorithm: Annotated[str, typer.Option(help="Hash algorithm.")] = "sha256",
    recursive: Annotated[bool, typer.Option(help="Scan subdirectories.")] = True,
    include_hidden: Annotated[
        bool,
        typer.Option(
            "--include-hidden",
            help="Include dotfiles and files under hidden directories in the report.",
        ),
    ] = False,
    output_format: Annotated[
        str,
        typer.Option(
            "--format",
            "-f",
            help=_FORMAT_HELP,
            case_sensitive=False,
            callback=_validate_format,
        ),
    ] = "rich",
) -> None:
    """Scan and display a summary report of duplicates."""
    directory = resolve_cli_path(directory, must_exist=True, must_be_dir=True)
    renderer: Renderer = make_renderer(output_format)
    renderer.begin("report")

    detector = _get_detector()
    from file_organizer.services.deduplication.detector import ScanOptions
    from file_organizer.services.deduplication.hasher import HashAlgorithm

    options = ScanOptions(
        algorithm=cast("HashAlgorithm", algorithm),
        recursive=recursive,
        include_hidden=include_hidden,
    )

    with renderer.status("Scanning…"):
        detector.scan_directory(directory, options)

    stats = detector.get_statistics()
    groups = detector.get_duplicate_groups()
    total_wasted = sum(g.wasted_space for g in groups.values())
    renderer.render_report(stats=stats, groups=groups, total_wasted=total_wasted)
    renderer.end()
