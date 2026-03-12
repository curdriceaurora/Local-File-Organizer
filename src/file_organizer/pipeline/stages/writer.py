"""Writer stage - file copy/move operations.

Copies the file to its computed destination.  Skipped in dry-run
mode (``context.dry_run is True``).
"""

from __future__ import annotations

import logging
import shutil

from file_organizer.interfaces.pipeline import StageContext

logger = logging.getLogger(__name__)


class WriterStage:
    """Copy or move the file to its destination.

    In dry-run mode the stage records what *would* happen but
    does not touch the filesystem.
    """

    @property
    def name(self) -> str:
        """Return stage name."""
        return "writer"

    def process(self, context: StageContext) -> StageContext:
        """Copy the file to ``context.destination``."""
        if context.failed:
            return context

        if context.destination is None:
            context.error = "No destination set (postprocessor stage missing?)"
            return context

        if context.dry_run:
            logger.info(
                "[DRY RUN] Would copy %s -> %s",
                context.file_path,
                context.destination,
            )
            return context

        try:
            context.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(context.file_path, context.destination)
            logger.info("Copied %s -> %s", context.file_path, context.destination)
        except Exception as exc:
            logger.exception("Writer failed for %s", context.file_path)
            context.error = str(exc)

        return context
