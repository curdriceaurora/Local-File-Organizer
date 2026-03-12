"""Postprocessor stage - destination path computation.

Combines the category and filename from analysis with the output
directory to produce the final destination path, handling duplicate
filenames with numeric suffixes.
"""

from __future__ import annotations

import logging
from pathlib import Path

from file_organizer.interfaces.pipeline import StageContext

logger = logging.getLogger(__name__)


class PostprocessorStage:
    """Compute the destination path for the file.

    Reads ``context.category`` and ``context.filename`` (set by the
    analyzer or preprocessor) and writes ``context.destination``.
    Appends numeric suffixes to avoid overwriting existing files.
    """

    def __init__(self, output_directory: Path) -> None:
        """Initialize with output directory for destination paths."""
        self._output_directory = output_directory

    @property
    def name(self) -> str:
        """Return stage name."""
        return "postprocessor"

    def process(self, context: StageContext) -> StageContext:
        """Build destination path, deduplicating if needed."""
        if context.failed:
            return context

        category = context.category or "uncategorized"
        filename = context.filename or context.file_path.stem
        suffix = context.file_path.suffix

        destination = self._output_directory / category / f"{filename}{suffix}"

        # Deduplicate
        final = destination
        counter = 1
        while final.exists():
            final = destination.parent / f"{filename}_{counter}{suffix}"
            counter += 1

        context.destination = final
        logger.debug("Postprocessed %s -> %s", context.file_path.name, final)
        return context
