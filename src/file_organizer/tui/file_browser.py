"""TUI file browser with directory tree, metadata panel, and filtering.

Provides a navigable directory tree with vim keybindings, a metadata
panel for the highlighted file, and a filter input for extension-based
filtering.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import DirectoryTree, Input, Static

if TYPE_CHECKING:
    from textual.widgets._directory_tree import DirEntry


def _format_size(size: int) -> str:
    """Format a file size in human-readable form.

    Args:
        size: Size in bytes.

    Returns:
        Formatted string like ``1.2 MB``.
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024  # type: ignore[assignment]
    return f"{size:.1f} PB"


class FileBrowserTree(DirectoryTree):
    """Directory tree with extension filtering and vim keybindings.

    Extends Textual's built-in ``DirectoryTree`` which already handles
    lazy-loading of directory contents.
    """

    BINDINGS = [
        Binding("h", "cursor_parent", "Parent", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("l", "cursor_toggle", "Expand", show=False),
    ]

    def __init__(
        self,
        path: str | Path = ".",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the file browser tree with the given path and widget parameters."""
        super().__init__(path, name=name, id=id, classes=classes)
        self._extension_filter: set[str] = set()

    def set_extension_filter(self, extensions: set[str]) -> None:
        """Apply an extension filter and reload the tree.

        Args:
            extensions: Set of extensions to show (e.g. ``{'.py', '.txt'}``).
                        Pass an empty set to clear the filter.
        """
        self._extension_filter = {ext if ext.startswith(".") else f".{ext}" for ext in extensions}
        try:
            self.reload()
        except RuntimeError:
            # No event loop available (e.g. during unit tests)
            pass

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        """Filter visible paths based on the current extension filter.

        Directories are always shown so the tree remains navigable.

        Args:
            paths: Candidate paths to filter.

        Returns:
            Filtered iterable of paths.
        """
        if not self._extension_filter:
            return paths
        return [p for p in paths if p.is_dir() or p.suffix.lower() in self._extension_filter]

    # Vim-style cursor actions ------------------------------------------

    def action_cursor_parent(self) -> None:
        """Move cursor to parent node (vim ``h``)."""
        node = self.cursor_node
        if node is not None and node.parent is not None:
            self.select_node(node.parent)
            node.parent.expand()

    def action_cursor_toggle(self) -> None:
        """Expand directory or select file (vim ``l``)."""
        node = self.cursor_node
        if node is not None:
            if node.allow_expand:
                node.toggle()
            else:
                if node.data is not None:
                    self.post_message(self.FileSelected(node, node.data.path))


class FileMetadataPanel(Static):
    """Displays metadata for the currently highlighted file."""

    DEFAULT_CSS = """
    FileMetadataPanel {
        height: 5;
        dock: bottom;
        padding: 0 1;
        background: $surface;
        border-top: solid $primary;
    }
    """

    def show_metadata(self, path: Path) -> None:
        """Update the panel with metadata for *path*.

        Args:
            path: File or directory path to inspect.
        """
        if not path.exists():
            self.update("[dim]Path not found[/dim]")
            return
        try:
            stat = path.stat()
            size = _format_size(stat.st_size)
            modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
            kind = "Directory" if path.is_dir() else (path.suffix or "File")
            self.update(f"[b]{path.name}[/b]\nType: {kind}  Size: {size}  Modified: {modified}")
        except OSError:
            self.update(f"[dim]Cannot read metadata for {path.name}[/dim]")


class FilterInput(Input):
    """Hidden filter input toggled with ``/``.

    When the user presses Enter, posts a ``FilterInput.Submitted``
    message with the filter value, then hides itself.
    """

    DEFAULT_CSS = """
    FilterInput {
        display: none;
        dock: top;
        height: 1;
    }
    FilterInput.-visible {
        display: block;
    }
    """

    class Submitted(Message):
        """Posted when the user submits a filter value."""

        def __init__(self, value: str) -> None:
            """Create a submitted message carrying the input value."""
            super().__init__()
            self.value = value

    def toggle_visibility(self) -> None:
        """Show or hide the filter input."""
        self.toggle_class("-visible")
        if self.has_class("-visible"):
            self.focus()
        else:
            self.value = ""

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key — post filter and hide."""
        self.post_message(self.Submitted(event.value))
        self.remove_class("-visible")
        self.value = ""


class FileBrowserView(Vertical):
    """Composite view: filter + directory tree + metadata panel.

    Posts ``FileHighlighted`` when the user highlights a file in the tree.
    """

    DEFAULT_CSS = """
    FileBrowserView {
        width: 1fr;
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("slash", "toggle_filter", "Filter", show=True),
    ]

    class FileHighlighted(Message):
        """Posted when a file is highlighted in the tree."""

        def __init__(self, path: Path) -> None:
            """Create a message carrying the highlighted file path."""
            super().__init__()
            self.path = path

    def __init__(
        self,
        path: str | Path = ".",
        *,
        name: str | None = None,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Set up the file browser view with the given root path."""
        super().__init__(name=name, id=id, classes=classes)
        self._root_path = Path(path)

    def compose(self) -> ComposeResult:
        """Build the file browser layout."""
        yield FilterInput(placeholder="Filter extensions (e.g. .py .txt) …")
        yield FileBrowserTree(self._root_path, id="file-tree")
        yield FileMetadataPanel("[dim]Select a file to view metadata[/dim]")

    # Event handlers ---------------------------------------------------

    @on(DirectoryTree.NodeHighlighted)
    def _on_node_highlighted(self, event: DirectoryTree.NodeHighlighted[DirEntry]) -> None:
        """Update metadata panel and post FileHighlighted message."""
        node = event.node
        path = node.data.path if node.data else None
        if path is not None:
            self.query_one(FileMetadataPanel).show_metadata(path)
            self.post_message(self.FileHighlighted(path))

    @on(FilterInput.Submitted)
    def _on_filter_submitted(self, event: FilterInput.Submitted) -> None:
        """Apply the extension filter from the filter input."""
        raw = event.value.strip()
        if raw:
            extensions = {tok.strip() for tok in raw.replace(",", " ").split() if tok.strip()}
        else:
            extensions = set()
        self.query_one(FileBrowserTree).set_extension_filter(extensions)

    def action_toggle_filter(self) -> None:
        """Show/hide the filter input."""
        self.query_one(FilterInput).toggle_visibility()
