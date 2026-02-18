"""Path auto-completion callbacks for Typer CLI arguments.

Provides completion helpers that enumerate directory children matching
a user-typed prefix, suitable for ``typer.Argument(autocompletion=...)``.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def complete_directory(incomplete: str) -> Iterator[tuple[str, str]]:
    """Yield directory completions matching *incomplete*.

    Args:
        incomplete: Partial directory path typed by the user.

    Yields:
        ``(completion, help_text)`` pairs for each matching directory.
    """
    search = Path(incomplete) if incomplete else Path(".")
    parent = search.parent if not search.is_dir() else search
    prefix = search.name if not search.is_dir() else ""

    try:
        for child in sorted(parent.iterdir()):
            if child.is_dir() and child.name.startswith(prefix):
                yield str(child), "directory"
    except OSError:
        return


def complete_file(incomplete: str) -> Iterator[tuple[str, str]]:
    """Yield file completions matching *incomplete*.

    Args:
        incomplete: Partial file path typed by the user.

    Yields:
        ``(completion, help_text)`` pairs for each matching file or
        directory.
    """
    search = Path(incomplete) if incomplete else Path(".")
    parent = search.parent if not search.is_dir() else search
    prefix = search.name if not search.is_dir() else ""

    try:
        for child in sorted(parent.iterdir()):
            if child.name.startswith(prefix):
                kind = "directory" if child.is_dir() else child.suffix or "file"
                yield str(child), kind
    except OSError:
        return
