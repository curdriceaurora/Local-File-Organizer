"""Writer stage - file copy/move operations.

Copies the file to its computed destination.  Skipped in dry-run
mode (``context.dry_run is True``).
"""

from __future__ import annotations

import logging
from pathlib import Path

from file_organizer.interfaces.pipeline import StageContext
from file_organizer.utils.safe_copy import safe_copy2

logger = logging.getLogger(__name__)


def _write_destination(source: Path, destination: Path, output_root: Path | None) -> None:
    """Backward-compatible wrapper for the shared SafeDir copy helper."""
    safe_copy2(source, destination, output_root)


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
            destination = context.destination
            assert destination is not None
            # Symlink-safe copy: refuses a symlinked source or destination
            # (SymlinkRejected → OSError → file marked failed) so the write
            # cannot be redirected outside the output tree (#322/#354). When a
            # trusted ``output_root`` is set (postprocessor), the copy also
            # descends from it component-by-component so a symlinked *ancestor*
            # directory is refused rather than traversed (#1268).
            _write_destination(context.file_path, destination, context.output_root)
            logger.info("Copied %s -> %s", context.file_path, context.destination)
        except OSError as exc:
            logger.exception("Writer failed for %s", context.file_path)
            context.error = str(exc)

        return context
