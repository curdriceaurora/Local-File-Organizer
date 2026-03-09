"""TUI file preview panel and selection manager.

Provides a split-pane view with the file browser on the left and a
type-dispatched preview panel on the right, plus multi-file selection.
"""

from __future__ import annotations

from pathlib import Path

from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Static

from file_organizer.tui.file_browser import FileBrowserView


class FileSelectionManager:
    """Tracks a set of selected file paths.

    Pure logic — no TUI dependency so it is easy to unit-test.
    """

    def __init__(self) -> None:
        """Create an empty file selection manager."""
        self._selected: set[Path] = set()

    def toggle(self, path: Path) -> bool:
        """Toggle *path* in the selection set.

        Args:
            path: File path to toggle.

        Returns:
            ``True`` if *path* is now selected, ``False`` if deselected.
        """
        if path in self._selected:
            self._selected.discard(path)
            return False
        self._selected.add(path)
        return True

    def select_all(self, paths: set[Path]) -> None:
        """Add all *paths* to the selection.

        Args:
            paths: Set of paths to select.
        """
        self._selected.update(paths)

    def clear(self) -> None:
        """Remove all paths from the selection."""
        self._selected.clear()

    @property
    def count(self) -> int:
        """Number of currently selected paths."""
        return len(self._selected)

    @property
    def selected_files(self) -> set[Path]:
        """Return a copy of the selected-paths set."""
        return set(self._selected)


class FilePreviewPanel(Static):
    """Displays a type-dispatched preview for the highlighted file.

    Preview strategies:
    - **Text files** — first ~100 lines
    - **Images** — PIL metadata (dimensions, mode, format)
    - **PDFs** — page count via PyMuPDF
    - **Archives** — file listing
    - **Generic** — ``os.stat()`` summary
    """

    DEFAULT_CSS = """
    FilePreviewPanel {
        width: 1fr;
        padding: 1 2;
        overflow-y: auto;
    }
    """

    _TEXT_EXTENSIONS = {
        ".txt",
        ".md",
        ".py",
        ".js",
        ".ts",
        ".json",
        ".yaml",
        ".yml",
        ".toml",
        ".cfg",
        ".ini",
        ".csv",
        ".log",
        ".sh",
        ".bash",
        ".html",
        ".css",
        ".xml",
        ".rst",
        ".tex",
        ".sql",
    }
    _IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif", ".webp"}
    _PDF_EXTENSIONS = {".pdf"}
    _ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz", ".7z", ".rar"}

    @work(thread=True)
    def show_preview(self, path: Path) -> None:
        """Generate and display a preview for *path*.

        Runs on a worker thread to avoid blocking the event loop for
        large files or slow I/O.

        Args:
            path: File to preview.
        """
        try:
            if not path.exists():
                self.app.call_from_thread(self.update, "[dim]File not found[/dim]")
                return

            if path.is_dir():
                content = self._preview_directory(path)
            elif path.suffix.lower() in self._TEXT_EXTENSIONS:
                content = self._preview_text(path)
            elif path.suffix.lower() in self._IMAGE_EXTENSIONS:
                content = self._preview_image(path)
            elif path.suffix.lower() in self._PDF_EXTENSIONS:
                content = self._preview_pdf(path)
            elif path.suffix.lower() in self._ARCHIVE_EXTENSIONS:
                content = self._preview_archive(path)
            else:
                content = self._preview_generic(path)

            self.app.call_from_thread(self.update, content)
        except (AttributeError, RuntimeError):
            # Widget may not be fully mounted yet (e.g. during tests)
            pass

    # ---- Preview strategies ------------------------------------------

    @staticmethod
    def _preview_text(path: Path, max_lines: int = 100) -> str:
        """Return the first *max_lines* of a text file."""
        try:
            lines = path.read_text(errors="replace").splitlines()[:max_lines]
            truncated = (
                f"\n[dim]… ({len(lines)} of ~{len(lines)} lines shown)[/dim]"
                if len(lines) == max_lines
                else ""
            )
            return "\n".join(lines) + truncated
        except OSError as exc:
            return f"[red]Cannot read file: {exc}[/red]"

    @staticmethod
    def _preview_image(path: Path) -> str:
        """Return image metadata using Pillow."""
        try:
            from PIL import Image

            with Image.open(path) as img:
                return (
                    f"[b]Image Preview[/b]\n\n"
                    f"Format: {img.format}\n"
                    f"Size: {img.size[0]} x {img.size[1]}\n"
                    f"Mode: {img.mode}\n"
                    f"File size: {path.stat().st_size:,} bytes"
                )
        except Exception as exc:
            return f"[b]Image[/b]\n\n[dim]Cannot read image metadata: {exc}[/dim]"

    @staticmethod
    def _preview_pdf(path: Path) -> str:
        """Return PDF page count using PyMuPDF."""
        try:
            import fitz  # PyMuPDF

            with fitz.open(path) as doc:
                return (
                    f"[b]PDF Preview[/b]\n\n"
                    f"Pages: {len(doc)}\n"
                    f"File size: {path.stat().st_size:,} bytes"
                )
        except Exception as exc:
            return f"[b]PDF[/b]\n\n[dim]Cannot read PDF: {exc}[/dim]"

    @staticmethod
    def _preview_archive(path: Path) -> str:
        """Return archive file listing."""
        try:
            from file_organizer.utils.file_readers import read_file

            content = read_file(str(path))
            if content:
                return f"[b]Archive Contents[/b]\n\n{content[:2000]}"
            return "[b]Archive[/b]\n\n[dim]Empty or unreadable archive[/dim]"
        except Exception as exc:
            return f"[b]Archive[/b]\n\n[dim]Cannot read archive: {exc}[/dim]"

    @staticmethod
    def _preview_directory(path: Path) -> str:
        """Return a listing of directory contents."""
        try:
            children = sorted(path.iterdir())[:50]
            lines = []
            for child in children:
                prefix = "[bold blue]D[/bold blue]" if child.is_dir() else " "
                lines.append(f"  {prefix} {child.name}")
            header = f"[b]{path.name}/[/b]  ({len(list(path.iterdir()))} items)\n"
            return header + "\n".join(lines)
        except OSError as exc:
            return f"[red]Cannot list directory: {exc}[/red]"

    @staticmethod
    def _preview_generic(path: Path) -> str:
        """Return a generic stat-based preview."""
        try:
            stat = path.stat()
            return (
                f"[b]{path.name}[/b]\n\n"
                f"Type: {path.suffix or 'unknown'}\n"
                f"Size: {stat.st_size:,} bytes\n"
                f"Modified: {stat.st_mtime}\n"
            )
        except OSError as exc:
            return f"[red]Cannot stat file: {exc}[/red]"


