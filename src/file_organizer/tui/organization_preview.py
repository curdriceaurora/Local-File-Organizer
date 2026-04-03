# pyre-ignore-all-errors
"""TUI live organization preview view.

Shows a before/after panel of how files would be organized,
along with an organization summary with file counts and status.
"""

from __future__ import annotations

import logging
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from file_organizer.tui.settings_view import load_parallel_runtime_settings

logger = logging.getLogger(__name__)


class BeforeAfterPanel(Static):
    """Two-column display: current path -> proposed destination.

    Built from ``OrganizationResult.organized_structure`` which maps
    folder names to lists of filenames.
    """

    DEFAULT_CSS = """
    BeforeAfterPanel {
        height: auto;
        padding: 1 2;
        overflow-y: auto;
    }
    """

    def set_structure(
        self,
        organized_structure: dict[str, list[str]],
        input_dir: str = "",
    ) -> None:
        """Render the before/after mapping.

        Args:
            organized_structure: Mapping of target folder to file lists.
            input_dir: Original input directory for display.
        """
        if not organized_structure:
            self.update("[dim]No files to organize.[/dim]")
            return

        lines: list[str] = ["[b]Before -> After[/b]\n"]
        for folder, files in sorted(organized_structure.items()):
            lines.append(f"[bold cyan]{folder}/[/bold cyan]")
            for fname in files[:20]:
                source = f"{input_dir}/{fname}" if input_dir else fname
                lines.append(f"  {source}  [dim]->[/dim]  {folder}/{fname}")
            if len(files) > 20:
                lines.append(f"  [dim]... and {len(files) - 20} more[/dim]")
            lines.append("")

        self.update("\n".join(lines))


class OrganizationSummary(Static):
    """Summary panel showing total files, folders, and status counts."""

    DEFAULT_CSS = """
    OrganizationSummary {
        height: auto;
        padding: 1 2;
        background: $surface;
        margin-top: 1;
    }
    """

    def set_result(
        self,
        total: int = 0,
        processed: int = 0,
        skipped: int = 0,
        failed: int = 0,
        folders: int = 0,
        errors: list[tuple[str, str]] | None = None,
    ) -> None:
        """Update the summary display.

        Args:
            total: Total files found.
            processed: Successfully processed files.
            skipped: Skipped files.
            failed: Failed files.
            folders: Number of target folders.
            errors: List of (filename, error_message) tuples.
        """
        lines = [
            "[b]Organization Summary[/b]\n",
            f"  Total files:   {total}",
            f"  Processed:     [green]{processed}[/green]",
            f"  Skipped:       [yellow]{skipped}[/yellow]",
            f"  Failed:        [red]{failed}[/red]",
            f"  Folders:       {folders}",
        ]

        if errors:
            lines.append("\n[b]Errors:[/b]")
            for fname, msg in errors[:5]:
                lines.append(f"  [red]{fname}[/red]: {msg}")
            if len(errors) > 5:
                lines.append(f"  [dim]... and {len(errors) - 5} more[/dim]")

        self.update("\n".join(lines))


class OrganizationPreviewView(Vertical):
    """Live organization preview mounted as ``#view`` for the Organized nav.

    Bindings:
        r - Refresh the preview
        Enter - Confirm organization (placeholder)
        Escape - Cancel / go back
    """

    DEFAULT_CSS = """
    OrganizationPreviewView {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_preview", "Refresh", show=True),
        Binding("enter", "confirm", "Confirm", show=True),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(
        self,
        input_dir: str | Path = ".",
        output_dir: str | Path = "organized_output",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the preview view for the given input and output directories."""
        super().__init__(name=name, id=id, classes=classes)
        self._input_dir = Path(input_dir)
        self._output_dir = Path(output_dir)

    def compose(self) -> ComposeResult:
        """Build the preview layout."""
        yield Static("[b]Organization Preview[/b] (dry-run)\n", id="org-header")
        yield BeforeAfterPanel("[dim]Loading preview...[/dim]")
        yield OrganizationSummary("[dim]Calculating...[/dim]")

    def on_mount(self) -> None:
        """Trigger the initial preview load."""
        self._load_preview()

    def action_refresh_preview(self) -> None:
        """Re-run the dry-run organization."""
        self.query_one(BeforeAfterPanel).update("[dim]Refreshing...[/dim]")
        self.query_one(OrganizationSummary).update("[dim]Calculating...[/dim]")
        self._load_preview()

    def action_confirm(self) -> None:
        """Placeholder for confirming organization."""
        self._set_status("Confirm not yet implemented.")

    def action_cancel(self) -> None:
        """Go back / cancel."""
        self._set_status("Ready")

    @work(thread=True)
    def _load_preview(self) -> None:
        """Run a dry-run organization in a worker thread."""
        try:
            from file_organizer.core.organizer import FileOrganizer

            runtime_settings = load_parallel_runtime_settings()
            organizer = FileOrganizer(
                dry_run=True,
                parallel_workers=runtime_settings.max_workers,
                prefetch_depth=runtime_settings.prefetch_depth,
            )
            result = organizer.organize(
                input_path=self._input_dir,
                output_path=self._output_dir,
            )

            panel = self.query_one(BeforeAfterPanel)
            summary = self.query_one(OrganizationSummary)

            self.app.call_from_thread(
                panel.set_structure,
                result.organized_structure,
                str(self._input_dir),
            )
            self.app.call_from_thread(
                summary.set_result,
                total=result.total_files,
                processed=result.processed_files,
                skipped=result.skipped_files,
                failed=result.failed_files,
                folders=len(result.organized_structure),
                errors=result.errors,
            )
            self.app.call_from_thread(self._set_status, "Preview loaded")

        except Exception as exc:
            self.app.call_from_thread(
                self.query_one(BeforeAfterPanel).update,
                f"[red]Models unavailable:[/red] {exc}\n\n"
                "[dim]Ensure Ollama is running with required models.[/dim]",
            )
            self.app.call_from_thread(
                self.query_one(OrganizationSummary).update,
                "[dim]No data available.[/dim]",
            )

    def _set_status(self, message: str) -> None:
        """Update the app status bar if available."""
        try:
            from file_organizer.tui.app import StatusBar

            self.app.query_one(StatusBar).set_status(message)
        except Exception:
            logger.debug("OrganizationPreviewView status bar unavailable", exc_info=True)
