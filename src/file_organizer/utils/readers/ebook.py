# pyre-ignore-all-errors
"""Reader for eBook formats (EPUB)."""

from __future__ import annotations

import re
from pathlib import Path

try:
    import ebooklib
    from ebooklib import epub

    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False

from loguru import logger

from file_organizer.utils.readers._base import FileReadError, _check_file_size


def read_ebook_file(file_path: str | Path, max_chars: int = 10000) -> str:
    """Read text content from ebook file (EPUB only for now).

    Args:
        file_path: Path to ebook file
        max_chars: Maximum characters to extract

    Returns:
        Extracted text content

    Raises:
        FileReadError: If file cannot be read
        ImportError: If ebooklib is not installed
    """
    if not EBOOKLIB_AVAILABLE:
        raise ImportError("ebooklib is not installed. Install with: pip install ebooklib")

    file_path = Path(file_path)
    _check_file_size(file_path)

    try:
        # Only support EPUB for now
        if file_path.suffix.lower() != ".epub":
            raise FileReadError(
                f"Unsupported ebook format: {file_path.suffix}. Only .epub supported."
            )
        book = epub.read_epub(file_path)

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

        logger.debug(f"Extracted {len(text)} characters from ebook {file_path.name}")
        return text
    except Exception as e:
        raise FileReadError(f"Failed to read ebook file {file_path}: {e}") from e
