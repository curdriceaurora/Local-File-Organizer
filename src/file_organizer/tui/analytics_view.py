# pyre-ignore-all-errors
"""TUI analytics dashboard view.

Provides storage overview, file distribution chart, quality scores,
and duplicate statistics in a scrollable panel layout.
"""

from __future__ import annotations

import logging
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

logger = logging.getLogger(__name__)


class StorageOverviewPanel(Static):
    """Displays total size, file/dir counts, organized size, and space saved."""

    DEFAULT_CSS = """
    StorageOverviewPanel {
        height: auto;
        padding: 1 2;
    }
    """

    def set_stats(
        self,
        total_size: str = "0 B",
        file_count: int = 0,
        dir_count: int = 0,
        organized_size: str = "0 B",
        saved_size: str = "0 B",
    ) -> None:
        """Update the storage overview display.

        Args:
            total_size: Human-readable total size.
            file_count: Number of files.
            dir_count: Number of directories.
            organized_size: Human-readable organized size.
            saved_size: Human-readable space saved.
        """
        self.update(
            "[b]Storage Overview[/b]\n\n"
            f"  Total size:     {total_size}\n"
            f"  Files:          {file_count:,}\n"
            f"  Directories:    {dir_count:,}\n"
            f"  Organized size: {organized_size}\n"
            f"  Space saved:    [green]{saved_size}[/green]"
        )


class FileDistributionPanel(Static):
    """ASCII bar chart of top file types by size."""

    DEFAULT_CSS = """
    FileDistributionPanel {
        height: auto;
        padding: 1 2;
        margin-top: 1;
    }
    """

    def set_distribution(
        self,
        size_by_type: dict[str, int],
        top_n: int = 10,
    ) -> None:
        """Render a horizontal bar chart of file types.

        Args:
            size_by_type: Mapping of file extension to total bytes.
            top_n: Maximum number of types to display.
        """
        if not size_by_type:
            self.update("[b]File Distribution[/b]\n\n  [dim]No data.[/dim]")
            return

        sorted_types = sorted(size_by_type.items(), key=lambda x: x[1], reverse=True)[:top_n]
        max_val = sorted_types[0][1] if sorted_types else 1

        lines = ["[b]File Distribution[/b]  (by size)\n"]
        for ext, size in sorted_types:
            bar_len = max(1, int(size / max_val * 30))
            bar = "[cyan]" + "#" * bar_len + "[/cyan]"
            size_str = _format_bytes(size)
            lines.append(f"  {ext:<8} {bar} {size_str}")

        self.update("\n".join(lines))


class QualityScorePanel(Static):
    """Letter grade with breakdown bars for naming/structure/metadata/categorization."""

    DEFAULT_CSS = """
    QualityScorePanel {
        height: auto;
        padding: 1 2;
        margin-top: 1;
        background: $surface;
    }
    """

    def set_metrics(
        self,
        grade: str = "?",
        naming: float = 0.0,
        structure: float = 0.0,
        metadata: float = 0.0,
        categorization: float = 0.0,
    ) -> None:
        """Update the quality score display.

        Args:
            grade: Letter grade (A-F).
            naming: Naming compliance score (0-1).
            structure: Structure consistency score (0-1).
            metadata: Metadata completeness score (0-1).
            categorization: Categorization accuracy score (0-1).
        """
        lines = [f"[b]Quality Score[/b]  Grade: [bold]{grade}[/bold]\n"]
        metrics = [
            ("Naming", naming),
            ("Structure", structure),
            ("Metadata", metadata),
            ("Categorize", categorization),
        ]
        for label, value in metrics:
            filled = int(value * 20)
            bar = "[green]" + "#" * filled + "[/green]" + "." * (20 - filled)
            pct = int(value * 100)
            lines.append(f"  {label:<12} {bar} {pct}%")

        self.update("\n".join(lines))


class DuplicateStatsPanel(Static):
    """Shows duplicate groups count, space wasted, and recoverable space."""

    DEFAULT_CSS = """
    DuplicateStatsPanel {
        height: auto;
        padding: 1 2;
        margin-top: 1;
    }
    """

    def set_stats(
        self,
        groups: int = 0,
        space_wasted: str = "0 B",
        recoverable: str = "0 B",
    ) -> None:
        """Update the duplicate statistics display.

        Args:
            groups: Number of duplicate groups.
            space_wasted: Human-readable wasted space.
            recoverable: Human-readable recoverable space.
        """
        self.update(
            "[b]Duplicate Detection[/b]\n\n"
            f"  Groups found:   {groups:,}\n"
            f"  Space wasted:   [red]{space_wasted}[/red]\n"
            f"  Recoverable:    [green]{recoverable}[/green]"
        )


