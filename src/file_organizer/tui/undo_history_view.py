"""TUI view for undo/redo operations and operation history.

Provides panels showing recent operations, undo/redo stacks,
and aggregate history statistics.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

if TYPE_CHECKING:
    from file_organizer.history.models import Operation


class OperationHistoryPanel(Static):
    """Table of recent file operations (move, rename, delete, etc.)."""

    DEFAULT_CSS = """
    OperationHistoryPanel {
        height: auto;
        padding: 1 2;
    }
    """

    def set_operations(self, ops: list[Operation]) -> None:
        """Render a table of operations.

        Args:
            ops: List of Operation dataclass instances.
        """
        if not ops:
            self.update("[b]Recent Operations[/b]\n\n  [dim]No operations recorded.[/dim]")
            return

        lines = [
            "[b]Recent Operations[/b]\n",
            f"  {'ID':<6} {'Type':<8} {'Status':<12} {'Time':<20} {'Source -> Dest'}",
            "  " + "-" * 78,
        ]
        for op in ops[:20]:
            op_id = str(op.id or "-")
            op_type = (
                str(op.operation_type.value)
                if hasattr(op.operation_type, "value")
                else str(op.operation_type)
            )
            status = str(op.status.value) if hasattr(op.status, "value") else str(op.status)
            timestamp = _format_timestamp(op.timestamp) if op.timestamp else "-"
            source = _truncate(str(op.source_path), 25)
            dest = _truncate(str(op.destination_path), 25) if op.destination_path else "-"
            lines.append(
                f"  {op_id:<6} {op_type:<8} {status:<12} {timestamp:<20} {source} -> {dest}"
            )

        self.update("\n".join(lines))


class UndoRedoStackPanel(Static):
    """Shows undo and redo stack sizes with top entries."""

    DEFAULT_CSS = """
    UndoRedoStackPanel {
        height: auto;
        padding: 1 2;
        margin-top: 1;
    }
    """

    def set_stacks(
        self,
        undo_stack: list[Operation],
        redo_stack: list[Operation],
    ) -> None:
        """Update undo/redo stack display.

        Args:
            undo_stack: List of undoable Operation instances.
            redo_stack: List of redoable Operation instances.
        """
        lines = [
            "[b]Undo / Redo Stacks[/b]\n",
            f"  Undo stack: [cyan]{len(undo_stack)}[/cyan] operations",
        ]

        if undo_stack:
            lines.append("  [dim]Top 5 undoable:[/dim]")
            for op in undo_stack[:5]:
                op_type = (
                    str(op.operation_type.value)
                    if hasattr(op.operation_type, "value")
                    else str(op.operation_type)
                )
                source = _truncate(str(op.source_path), 35)
                lines.append(f"    {op_type:<8} {source}")

        lines.append(f"\n  Redo stack: [cyan]{len(redo_stack)}[/cyan] operations")

        if redo_stack:
            lines.append("  [dim]Top 5 redoable:[/dim]")
            for op in redo_stack[:5]:
                op_type = (
                    str(op.operation_type.value)
                    if hasattr(op.operation_type, "value")
                    else str(op.operation_type)
                )
                source = _truncate(str(op.source_path), 35)
                lines.append(f"    {op_type:<8} {source}")

        self.update("\n".join(lines))


class HistoryStatsPanel(Static):
    """Aggregate statistics about the operation history."""

    DEFAULT_CSS = """
    HistoryStatsPanel {
        height: auto;
        padding: 1 2;
        margin-top: 1;
        background: $surface;
    }
    """

    def set_stats(self, stats: dict[str, object]) -> None:
        """Update history statistics display.

        Args:
            stats: Dict from HistoryViewer.get_statistics() containing
                total_operations, by_type, by_status, latest_operation,
                oldest_operation.
        """
        total = stats.get("total_operations", 0)
        by_type: dict[str, int] = stats.get("by_type", {})  # type: ignore[assignment]
        by_status: dict[str, int] = stats.get("by_status", {})  # type: ignore[assignment]

        lines = ["[b]History Statistics[/b]\n", f"  Total operations: [cyan]{total}[/cyan]\n"]

        if by_type:
            lines.append("  [dim]By type:[/dim]")
            for op_type, count in sorted(by_type.items()):
                lines.append(f"    {op_type:<14} {count:>5}")

        if by_status:
            lines.append("\n  [dim]By status:[/dim]")
            for status, count in sorted(by_status.items()):
                color = (
                    "green"
                    if status.lower() == "completed"
                    else "yellow"
                    if status.lower() == "pending"
                    else "red"
                )
                lines.append(f"    {status:<14} [{color}]{count:>5}[/{color}]")

        latest = stats.get("latest_operation")
        if latest is not None:
            ts = (
                _format_timestamp(latest.timestamp)
                if hasattr(latest, "timestamp") and latest.timestamp
                else "unknown"
            )
            lines.append(f"\n  Latest: {ts}")

        self.update("\n".join(lines))


class UndoHistoryView(Vertical):
    """Undo/redo and operation history view mounted as ``#view``.

    Bindings:
        r - Refresh history data
        u - Undo last operation
        y - Redo last operation
    """

    DEFAULT_CSS = """
    UndoHistoryView {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_history", "Refresh", show=True),
        Binding("u", "undo_last", "Undo", show=True),
        Binding("y", "redo_last", "Redo", show=True),
    ]

    def __init__(
        self,
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the undo history view with the given Textual widget parameters."""
        super().__init__(name=name, id=id, classes=classes)

    def compose(self) -> ComposeResult:
        """Build the undo/history layout."""
        yield Static("[b]Undo / Redo & Operation History[/b]\n", id="history-header")
        yield OperationHistoryPanel("[dim]Loading...[/dim]")
        yield UndoRedoStackPanel("[dim]Loading...[/dim]")
        yield HistoryStatsPanel("[dim]Loading...[/dim]")

    def on_mount(self) -> None:
        """Trigger the initial history load."""
        self._load_history()

    def action_refresh_history(self) -> None:
        """Reload history data."""
        for panel_type in (OperationHistoryPanel, UndoRedoStackPanel, HistoryStatsPanel):
            self.query_one(panel_type).update("[dim]Refreshing...[/dim]")
        self._load_history()

    def action_undo_last(self) -> None:
        """Undo the most recent operation."""
        self._run_undo()

    def action_redo_last(self) -> None:
        """Redo the most recently undone operation."""
        self._run_redo()

    @work(thread=True)
    def _load_history(self) -> None:
        """Load history data in a worker thread."""
        try:
            from file_organizer.history.tracker import OperationHistory
            from file_organizer.undo.undo_manager import UndoManager
            from file_organizer.undo.viewer import HistoryViewer

            history = OperationHistory()
            try:
                manager = UndoManager(history=history)
                viewer = HistoryViewer(history=history)

                recent = history.get_recent_operations(limit=50)
                undo_stack = manager.get_undo_stack()
                redo_stack = manager.get_redo_stack()
                stats = viewer.get_statistics()

                self.app.call_from_thread(
                    self.query_one(OperationHistoryPanel).set_operations,
                    recent,
                )
                self.app.call_from_thread(
                    self.query_one(UndoRedoStackPanel).set_stacks,
                    undo_stack,
                    redo_stack,
                )
                self.app.call_from_thread(
                    self.query_one(HistoryStatsPanel).set_stats,
                    stats,
                )
                self.app.call_from_thread(self._set_status, "History loaded")
            finally:
                history.close()

        except Exception as exc:
            msg = f"[red]History unavailable:[/red] {exc}"
            for panel_type in (OperationHistoryPanel, UndoRedoStackPanel, HistoryStatsPanel):
                self.app.call_from_thread(self.query_one(panel_type).update, msg)

    @work(thread=True)
    def _run_undo(self) -> None:
        """Execute undo in a worker thread, then reload."""
        try:
            from file_organizer.history.tracker import OperationHistory
            from file_organizer.undo.undo_manager import UndoManager

            history = OperationHistory()
            try:
                manager = UndoManager(history=history)
                success = manager.undo_last_operation()
                if success:
                    self.app.call_from_thread(self._set_status, "Undo successful")
                else:
                    self.app.call_from_thread(self._set_status, "Nothing to undo")
            finally:
                history.close()
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Undo failed: {exc}")

        # Reload history to reflect changes
        self.app.call_from_thread(self.action_refresh_history)

    @work(thread=True)
    def _run_redo(self) -> None:
        """Execute redo in a worker thread, then reload."""
        try:
            from file_organizer.history.tracker import OperationHistory
            from file_organizer.undo.undo_manager import UndoManager

            history = OperationHistory()
            try:
                manager = UndoManager(history=history)
                success = manager.redo_last_operation()
                if success:
                    self.app.call_from_thread(self._set_status, "Redo successful")
                else:
                    self.app.call_from_thread(self._set_status, "Nothing to redo")
            finally:
                history.close()
        except Exception as exc:
            self.app.call_from_thread(self._set_status, f"Redo failed: {exc}")

        # Reload history to reflect changes
        self.app.call_from_thread(self.action_refresh_history)

    def _set_status(self, message: str) -> None:
        """Update the app status bar if available."""
        try:
            from file_organizer.tui.app import StatusBar

            self.app.query_one(StatusBar).set_status(message)
        except Exception:
            pass


def _format_timestamp(ts: datetime | None) -> str:
    """Format a datetime for display.

    Args:
        ts: Datetime to format.

    Returns:
        Formatted string or '-'.
    """
    if ts is None:
        return "-"
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def _truncate(text: str, max_len: int) -> str:
    """Truncate text with ellipsis if too long.

    Args:
        text: Text to truncate.
        max_len: Maximum length.

    Returns:
        Truncated string.
    """
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"