class FilePreviewView(Horizontal):
    """Split view: file browser (left) + preview panel (right).

    Bindings:
    - **Space** — Toggle file selection
    - **Ctrl+A** — Select all visible files
    - **Ctrl+D** — Deselect all
    """

    DEFAULT_CSS = """
    FilePreviewView {
        width: 1fr;
        height: 1fr;
    }
    FilePreviewView > FileBrowserView {
        width: 1fr;
    }
    FilePreviewView > FilePreviewPanel {
        width: 1fr;
        border-left: solid $primary;
    }
    """

    BINDINGS = [
        Binding("space", "toggle_select", "Select", show=True),
        Binding("ctrl+a", "select_all", "Select All", show=True),
        Binding("ctrl+d", "deselect_all", "Deselect", show=True),
    ]

    class SelectionChanged(Message):
        """Posted when the selection set changes."""

        def __init__(self, count: int) -> None:
            """Create a message with the new selection count."""
            super().__init__()
            self.count = count

    def __init__(
        self,
        path: str | Path = ".",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the file preview view rooted at the given path."""
        super().__init__(name=name, id=id, classes=classes)
        self._root_path = Path(path)
        self.selection = FileSelectionManager()
        self._current_path: Path | None = None

    def compose(self) -> ComposeResult:
        """Build the split-pane layout."""
        yield FileBrowserView(self._root_path)
        yield FilePreviewPanel("[dim]Select a file to preview[/dim]")

    # Event handlers ---------------------------------------------------

    @on(FileBrowserView.FileHighlighted)
    def _on_file_highlighted(self, event: FileBrowserView.FileHighlighted) -> None:
        """Update the preview panel when a file is highlighted."""
        self._current_path = event.path
        self.query_one(FilePreviewPanel).show_preview(event.path)

    # Actions ----------------------------------------------------------

    def action_toggle_select(self) -> None:
        """Toggle selection of the currently highlighted file."""
        if self._current_path and self._current_path.is_file():
            self.selection.toggle(self._current_path)
            self._notify_selection()

    def action_select_all(self) -> None:
        """Select all files in the current directory."""
        try:
            all_files = {p for p in self._root_path.rglob("*") if p.is_file()}
            self.selection.select_all(all_files)
            self._notify_selection()
        except OSError:
            pass

    def action_deselect_all(self) -> None:
        """Clear all selections."""
        self.selection.clear()
        self._notify_selection()

    def _notify_selection(self) -> None:
        """Post a ``SelectionChanged`` message and update the status bar."""
        self.post_message(self.SelectionChanged(self.selection.count))
        # Try to update the app's status bar if available
        try:
            from file_organizer.tui.app import StatusBar

            bar = self.app.query_one(StatusBar)
            count = self.selection.count
            bar.set_status(
                f"{count} file{'s' if count != 1 else ''} selected" if count else "Ready"
            )
        except Exception:
            pass
