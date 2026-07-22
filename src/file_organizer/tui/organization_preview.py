# pyre-ignore-all-errors
"""TUI live organization preview view.

Shows a before/after panel of how files would be organized,
along with an organization summary with file counts and status.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from file_organizer.core.errors import DomainError, DomainErrorCode
from file_organizer.core.organization_service import OrganizationService
from file_organizer.core.organize_options import OrganizeOptions, OrganizeRequest
from file_organizer.core.plan import OrganizationPlan
from file_organizer.core.types import OrganizationResult
from file_organizer.tui.organization_adapter import TUIOrganizationAdapter
from file_organizer.tui.settings_view import load_parallel_runtime_settings
from file_organizer.tui.status import StatusMixin

if TYPE_CHECKING:
    from file_organizer.tui.workspace import TUIWorkspace


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


class OrganizationPreviewView(StatusMixin, Vertical):
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
        workspace: TUIWorkspace | None = None,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the preview view for the given input and output directories."""
        super().__init__(name=name, id=id, classes=classes)
        self._workspace = workspace
        self._input_dir = workspace.active_root if workspace is not None else Path(input_dir)
        self._output_dir = workspace.output_root if workspace is not None else Path(output_dir)
        self._is_applying = False
        self._current_plan = workspace.reviewed_plan if workspace is not None else None
        self._current_request: OrganizeRequest | None = None
        self._adapter = TUIOrganizationAdapter(workspace) if workspace is not None else None

    def compose(self) -> ComposeResult:
        """Build the preview layout."""
        yield Static("[b]Organization Preview[/b] (dry-run)\n", id="org-header")
        yield Static(self._options_summary(), id="org-options")
        yield BeforeAfterPanel("[dim]Loading preview...[/dim]")
        yield OrganizationSummary("[dim]Calculating...[/dim]")

    def on_mount(self) -> None:
        """Trigger the initial preview load."""
        self._load_preview()

    def action_refresh_preview(self) -> None:
        """Re-run the dry-run organization."""
        self._current_plan = None
        self.query_one(BeforeAfterPanel).update("[dim]Refreshing...[/dim]")
        self.query_one(OrganizationSummary).update("[dim]Calculating...[/dim]")
        self._load_preview()

    def action_confirm(self) -> None:
        """Apply the currently previewed organization and open History."""
        if self._is_applying:
            self._set_status("Organization is already applying...")
            return
        if self._current_plan is None:
            self._set_status("Refresh preview before applying.")
            self.query_one(BeforeAfterPanel).update(
                "[yellow]No reviewed plan is loaded.[/yellow]\n\n"
                "[dim]Refresh the preview, review the proposed changes, then confirm.[/dim]"
            )
            return

        plan = self._current_plan
        self._is_applying = True
        self.query_one(BeforeAfterPanel).update("[dim]Applying organization...[/dim]")
        self.query_one(OrganizationSummary).update("[dim]Working...[/dim]")
        self._set_status("Applying organization...")
        self._apply_organization(plan)

    def action_cancel(self) -> None:
        """Go back / cancel."""
        self._set_status("Ready")

    @work(thread=True)
    def _load_preview(self) -> None:
        """Run a dry-run organization in a worker thread."""
        try:
            request = self._build_request()
            result = (
                self._adapter.preview()
                if self._adapter is not None
                else self._create_service().preview(request)
            )
            plan = getattr(result, "plan", None)
            if result.total_files == 0:
                panel = self.query_one(BeforeAfterPanel)
                summary = self.query_one(OrganizationSummary)
                self.app.call_from_thread(self._set_current_plan, None)
                self.app.call_from_thread(panel.set_structure, {}, str(request.input_path))
                self.app.call_from_thread(
                    summary.set_result,
                    total=result.total_files,
                    processed=result.processed_files,
                    skipped=result.skipped_files,
                    failed=result.failed_files,
                    folders=0,
                    errors=result.errors,
                )
                self.app.call_from_thread(self._set_status, "No files to organize")
                return
            if not isinstance(plan, OrganizationPlan):
                raise RuntimeError("Preview did not produce an executable plan.")

            panel = self.query_one(BeforeAfterPanel)
            summary = self.query_one(OrganizationSummary)

            self.app.call_from_thread(
                self._set_current_plan,
                plan,
            )
            self.app.call_from_thread(self._set_current_request, request)
            self.app.call_from_thread(
                panel.set_structure,
                plan.organized_structure(),
                str(request.input_path),
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
            self._record_error(exc)
            self.app.call_from_thread(self._set_current_plan, None)
            self.app.call_from_thread(
                self.query_one(BeforeAfterPanel).update,
                f"[red]Preview unavailable:[/red] {exc}\n\n"
                "[dim]Review the workspace paths, selection scope, options, and model setup.[/dim]",
            )
            self.app.call_from_thread(
                self.query_one(OrganizationSummary).update,
                "[dim]No data available.[/dim]",
            )

    @work(thread=True)
    def _apply_organization(self, plan: OrganizationPlan | None) -> None:
        """Run the reviewed organization for real and navigate to history."""
        try:
            if plan is None:
                raise RuntimeError("Refresh preview before applying.")
            request = self._current_request or self._build_request()
            result = (
                self._adapter.execute(plan)
                if self._adapter is not None
                else self._create_service().execute(request, plan)
            )

            self.app.call_from_thread(self._handle_apply_success, result)
        except Exception as exc:
            self._record_error(exc)
            self.app.call_from_thread(self._handle_apply_error, exc)

    def _set_current_plan(self, plan: OrganizationPlan | None) -> None:
        """Store the last reviewed executable plan."""
        self._current_plan = plan
        if self._workspace is not None:
            self._workspace.reviewed_plan = plan

    def _set_current_request(self, request: OrganizeRequest) -> None:
        """Store the exact request represented by the reviewed plan."""
        self._current_request = request

    def _handle_apply_success(self, result: OrganizationResult) -> None:
        """Update the preview with the applied result and switch to History."""
        self._is_applying = False
        if self._workspace is not None:
            self._workspace.last_result = result
            self._workspace.last_error = None
        panel = self.query_one(BeforeAfterPanel)
        summary = self.query_one(OrganizationSummary)
        organized_structure = getattr(result, "organized_structure", {})
        panel.set_structure(organized_structure, str(self._input_dir))
        summary.set_result(
            total=getattr(result, "total_files", 0),
            processed=getattr(result, "processed_files", 0),
            skipped=getattr(result, "skipped_files", 0),
            failed=getattr(result, "failed_files", 0),
            folders=len(organized_structure),
            errors=getattr(result, "errors", []),
        )
        self._set_status("Organization applied. Opening history.")
        switch_view = getattr(self.app, "action_switch_view", None)
        if switch_view is not None:
            result = switch_view("history")
            if hasattr(result, "__await__"):
                self.app.run_worker(result, exclusive=False)

    def _handle_apply_error(self, exc: Exception) -> None:
        """Show apply failures without leaving the preview."""
        self._is_applying = False
        self.query_one(BeforeAfterPanel).update(
            f"[red]Apply failed:[/red] {exc}\n\n"
            "[dim]Some files may have been changed. Check History before retrying.[/dim]"
        )
        self.query_one(OrganizationSummary).update("[dim]No data available.[/dim]")
        self._set_status("Apply failed")

    def _build_request(self) -> OrganizeRequest:
        """Build the exact canonical request represented by the visible workspace."""
        if self._workspace is not None:
            if self._adapter is None:
                raise RuntimeError("TUI organization adapter is unavailable.")
            return self._adapter.request()
        runtime_settings = load_parallel_runtime_settings()
        options = OrganizeOptions(
            parallel_workers=runtime_settings.max_workers,
            prefetch_depth=runtime_settings.prefetch_depth,
        )
        if self._input_dir is None or self._output_dir is None:
            raise DomainError(
                DomainErrorCode.INVALID_REQUEST,
                "Explicit source and output directories are required before preview.",
            )
        return OrganizeRequest(self._input_dir, self._output_dir, options)

    @staticmethod
    def _create_service() -> OrganizationService:
        """Create the canonical service while preserving the organizer test seam."""
        from file_organizer.core.organizer import FileOrganizer

        return OrganizationService(organizer_factory=FileOrganizer)

    def _options_summary(self) -> str:
        """Render effective roots, scope, and every behavior-affecting option."""
        if self._workspace is not None:
            source = (
                str(self._workspace.active_root)
                if self._workspace.active_root is not None
                else "[unset]"
            )
            output = (
                str(self._workspace.output_root)
                if self._workspace.output_root is not None
                else "[unset]"
            )
            selected = len(self._workspace.selected_files)
            options = self._workspace.options
        else:
            source = str(self._input_dir) if self._input_dir is not None else "[unset]"
            output = str(self._output_dir) if self._output_dir is not None else "[unset]"
            selected = 0
            runtime = load_parallel_runtime_settings()
            options = OrganizeOptions(
                parallel_workers=runtime.max_workers,
                prefetch_depth=runtime.prefetch_depth,
            )
        fields = options.to_dict()
        option_text = " · ".join(f"{name}={value}" for name, value in fields.items())
        return (
            f"Source: {source}\nOutput: {output}\nSelection: {selected} files\n"
            f"[dim]{option_text}[/dim]"
        )

    def _record_error(self, exc: Exception) -> None:
        """Retain domain failures unchanged in meaning for the History view."""
        if self._workspace is None:
            return
        self._workspace.record_error(exc)
