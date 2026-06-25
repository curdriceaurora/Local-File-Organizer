# pyre-ignore-all-errors
"""Output backends for the ``dedupe`` CLI sub-app.

Issue #157 / Epic D / D4 Renderer extraction.

Three implementations, selected via ``--format``:

- :class:`RichRenderer` (default): Rich tables + colored output for terminals.
- :class:`JsonRenderer`: buffered single-document JSON envelope, flushed in
  :meth:`end`. Suitable for ``dedupe scan --format=json | jq``.
- :class:`PlainRenderer`: line-oriented, no colors, no tables. Suitable for
  ``awk`` / ``cut`` pipelines.

All three implement :class:`Renderer` (a runtime-checkable Protocol).
``--format=rich`` produces output identical to the pre-D4 behavior of
``dedupe_v2.py`` (modulo the flag plumbing).
"""

from __future__ import annotations

import contextlib
import json
import sys
from contextlib import AbstractContextManager
from pathlib import Path
from typing import IO, Any, Literal, Protocol, runtime_checkable

from rich.console import Console
from rich.table import Table

from file_organizer.services.deduplication.index import DuplicateGroup

MessageLevel = Literal["info", "success", "warning", "error"]
ResolveAction = Literal["would_remove", "removed", "error"]

_VALID_FORMATS = ("rich", "json", "plain")
_VALID_LEVELS: tuple[MessageLevel, ...] = ("info", "success", "warning", "error")

