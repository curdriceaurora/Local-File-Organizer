"""Writer stage - file copy/move operations.

Copies the file to its computed destination.  Skipped in dry-run
mode (``context.dry_run is True``).
"""

from __future__ import annotations

import errno
import logging
import os
import shutil
import stat
import sys
from pathlib import Path

from file_organizer.interfaces.pipeline import StageContext
from file_organizer.utils.safedir import SafeDir

logger = logging.getLogger(__name__)

# errno sets mirror shutil._copyxattr: unsupported filesystems, missing-attr
# races, and protected namespaces (e.g. security.selinux for an unprivileged
# process) are skipped rather than failing the copy — exactly what copy2 does.
_XATTR_LIST_SKIP = frozenset({errno.ENOTSUP, errno.ENODATA, errno.EINVAL})
_XATTR_SET_SKIP = frozenset({errno.EPERM, errno.EACCES, errno.ENOTSUP, errno.ENODATA, errno.EINVAL})


def _copy_fd_xattrs(src_fd: int, dst_fd: int) -> None:
    """Best-effort copy of extended attributes between two fds (Linux).

    Mirrors ``shutil.copystat``'s xattr handling so ``user.*`` tags, SELinux
    labels, etc. survive the organize copy. Unsupported filesystems and
    protected namespaces are swallowed (the same errnos ``copy2`` ignores).
    A no-op where ``os.listxattr`` is unavailable (non-Linux).
    """
    if not hasattr(os, "listxattr"):
        return
    try:
        names = os.listxattr(src_fd)
    except OSError as exc:
        if exc.errno not in _XATTR_LIST_SKIP:
            raise
        return
    for name in names:
        try:
            os.setxattr(dst_fd, name, os.getxattr(src_fd, name))
        except OSError as exc:
            if exc.errno not in _XATTR_SET_SKIP:
                raise


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
        # O_NONBLOCK so a source swapped to a FIFO (after PreprocessorStage's
        # is_file() check) doesn't block this open waiting for a writer; we
        # fstat below and refuse anything that isn't a regular file. O_NONBLOCK
        # is a no-op for reads on regular files.
        src_fd = src_root.open_child(source.name, flags=os.O_RDONLY | os.O_NONBLOCK)
        try:
            src_handle = os.fdopen(src_fd, "rb", closefd=True)
        except OSError:
            os.close(src_fd)
            raise
        with src_handle:
            src_stat = os.fstat(src_handle.fileno())
            # Refuse non-regular sources (FIFO, device, socket): shutil.copy2
            # raised SpecialFileError rather than streaming them. (OSError
            # subclass → file marked failed.)
            if not stat.S_ISREG(src_stat.st_mode):
                raise shutil.SpecialFileError(f"`{source}` is not a regular file")
            with SafeDir.open_root(destination.parent) as dst_root:
                # Open the destination WITHOUT O_TRUNC and WITH O_NONBLOCK, then
                # validate the opened fd — every check runs against the inode we
                # will actually write through, so there is no lstat→open TOCTOU:
                #   * O_NONBLOCK: a destination swapped to a reader-less FIFO
                #     returns ENXIO immediately instead of blocking the worker.
                #   * O_NOFOLLOW (added by open_child): a symlinked destination
                #     is refused (SymlinkRejected).
                #   * post-open S_ISREG: any other special file (device/socket)
                #     is refused with SpecialFileError, matching copy2.
                #   * post-open same-inode: identical path / hard link to the
                #     source raises SameFileError *before* truncation, so the
                #     source is never zeroed.
                # Only after all checks pass do we ftruncate for copy2 parity.
                dst_fd = dst_root.open_child(
                    destination.name,
                    flags=os.O_WRONLY | os.O_CREAT | os.O_NONBLOCK,
                    mode=0o666,
                )
                try:
                    dst_meta = os.fstat(dst_fd)
                    if not stat.S_ISREG(dst_meta.st_mode):
                        raise shutil.SpecialFileError(f"`{destination}` is not a regular file")
                    if (dst_meta.st_dev, dst_meta.st_ino) == (
                        src_stat.st_dev,
                        src_stat.st_ino,
                    ):
                        raise shutil.SameFileError(
                            f"{source!r} and {destination!r} are the same file"
                        )
                    os.ftruncate(dst_fd, 0)
                    dst_handle = os.fdopen(dst_fd, "wb", closefd=True)
                except OSError:
                    os.close(dst_fd)
                    raise
                with dst_handle:
                    shutil.copyfileobj(src_handle, dst_handle)
                    dst_handle.flush()
                    # Re-stat the source *after* the read: shutil.copy2 stats
                    # the source post-copy, so on relatime mounts (where the
                    # read bumps atime) copying the pre-read atime would break
                    # parity. mtime/mode are unaffected by the read.
                    src_meta = os.fstat(src_handle.fileno())
                    # Replicate copy2's mode + times through the open fd so a
                    # concurrent path swap can't redirect the metadata ops.
                    dst_target = dst_handle.fileno()
                    os.fchmod(dst_target, stat.S_IMODE(src_meta.st_mode))
                    os.utime(
                        dst_target,
                        ns=(src_meta.st_atime_ns, src_meta.st_mtime_ns),
                    )
                    # copy2 → copystat also copies extended attributes; mirror
                    # that (best-effort) so user.*/SELinux metadata survives.
                    _copy_fd_xattrs(src_handle.fileno(), dst_target)


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
