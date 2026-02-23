"""File routing for the auto-organization pipeline.

Routes files to the appropriate processor based on file extension,
with support for custom routing rules.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from file_organizer._compat import StrEnum

logger = logging.getLogger(__name__)


class ProcessorType(StrEnum):
    """Types of file processors available in the pipeline."""

    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    UNKNOWN = "unknown"


# Default extension-to-processor mappings
_DEFAULT_TEXT_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".txt",
        ".md",
        ".docx",
        ".doc",
        ".pdf",
        ".csv",
        ".xlsx",
        ".xls",
        ".ppt",
        ".pptx",
        ".epub",
        ".dwg",
        ".dxf",
        ".step",
        ".stp",
        ".iges",
        ".igs",
    }
)

_DEFAULT_IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".bmp",
        ".tiff",
    }
)

_DEFAULT_VIDEO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp4",
        ".avi",
        ".mkv",
        ".mov",
        ".wmv",
    }
)

_DEFAULT_AUDIO_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".mp3",
        ".wav",
        ".flac",
        ".m4a",
        ".ogg",
    }
)


class FileRouter:
    """Routes files to the appropriate processor type based on extension.

    Uses a configurable mapping from file extensions to processor types,
    with sensible defaults for common file formats. Supports custom
    routing rules that can override extension-based routing.

    Example:
        >>> router = FileRouter()
        >>> router.route(Path("document.pdf"))
        <ProcessorType.TEXT: 'text'>
        >>> router.route(Path("photo.jpg"))
        <ProcessorType.IMAGE: 'image'>
    """

    def __init__(self) -> None:
        """Initialize the file router with default extension mappings."""
        # Build extension -> processor type mapping
        self._extension_map: dict[str, ProcessorType] = {}

        for ext in _DEFAULT_TEXT_EXTENSIONS:
            self._extension_map[ext] = ProcessorType.TEXT
        for ext in _DEFAULT_IMAGE_EXTENSIONS:
            self._extension_map[ext] = ProcessorType.IMAGE
        for ext in _DEFAULT_VIDEO_EXTENSIONS:
            self._extension_map[ext] = ProcessorType.VIDEO
        for ext in _DEFAULT_AUDIO_EXTENSIONS:
            self._extension_map[ext] = ProcessorType.AUDIO

        # Custom routing rules: list of (predicate, processor_type) pairs.
        # Evaluated in order; first match wins. Checked before extension map.
        self._custom_rules: list[tuple[Callable[[Path], bool], ProcessorType]] = []

    def route(self, file_path: Path) -> ProcessorType:
        """Determine which processor type should handle a file.

        Custom rules are checked first (in registration order), then
        extension-based mapping, then falls back to UNKNOWN.

        Args:
            file_path: Path to the file to route.

        Returns:
            The ProcessorType that should handle this file.
        """
        # Check custom rules first
        for predicate, processor_type in self._custom_rules:
            try:
                if predicate(file_path):
                    logger.debug(
                        "Custom rule matched %s -> %s",
                        file_path.name,
                        processor_type.value,
                    )
                    return processor_type
            except Exception:
                logger.exception("Error in custom routing rule for %s", file_path.name)
                continue

        # Fall back to extension-based routing
        ext = file_path.suffix.lower()
        processor_type = self._extension_map.get(ext, ProcessorType.UNKNOWN)

        logger.debug(
            "Extension routing %s (%s) -> %s",
            file_path.name,
            ext,
            processor_type.value,
        )
        return processor_type

    def add_extension(self, extension: str, processor_type: ProcessorType) -> None:
        """Register or override the processor type for a file extension.

        Args:
            extension: File extension (with or without leading dot).
            processor_type: The processor type to use for this extension.
        """
        ext = extension if extension.startswith(".") else f".{extension}"
        ext = ext.lower()
        self._extension_map[ext] = processor_type
        logger.debug("Registered extension %s -> %s", ext, processor_type.value)

    def remove_extension(self, extension: str) -> None:
        """Remove a file extension mapping.

        Args:
            extension: File extension to remove (with or without leading dot).

        Raises:
            KeyError: If the extension is not registered.
        """
        ext = extension if extension.startswith(".") else f".{extension}"
        ext = ext.lower()
        del self._extension_map[ext]

    def add_custom_rule(
        self,
        predicate: Callable[[Path], bool],
        processor_type: ProcessorType,
    ) -> None:
        """Add a custom routing rule.

        Custom rules are evaluated before extension-based routing,
        in the order they were added. The first matching rule wins.

        Args:
            predicate: A callable that accepts a Path and returns True
                if the rule applies.
            processor_type: The processor type to use when the predicate
                matches.
        """
        self._custom_rules.append((predicate, processor_type))
        logger.debug(
            "Added custom routing rule -> %s (total: %d)",
            processor_type.value,
            len(self._custom_rules),
        )

    def clear_custom_rules(self) -> None:
        """Remove all custom routing rules."""
        self._custom_rules.clear()

    def get_extension_map(self) -> dict[str, ProcessorType]:
        """Return a copy of the current extension-to-processor mapping.

        Returns:
            Dictionary mapping extensions to processor types.
        """
        return dict(self._extension_map)

    @property
    def custom_rule_count(self) -> int:
        """Return the number of registered custom routing rules."""
        return len(self._custom_rules)