# Pyre wants AbstractContextManager parameterized with both type vars
# (yield type + __exit__ return type). We use ``Any`` for both because Rich's
# ``Status`` has ``__enter__ -> Status`` while ``contextlib.nullcontext()``
# has ``__enter__ -> None`` — both are valid implementations of ``status()``,
# so widening the protocol's return type accepts both.
_StatusCtx = AbstractContextManager[Any, Any]


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class Renderer(Protocol):
    """Output backend protocol for the dedupe CLI.

    Lifecycle: :meth:`begin` (once, with the command name) → arbitrary
    ``render_*`` calls → :meth:`end` (once). For ``RichRenderer`` and
    ``PlainRenderer`` the lifecycle methods are no-ops; for
    ``JsonRenderer`` they bracket the buffered envelope.
    """

    def begin(self, command: str) -> None:
        """Mark the start of a command run."""

    def end(self) -> None:
        """Mark the end of a command run; flush buffered output if any."""

    def status(self, message: str) -> _StatusCtx:
        """Return a context manager that displays ``message`` while it's open."""

    def render_groups_header(self, count: int) -> None:
        """Render the ``Found N duplicate groups`` header (or skip silently)."""

    def render_groups(self, groups: dict[str, DuplicateGroup]) -> None:
        """Render a duplicate-group listing keyed by hash."""

    def render_resolve_action(
        self,
        action: ResolveAction,
        path: Path,
        error: str | None = None,
    ) -> None:
        """Render a single per-file resolve action (would_remove/removed/error)."""

    def render_resolve_summary(self, removed_count: int, dry_run: bool) -> None:
        """Render the resolve-command summary line(s)."""

    def render_report(
        self,
        stats: dict[str, Any],
        groups: dict[str, DuplicateGroup],
        total_wasted: int,
    ) -> None:
        """Render the report-command summary table / object / lines."""

    def render_message(self, level: MessageLevel, message: str) -> None:
        """Render a free-form info/success/warning/error message."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_size(size: int) -> str:
    """Format file size in human-readable units (binary, 1024-step)."""
    value: float = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def _validate_level(level: str) -> MessageLevel:
    """Reject unknown message levels.

    Per anti-pattern T10: predicates and dispatchers must reject inputs that
    look valid but aren't, with a message naming the accepted alternatives.
    """
    if level not in _VALID_LEVELS:
        raise ValueError(
            f"Unknown message level {level!r}; expected one of: " + ", ".join(_VALID_LEVELS)
        )
    # mypy does not narrow ``str`` to ``MessageLevel`` from a runtime
    # ``in tuple[Literal, ...]`` check, so suppress the return-value error.
    return level  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# RichRenderer — visible terminal output (default)
# ---------------------------------------------------------------------------


_LEVEL_RICH_STYLE: dict[MessageLevel, str] = {
    "info": "dim",
    "success": "green",
    "warning": "yellow",
    "error": "red",
}


class RichRenderer:
    """Rich-console output. Tables, colors, status spinners."""

    def __init__(self, console: Console | None = None) -> None:
        """Initialize with an optional pre-built ``Console`` (else default)."""
        self._console = console if console is not None else Console()

    def begin(self, command: str) -> None:
        """No-op: Rich output is unbuffered."""
        del command

    def end(self) -> None:
        """No-op: Rich output is unbuffered."""
        return

    def status(self, message: str) -> _StatusCtx:
        """Return Rich's :meth:`Console.status` spinner as a context manager."""
        return self._console.status(message)  # type: ignore[no-any-return]

    def render_groups_header(self, count: int) -> None:
        """Emit ``Found N duplicate groups`` as a Rich-styled line."""
        self._console.print(f"Found [bold]{count}[/bold] duplicate groups.\n")

    def render_groups(self, groups: dict[str, DuplicateGroup]) -> None:
        """Emit one Rich Table per duplicate group with file rows."""
        for hash_val, group in groups.items():
            table = Table(title=f"Group {hash_val[:12]}…", show_lines=True)
            table.add_column("#", style="dim", width=3)
            table.add_column("Path")
            table.add_column("Size", justify="right")
            table.add_column("Modified")
            for idx, fmeta in enumerate(group.files, 1):
                table.add_row(
                    str(idx),
                    str(fmeta.path),
                    _format_size(fmeta.size),
                    fmeta.modified_time.strftime("%Y-%m-%d %H:%M"),
                )
            self._console.print(table)
            self._console.print(f"  [dim]Wasted space: {_format_size(group.wasted_space)}[/dim]\n")

    def render_resolve_action(
        self,
        action: ResolveAction,
        path: Path,
        error: str | None = None,
    ) -> None:
        """Emit a single resolve action with Rich color coding."""
        if action == "would_remove":
            self._console.print(f"  [dim]Would remove:[/dim] {path}")
        elif action == "removed":
            self._console.print(f"  [red]Removed:[/red] {path}")
        elif action == "error":
            self._console.print(f"  [red]Error removing {path}: {error}[/red]")
        else:
            raise ValueError(
                f"Unknown resolve action {action!r}; expected one of: would_remove, removed, error"
            )

    def render_resolve_summary(self, removed_count: int, dry_run: bool) -> None:
        """Emit the dry-run or actual-removed summary line."""
        if dry_run:
            self._console.print("\n[yellow]Dry run — no files were removed.[/yellow]")
        else:
            self._console.print(f"\n[green]Removed {removed_count} duplicate files.[/green]")

    def render_report(
        self,
        stats: dict[str, Any],
        groups: dict[str, DuplicateGroup],
        total_wasted: int,
    ) -> None:
        """Emit the report Rich table with aggregate metrics."""
        table = Table(title="Duplicate Report")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")
        table.add_row("Duplicate groups", str(len(groups)))
        table.add_row("Total files scanned", str(stats.get("total_files", "?")))
        table.add_row("Total duplicate files", str(stats.get("duplicate_files", "?")))
        table.add_row("Wasted space", _format_size(total_wasted))
        self._console.print(table)

    def render_message(self, level: MessageLevel, message: str) -> None:
        """Emit a free-form message with the level's Rich style."""
        validated = _validate_level(level)
        style = _LEVEL_RICH_STYLE[validated]
        self._console.print(f"[{style}]{message}[/{style}]")