class AnalyticsView(Vertical):
    """Analytics dashboard mounted as ``#view`` for the Analytics nav.

    Bindings:
        r - Refresh analytics data
    """

    DEFAULT_CSS = """
    AnalyticsView {
        width: 1fr;
        height: 1fr;
        overflow-y: auto;
    }
    """

    BINDINGS = [
        Binding("r", "refresh_analytics", "Refresh", show=True),
    ]

    def __init__(
        self,
        directory: str | Path = ".",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the analytics view for the given directory."""
        super().__init__(name=name, id=id, classes=classes)
        self._directory = Path(directory)

    def compose(self) -> ComposeResult:
        """Build the analytics dashboard layout."""
        yield Static("[b]Analytics Dashboard[/b]\n", id="analytics-header")
        yield StorageOverviewPanel("[dim]Loading...[/dim]")
        yield FileDistributionPanel("[dim]Loading...[/dim]")
        yield QualityScorePanel("[dim]Loading...[/dim]")
        yield DuplicateStatsPanel("[dim]Loading...[/dim]")

    def on_mount(self) -> None:
        """Trigger the initial analytics load."""
        self._load_analytics()

    def action_refresh_analytics(self) -> None:
        """Reload analytics data."""
        for panel_type in (
            StorageOverviewPanel,
            FileDistributionPanel,
            QualityScorePanel,
            DuplicateStatsPanel,
        ):
            self.query_one(panel_type).update("[dim]Refreshing...[/dim]")
        self._load_analytics()

    @work(thread=True)
    def _load_analytics(self) -> None:
        """Load analytics data in a worker thread."""
        try:
            from file_organizer.services.analytics.analytics_service import (
                AnalyticsService,
            )

            service = AnalyticsService()
            dashboard = service.generate_dashboard(self._directory)

            ss = dashboard.storage_stats
            self.app.call_from_thread(
                self.query_one(StorageOverviewPanel).set_stats,
                total_size=ss.formatted_total_size,
                file_count=ss.file_count,
                dir_count=ss.directory_count,
                organized_size=_format_bytes(ss.organized_size),
                saved_size=ss.formatted_saved_size,
            )

            self.app.call_from_thread(
                self.query_one(FileDistributionPanel).set_distribution,
                ss.size_by_type,
            )

            qm = dashboard.quality_metrics
            self.app.call_from_thread(
                self.query_one(QualityScorePanel).set_metrics,
                grade=qm.grade,
                naming=qm.naming_compliance,
                structure=qm.structure_consistency,
                metadata=qm.metadata_completeness,
                categorization=qm.categorization_accuracy,
            )

            ds = dashboard.duplicate_stats
            self.app.call_from_thread(
                self.query_one(DuplicateStatsPanel).set_stats,
                groups=ds.duplicate_groups,
                space_wasted=ds.formatted_space_wasted,
                recoverable=ds.formatted_recoverable,
            )

            self.app.call_from_thread(self._set_status, "Analytics loaded")

        except Exception as exc:
            msg = f"[red]Analytics unavailable:[/red] {exc}"
            for panel_type in (
                StorageOverviewPanel,
                FileDistributionPanel,
                QualityScorePanel,
                DuplicateStatsPanel,
            ):
                self.app.call_from_thread(self.query_one(panel_type).update, msg)

    def _set_status(self, message: str) -> None:
        """Update the app status bar if available."""
        try:
            from file_organizer.tui.app import StatusBar

            self.app.query_one(StatusBar).set_status(message)
        except Exception:
            logger.debug("AnalyticsView status bar unavailable", exc_info=True)


def _format_bytes(num_bytes: int) -> str:
    """Format bytes into a human-readable string.

    Args:
        num_bytes: Number of bytes.

    Returns:
        Formatted string like '1.2 MB'.
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024:
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} {unit}"
        num_bytes = num_bytes / 1024  # type: ignore[assignment]
    return f"{num_bytes:.1f} PB"
