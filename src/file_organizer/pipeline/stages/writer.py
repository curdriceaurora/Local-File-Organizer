"""Writer stage - file copy/move operations.

Copies the file to its computed destination.  Skipped in dry-run
mode (``context.dry_run is True``).
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import sys
from pathlib import Path

from file_organizer.interfaces.pipeline import StageContext
from file_organizer.utils.safedir import SafeDir

logger = logging.getLogger(__name__)


def _copy_via_safedir(source: Path, destination: Path) -> None:
    """Copy *source* to *destination*, refusing symlinks on both ends (POSIX).

    Hardened replacement for ``shutil.copy2`` on the organize write path:

    - The **destination** is opened under ``SafeDir.open_root(destination.parent)``
      with ``O_WRONLY | O_CREAT | O_TRUNC`` (``open_child`` always adds
      ``O_NOFOLLOW``). A symlink pre-planted at ``destination`` — e.g.
      ``output/Docs/report.txt -> /home/victim/.ssh/authorized_keys`` — is
      refused with ``SymlinkRejected`` instead of being followed, so the write
      cannot escape the output tree (#322). An existing *regular* file is still
      truncated and overwritten, matching ``copy2`` semantics.
    - The **source** is opened with ``O_NOFOLLOW`` too, so a symlinked source
      swapped in after enumeration is refused rather than dereferenced into the
      output (#354).
    - ``copy2``'s metadata contract (permission bits + access/modify times) is
      replicated via fd-based ``os.fchmod`` / ``os.utime`` — no path re-lookup
      that a concurrent swap could intercept.

    Falls back to ``shutil.copy2`` on Windows or where SafeDir is unavailable
    (``NotImplementedError``), preserving existing behaviour there.

    Raises:
        SymlinkRejected: If *source* or *destination* (or either parent) is a
            symlink. A subclass of ``OSError``, so the caller's
            ``except OSError`` marks the file failed rather than writing
            through the link.
        OSError: For other I/O failures.
    """
    if sys.platform == "win32":  # pragma: no cover - platform skip
        shutil.copy2(source, destination)
        return

    try:
        src_root_cm = SafeDir.open_root(source.parent)
    except NotImplementedError:  # pragma: no cover - platform skip
        shutil.copy2(source, destination)
        return

    with src_root_cm as src_root:
        src_fd = src_root.open_for_reader(source.name)
        try:
            src_handle = os.fdopen(src_fd, "rb", closefd=True)
        except OSError:
            os.close(src_fd)
            raise
        with src_handle:
            src_stat = os.fstat(src_handle.fileno())
            with SafeDir.open_root(destination.parent) as dst_root:
                # O_TRUNC overwrites an existing regular file (copy2 parity);
                # O_NOFOLLOW (added by open_child) refuses an existing symlink.
                dst_fd = dst_root.open_child(
                    destination.name,
                    flags=os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                    mode=0o666,
                )
                try:
                    dst_handle = os.fdopen(dst_fd, "wb", closefd=True)
                except OSError:
                    os.close(dst_fd)
                    raise
                with dst_handle:
                    shutil.copyfileobj(src_handle, dst_handle)
                    dst_handle.flush()
                    # Replicate copy2's mode + times through the open fd so a
                    # concurrent path swap can't redirect the metadata ops.
                    dst_target = dst_handle.fileno()
                    os.fchmod(dst_target, stat.S_IMODE(src_stat.st_mode))
                    os.utime(
                        dst_target,
                        ns=(src_stat.st_atime_ns, src_stat.st_mtime_ns),
                    )


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
            destination.parent.mkdir(parents=True, exist_ok=True)
            # Symlink-safe copy: refuses a symlinked source or destination
            # (SymlinkRejected → OSError → file marked failed) so the write
            # cannot be redirected outside the output tree (#322/#354).
            _copy_via_safedir(context.file_path, destination)
            logger.info("Copied %s -> %s", context.file_path, context.destination)
        except OSError as exc:
            logger.exception("Writer failed for %s", context.file_path)
            context.error = str(exc)

        return context