# ---------------------------------------------------------------------------
# JsonRenderer — buffered single-document envelope
# ---------------------------------------------------------------------------


class JsonRenderer:
    """Buffer all calls; emit one JSON document on :meth:`end`.

    Stdout receives only the JSON envelope. Per spec §2.1, banner / warnings
    / errors go to stderr as plain lines so ``--format=json | jq`` works.
    """

    def __init__(
        self,
        stream: IO[str] | None = None,
        stderr: IO[str] | None = None,
    ) -> None:
        """Initialize with optional stdout / stderr streams (defaults to sys)."""
        self._stream: IO[str] = stream if stream is not None else sys.stdout
        self._stderr: IO[str] = stderr if stderr is not None else sys.stderr
        self._command: str | None = None
        self._groups_payload: list[dict[str, Any]] = []
        self._actions: list[dict[str, Any]] = []
        self._summary: dict[str, Any] = {}
        self._began: bool = False

    def begin(self, command: str) -> None:
        """Open a new envelope tagged with ``command``."""
        self._command = command
        self._began = True

    def end(self) -> None:
        """Flush the envelope to stdout. No-op if :meth:`begin` wasn't called.

        Emits a stable v1 shape: ``groups`` / ``actions`` / ``summary``
        are always present (possibly empty) so consumers can rely on
        ``jq '.groups[]'`` / ``jq '.summary'`` not erroring on
        empty-result runs.
        """
        if not self._began:
            return
        envelope: dict[str, Any] = {
            "version": 1,
            "command": self._command,
            "groups": self._groups_payload,
            "actions": self._actions,
            "summary": self._summary,
        }
        json.dump(envelope, self._stream)
        # Reset for potential reuse.
        self._began = False
        self._groups_payload = []
        self._actions = []
        self._summary = {}
        self._command = None

    def status(self, message: str) -> _StatusCtx:
        """Status spinners are visual; return a no-op context."""
        del message
        return contextlib.nullcontext()

    def render_groups_header(self, count: int) -> None:
        """No-op: group count is implicit in the envelope's ``groups`` array."""
        del count

    def render_groups(self, groups: dict[str, DuplicateGroup]) -> None:
        """Append each group's serialized payload to the envelope."""
        for hash_val, group in groups.items():
            self._groups_payload.append(
                {
                    "hash": hash_val,
                    "count": group.count,
                    "total_size": group.total_size,
                    "wasted_space": group.wasted_space,
                    "files": [str(f.path) for f in group.files],
                }
            )

    def render_resolve_action(
        self,
        action: ResolveAction,
        path: Path,
        error: str | None = None,
    ) -> None:
        """Append a resolve-action entry to the envelope's ``actions`` array."""
        entry: dict[str, Any] = {"action": action, "path": str(path)}
        if error is not None:
            entry["error"] = error
        self._actions.append(entry)

    def render_resolve_summary(self, removed_count: int, dry_run: bool) -> None:
        """Set the envelope's ``summary`` for the resolve command."""
        self._summary = {"removed_count": removed_count, "dry_run": dry_run}

    def render_report(
        self,
        stats: dict[str, Any],
        groups: dict[str, DuplicateGroup],
        total_wasted: int,
    ) -> None:
        """Set the envelope's ``summary`` for the report command."""
        self._summary = {
            "total_files": stats.get("total_files"),
            "duplicate_files": stats.get("duplicate_files"),
            "duplicate_groups": len(groups),
            "total_wasted": total_wasted,
        }

    def render_message(self, level: MessageLevel, message: str) -> None:
        """Write the message to stderr (envelope stays clean for ``jq``)."""
        validated = _validate_level(level)
        self._stderr.write(f"{validated}: {message}\n")


# ---------------------------------------------------------------------------
# PlainRenderer — line-oriented, no colors
# ---------------------------------------------------------------------------


