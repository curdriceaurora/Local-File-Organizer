"""TUI PARA/JD methodology selector and preview.

Allows users to choose a file organization methodology (PARA, Johnny Decimal,
or none) and preview how files would be categorized under the selected scheme.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static


class MethodologySelectorPanel(Static):
    """Displays the currently active methodology with keybinding hints."""

    DEFAULT_CSS = """
    MethodologySelectorPanel {
        height: auto;
        padding: 1 2;
    }
    """

    _METHODS = {
        "none": "None (flat organization)",
        "para": "PARA (Projects / Areas / Resources / Archive)",
        "jd": "Johnny Decimal (Areas / Categories / Items)",
    }

    _current: str = "none"

    def on_mount(self) -> None:
        """Render the initial state."""
        self._render_selector()

    def set_methodology(self, methodology: str) -> None:
        """Change the highlighted methodology.

        Args:
            methodology: One of 'none', 'para', 'jd'.
        """
        self._current = methodology
        self._render_selector()

    def _render_selector(self) -> None:
        """Redraw the selector."""
        lines = ["[b]Methodology Selector[/b]\n"]
        for key, label in self._METHODS.items():
            marker = "[bold green]>[/bold green] " if key == self._current else "  "
            shortcut = {"none": "n", "para": "p", "jd": "j"}[key]
            lines.append(f"{marker}[{shortcut}] {label}")
        lines.append("\n[dim]Press p/j/n to switch, m to migrate (coming soon)[/dim]")
        self.update("\n".join(lines))

    @property
    def current_methodology(self) -> str:
        """Currently selected methodology."""
        return self._current


class MethodologyPreviewPanel(Static):
    """Preview of how files would be organized under the selected methodology."""

    DEFAULT_CSS = """
    MethodologyPreviewPanel {
        height: auto;
        padding: 1 2;
        margin-top: 1;
        background: $surface;
        overflow-y: auto;
    }
    """

    def show_none_preview(self) -> None:
        """Show preview for no methodology."""
        self.update(
            "[b]No Methodology[/b]\n\n"
            "Files are organized by AI-suggested categories\n"
            "without a structured methodology framework."
        )

    def show_para_preview(
        self,
        distribution: Optional[dict[str, int]] = None,
    ) -> None:
        """Show PARA category distribution.

        Args:
            distribution: Mapping of PARA category to file count.
        """
        lines = ["[b]PARA Preview[/b]\n"]
        if distribution:
            total = sum(distribution.values()) or 1
            for cat in ("Projects", "Areas", "Resources", "Archive"):
                count = distribution.get(cat, 0)
                pct = int(count / total * 20)
                bar = "[green]" + "#" * pct + "[/green]" + "." * (20 - pct)
                lines.append(f"  {cat:<12} {bar} {count}")
        else:
            lines.append("  [dim]No files analyzed yet.[/dim]")
        self.update("\n".join(lines))

    def show_jd_preview(
        self,
        areas: Optional[dict[int, str]] = None,
        categories: Optional[dict[str, str]] = None,
    ) -> None:
        """Show Johnny Decimal scheme overview.

        Args:
            areas: Mapping of area number to title.
            categories: Mapping of category ID to title.
        """
        lines = ["[b]Johnny Decimal Preview[/b]\n"]
        if areas:
            for num, title in sorted(areas.items()):
                lines.append(f"  [bold cyan]{num:02d}-{num + 9:02d}[/bold cyan]  {title}")
                if categories:
                    for cat_id, cat_title in sorted(categories.items()):
                        if cat_id.isdigit() and num <= int(cat_id) < num + 10:
                            lines.append(f"    {cat_id}  {cat_title}")
        else:
            lines.append("  [dim]No scheme configured.[/dim]")
        self.update("\n".join(lines))

    def show_loading(self) -> None:
        """Show loading state."""
        self.update("[dim]Loading preview...[/dim]")

    def show_error(self, message: str) -> None:
        """Show an error message.

        Args:
            message: Error description.
        """
        self.update(f"[red]Error:[/red] {message}")


class MethodologyView(Vertical):
    """Methodology selector view mounted as ``#view``.

    Bindings:
        p - Select PARA methodology
        j - Select Johnny Decimal
        n - Select no methodology
        m - Migrate files (placeholder)
    """

    DEFAULT_CSS = """
    MethodologyView {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("p", "set_para", "PARA", show=True),
        Binding("j", "set_jd", "JD", show=True),
        Binding("n", "set_none", "None", show=True),
        Binding("m", "migrate", "Migrate", show=True),
    ]

    _MAX_SAMPLE_FILES = 200

    def __init__(
        self,
        scan_dir: str | Path = ".",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the methodology view to scan the given directory."""
        super().__init__(name=name, id=id, classes=classes)
        self._scan_dir = Path(scan_dir)
        self._methodology = "none"

    def compose(self) -> ComposeResult:
        """Build the methodology view layout."""
        yield MethodologySelectorPanel()
        yield MethodologyPreviewPanel("[dim]Select a methodology to preview.[/dim]")

    def on_mount(self) -> None:
        """Show initial preview."""
        self._update_preview()

    def action_set_para(self) -> None:
        """Switch to PARA methodology."""
        self._methodology = "para"
        self.query_one(MethodologySelectorPanel).set_methodology("para")
        self._update_preview()

    def action_set_jd(self) -> None:
        """Switch to Johnny Decimal methodology."""
        self._methodology = "jd"
        self.query_one(MethodologySelectorPanel).set_methodology("jd")
        self._update_preview()

    def action_set_none(self) -> None:
        """Switch to no methodology."""
        self._methodology = "none"
        self.query_one(MethodologySelectorPanel).set_methodology("none")
        self._update_preview()

    def action_migrate(self) -> None:
        """Placeholder for migration action."""
        self._set_status("Migration not yet implemented.")

    def _update_preview(self) -> None:
        """Dispatch preview update based on current methodology."""
        preview = self.query_one(MethodologyPreviewPanel)
        if self._methodology == "none":
            preview.show_none_preview()
        elif self._methodology == "para":
            preview.show_loading()
            self._load_para_preview()
        elif self._methodology == "jd":
            preview.show_loading()
            self._load_jd_preview()

    @work(thread=True)
    def _load_para_preview(self) -> None:
        """Load PARA category distribution in a worker thread."""
        try:
            from file_organizer.methodologies.para.folder_mapper import (
                CategoryFolderMapper,
            )

            mapper = CategoryFolderMapper()
            scan = self._scan_dir
            files = [p for p in scan.rglob("*") if p.is_file()][: self._MAX_SAMPLE_FILES]

            if not files:
                self.app.call_from_thread(
                    self.query_one(MethodologyPreviewPanel).show_para_preview,
                    None,
                )
                return

            results = mapper.map_batch(files, scan)
            distribution: dict[str, int] = {}
            for r in results:
                cat_name = (
                    r.target_category.value
                    if hasattr(r.target_category, "value")
                    else str(r.target_category)
                )
                distribution[cat_name] = distribution.get(cat_name, 0) + 1

            self.app.call_from_thread(
                self.query_one(MethodologyPreviewPanel).show_para_preview,
                distribution,
            )
        except Exception as exc:
            self.app.call_from_thread(
                self.query_one(MethodologyPreviewPanel).show_error,
                str(exc),
            )

    @work(thread=True)
    def _load_jd_preview(self) -> None:
        """Load Johnny Decimal scheme overview in a worker thread."""
        try:
            from file_organizer.methodologies.johnny_decimal.config import (
                create_default_config,
            )

            config = create_default_config()
            scheme = config.scheme

            areas = {num: defn.name for num, defn in scheme.areas.items()} if scheme.areas else {}

            categories = (
                {cat_id: defn.name for cat_id, defn in scheme.categories.items()}
                if scheme.categories
                else {}
            )

            self.app.call_from_thread(
                self.query_one(MethodologyPreviewPanel).show_jd_preview,
                areas,
                categories,
            )
        except Exception as exc:
            self.app.call_from_thread(
                self.query_one(MethodologyPreviewPanel).show_error,
                str(exc),
            )

    def _set_status(self, message: str) -> None:
        """Update the app status bar if available."""
        try:
            from file_organizer.tui.app import StatusBar

            self.app.query_one(StatusBar).set_status(message)
        except Exception:
            pass
