"""Preprocessor stage - file validation and metadata extraction.

Validates that the file exists, is a regular file, and has a supported
extension.  Populates ``context.metadata`` with file size, extension,
and modification time.
"""

from __future__ import annotations

import logging
import mimetypes

from file_organizer.interfaces.pipeline import StageContext

logger = logging.getLogger(__name__)


class PreprocessorStage:
    """Validate files and extract metadata.

    Populates ``context.metadata`` with:

    - ``size_bytes``: File size in bytes.
    - ``extension``: Lowercase file extension (e.g. ``".pdf"``).
    - ``mime_type``: Guessed MIME type (or ``None``).
    - ``mtime``: Last modification timestamp.
    - ``stem``: Filename without extension.
    """

    def __init__(
        self,
        supported_extensions: frozenset[str] | None = None,
    ) -> None:
        """Initialize with optional extension filter."""
        self._supported_extensions = supported_extensions

    @property
    def name(self) -> str:
        """Return stage name."""
        return "preprocessor"

    def process(self, context: StageContext) -> StageContext:
        """Validate file and extract metadata into *context*."""
        if context.failed:
            return context

        path = context.file_path

        if not path.exists():
            context.error = f"File not found: {path}"
            return context

        if not path.is_file():
            context.error = f"Not a file: {path}"
            return context

        ext = path.suffix.lower()
        if self._supported_extensions is not None and ext not in self._supported_extensions:
            context.error = f"Unsupported file extension: {ext}"
            return context

        try:
            stat = path.stat()
        except OSError as exc:
            context.error = f"Cannot read file metadata: {exc}"
            return context
        mime_type, _ = mimetypes.guess_type(str(path))

        context.metadata = {
            "size_bytes": stat.st_size,
            "extension": ext,
            "mime_type": mime_type,
            "mtime": stat.st_mtime,
            "stem": path.stem,
        }
        context.filename = path.stem

        logger.debug("Preprocessed %s (%s, %d bytes)", path.name, ext, stat.st_size)
        return context