class PlainRenderer:
    """Line-oriented, no colors, no tables. Pipe-friendly."""

    def __init__(self, stream: IO[str] | None = None) -> None:
        """Initialize with an optional output stream (defaults to sys.stdout)."""
        self._stream: IO[str] = stream if stream is not None else sys.stdout

    def _write(self, text: str) -> None:
        """Write text to the stream, ensuring a trailing newline."""
        self._stream.write(text)
        if not text.endswith("\n"):
            self._stream.write("\n")

    def begin(self, command: str) -> None:
        """No-op: plain output is unbuffered."""
        del command

    def end(self) -> None:
        """No-op: plain output is unbuffered."""
        return

    def status(self, message: str) -> _StatusCtx:
        """No-op context: plain output has no spinner."""
        del message
        return contextlib.nullcontext()

    def render_groups_header(self, count: int) -> None:
        """Emit ``Found N duplicate groups.`` as a plain line."""
        self._write(f"Found {count} duplicate groups.")

    def render_groups(self, groups: dict[str, DuplicateGroup]) -> None:
        """Emit hash-prefixed groups with TAB-indented file/size lines."""
        for hash_val, group in groups.items():
            self._write(f"{hash_val}:")
            for fmeta in group.files:
                # TAB indent + path + size; awk-friendly.
                self._write(f"\t{fmeta.path}\t{fmeta.size}")

    def render_resolve_action(
        self,
        action: ResolveAction,
        path: Path,
        error: str | None = None,
    ) -> None:
        """Emit a resolve action as ``ACTION: path[: error]``.

        Validates ``action`` against the ``ResolveAction`` literal set so
        unknown values raise instead of silently emitting garbage. When
        ``action == "error"`` and no message was supplied, emits a stable
        ``"<unknown error>"`` placeholder rather than the literal string
        ``"None"``.
        """
        if action == "error":
            self._write(f"error: {path}: {error if error is not None else '<unknown error>'}")
        elif action in ("removed", "would_remove"):
            self._write(f"{action}: {path}")
        else:
            raise ValueError(
                f"Unknown resolve action {action!r}; expected one of: would_remove, removed, error"
            )

    def render_resolve_summary(self, removed_count: int, dry_run: bool) -> None:
        """Emit summary as ``key: value`` lines."""
        self._write(f"removed_count: {removed_count}")
        self._write(f"dry_run: {str(dry_run).lower()}")

    def render_report(
        self,
        stats: dict[str, Any],
        groups: dict[str, DuplicateGroup],
        total_wasted: int,
    ) -> None:
        """Emit report metrics as ``key: value`` lines."""
        self._write(f"total_files: {stats.get('total_files', 0)}")
        self._write(f"duplicate_files: {stats.get('duplicate_files', 0)}")
        self._write(f"duplicate_groups: {len(groups)}")
        self._write(f"total_wasted: {total_wasted}")

    def render_message(self, level: MessageLevel, message: str) -> None:
        """Emit a level-prefixed message as a plain line."""
        validated = _validate_level(level)
        self._write(f"{validated}: {message}")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def make_renderer(format: str) -> Renderer:
    """Construct a :class:`Renderer` for the given format string.

    Accepts ``rich``, ``json``, or ``plain`` (case-insensitive). Anything else
    raises :class:`ValueError`. The factory does not bind a console / stream;
    each renderer uses its own default (terminal, ``sys.stdout``).
    """
    normalized = format.lower()
    if normalized == "rich":
        return RichRenderer()
    if normalized == "json":
        return JsonRenderer()
    if normalized == "plain":
        return PlainRenderer()
    raise ValueError(f"Unknown format {format!r}; expected one of: " + ", ".join(_VALID_FORMATS))


__all__ = [
    "JsonRenderer",
    "MessageLevel",
    "PlainRenderer",
    "Renderer",
    "ResolveAction",
    "RichRenderer",
    "make_renderer",
]
