# pyre-ignore-all-errors
"""Reader for eBook formats (EPUB).

Accepts either a path (legacy) or an open binary file-like via the
``fileobj`` keyword. The file-like path is the SafeDir-friendly entry
point: callers open via ``SafeDir.open_for_reader``, wrap in
``os.fdopen(fd, "rb")``, and hand to the reader. ``ebooklib`` itself
delegates to ``zipfile`` for the underlying read, which accepts both
paths and file-like objects.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

try:
    import ebooklib
    from ebooklib import epub

    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False

from loguru import logger

from file_organizer.utils.readers._base import FileReadError, _check_fd_size, _check_file_size


def _parse_epub(source: object, max_chars: int, label: str) -> str:
    """Parse an EPUB from either a path string or an open file-like.

    ``epub.read_epub`` delegates to ``zipfile.ZipFile`` for the archive
    container; both accept a path string or a file-like, so the helper
    forwards either kind without further branching.
    """
    book = epub.read_epub(source)

    text_parts = []
    total_chars = 0

    for item in book.get_items():
        if item.get_type() == ebooklib.ITEM_DOCUMENT:
            content = item.get_content().decode("utf-8", errors="ignore")
            # Basic HTML stripping (simple approach)
            content = re.sub(r"<[^>]+>", " ", content)
            content = re.sub(r"\s+", " ", content).strip()

            if content:
                text_parts.append(content)
                total_chars += len(content)

                if total_chars >= max_chars:
                    break

    text = " ".join(text_parts)[:max_chars]
    logger.debug(f"Extracted {len(text)} characters from ebook {label}")
    return text


def read_ebook_file(
    file_path: str | Path | None = None,
    max_chars: int = 10000,
    *,
    fileobj: BinaryIO | None = None,
) -> str:
    """Read text content from ebook file (EPUB only for now).

    Args:
        file_path: Path to ebook file (legacy entry point).
        max_chars: Maximum characters to extract
        fileobj: Open binary file-like (SafeDir-friendly entry point). When
            given, ``file_path`` is used for extension validation and the
            log label; only ``.epub`` is supported.

    Returns:
        Extracted text content

    Raises:
        FileReadError: If file cannot be read or extension is unsupported.
        FileTooLargeError: If the file behind ``fileobj`` exceeds the limit.
        ImportError: If ebooklib is not installed
        ValueError: If neither ``file_path`` nor ``fileobj`` is provided.
    """
    # Argument-validation contract is independent of the optional dep —
    # raise ValueError on missing args BEFORE checking EBOOKLIB_AVAILABLE.
    if fileobj is None and file_path is None:
        raise ValueError("read_ebook_file requires file_path or fileobj")
    if not EBOOKLIB_AVAILABLE:
        raise ImportError("ebooklib is not installed. Install with: pip install ebooklib")

    if fileobj is not None:
        label = Path(file_path).name if file_path is not None else "<fileobj>"
        # Extension validation — preserves the legacy "only .epub" contract
        # for the fileobj branch too. ``file_path`` is required when the
        # extension isn't a literal ``.epub`` because we can't sniff it
        # from the stream without consuming bytes.
        if file_path is not None and Path(file_path).suffix.lower() != ".epub":
            raise FileReadError(
                f"Unsupported ebook format: {Path(file_path).suffix}. Only .epub supported."
            )
        # Size check outside the try so ``FileTooLargeError`` propagates.
        _check_fd_size(fileobj)
        try:
            return _parse_epub(fileobj, max_chars, label)
        except Exception as e:  # Intentional catch-all: ebooklib raises library-specific errors
            raise FileReadError(f"Failed to read ebook file {label}: {e}") from e
    assert file_path is not None  # narrowed by the early ValueError above
    path = Path(file_path)
    _check_file_size(path)
    try:
        if path.suffix.lower() != ".epub":
            raise FileReadError(f"Unsupported ebook format: {path.suffix}. Only .epub supported.")
        return _parse_epub(str(path), max_chars, path.name)
    except FileReadError:
        raise
    except Exception as e:  # Intentional catch-all: ebooklib raises library-specific errors
        raise FileReadError(f"Failed to read ebook file {path}: {e}") from e
