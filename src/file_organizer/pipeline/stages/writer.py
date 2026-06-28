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
from pathlib import Path, PurePath
from typing import BinaryIO

from file_organizer.interfaces.pipeline import StageContext
from file_organizer.utils.safedir import SafeDir

logger = logging.getLogger(__name__)

# errno sets mirror shutil._copyxattr: unsupported filesystems, missing-attr
# races, and protected namespaces (e.g. security.selinux for an unprivileged
# process) are skipped rather than failing the copy — exactly what copy2 does.
_XATTR_LIST_SKIP = frozenset({errno.ENOTSUP, errno.ENODATA, errno.EINVAL})
_XATTR_SET_SKIP = frozenset({errno.EPERM, errno.EACCES, errno.ENOTSUP, errno.ENODATA, errno.EINVAL})

# Destination open flags shared by both copy paths. WITHOUT O_TRUNC, WITH
# O_NONBLOCK: a destination swapped to a reader-less FIFO returns ENXIO
# immediately instead of blocking the worker; ``_finish_copy`` validates the
# opened inode (S_ISREG / same-inode) before truncating. O_NOFOLLOW is added by
# ``open_child`` itself. ``_DST_OPEN_MODE`` matches ``open()`` (0o644 under a
# typical 022 umask), not os.open's 0o777 default.
_DST_OPEN_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_NONBLOCK
_DST_OPEN_MODE = 0o666


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


def _open_source_nofollow(source: Path) -> tuple[BinaryIO, os.stat_result]:
    """Open *source* read-only with ``O_NOFOLLOW`` and return ``(handle, fstat)``.

    The source is opened under ``SafeDir.open_root(source.parent)`` so a
    symlinked source swapped in after enumeration is refused rather than
    dereferenced into the output (#354). ``O_NONBLOCK`` ensures a source swapped
    to a FIFO (after PreprocessorStage's ``is_file()`` check) doesn't block this
    open waiting for a writer; the ``fstat`` below refuses anything that isn't a
    regular file (``O_NONBLOCK`` is a no-op for reads on regular files).

    Caller owns the returned handle and must close it (``with handle:``).

    Raises:
        SymlinkRejected: If *source* is a symlink (``OSError`` subclass).
        shutil.SpecialFileError: If *source* is not a regular file (FIFO,
            device, socket) — matching ``shutil.copy2``.
        OSError: For other open failures.
    """
    with SafeDir.open_root(source.parent) as src_root:
        src_fd = src_root.open_child(source.name, flags=os.O_RDONLY | os.O_NONBLOCK)
    try:
        src_handle: BinaryIO = os.fdopen(src_fd, "rb", closefd=True)
    except OSError:
        os.close(src_fd)
        raise
    try:
        src_stat = os.fstat(src_handle.fileno())
        if not stat.S_ISREG(src_stat.st_mode):
            raise shutil.SpecialFileError(f"`{source}` is not a regular file")
    except BaseException:
        src_handle.close()
        raise
    return src_handle, src_stat


def _finish_copy(
    src_handle: BinaryIO,
    src_stat: os.stat_result,
    dst_fd: int,
    source: Path,
    destination: Path,
) -> None:
    """Validate the opened destination fd, then copy data + ``copy2`` metadata.

    Every check runs against the inode we will actually write through (the
    already-open *dst_fd*), so there is no lstat→open TOCTOU:

    - post-open ``S_ISREG``: a special file (device/socket) is refused with
      ``SpecialFileError``, matching ``copy2``;
    - post-open same-inode: an identical path / hard link to the source raises
      ``SameFileError`` *before* truncation, so the source is never zeroed.

    Only after all checks pass is the destination ``ftruncate``-d (``copy2``
    parity for an existing regular file), then the data is streamed and the
    permission bits, access/modify times, and extended attributes are
    replicated through the open fd (no path re-lookup a swap could intercept).
    Takes ownership of *dst_fd* (closes it on failure, or via the handle).
    """
    try:
        dst_meta = os.fstat(dst_fd)
        if not stat.S_ISREG(dst_meta.st_mode):
            raise shutil.SpecialFileError(f"`{destination}` is not a regular file")
        if (dst_meta.st_dev, dst_meta.st_ino) == (src_stat.st_dev, src_stat.st_ino):
            raise shutil.SameFileError(f"{source!r} and {destination!r} are the same file")
        os.ftruncate(dst_fd, 0)
        dst_handle = os.fdopen(dst_fd, "wb", closefd=True)
    except OSError:
        # SpecialFileError / SameFileError subclass OSError, so this also
        # closes dst_fd and re-raises for those refusal paths.
        os.close(dst_fd)
        raise
    with dst_handle:
        shutil.copyfileobj(src_handle, dst_handle)
        dst_handle.flush()
        # Re-stat the source *after* the read: shutil.copy2 stats the source
        # post-copy, so on relatime mounts (where the read bumps atime) copying
        # the pre-read atime would break parity. mtime/mode are unaffected.
        src_meta = os.fstat(src_handle.fileno())
        dst_target = dst_handle.fileno()
        os.fchmod(dst_target, stat.S_IMODE(src_meta.st_mode))
        os.utime(dst_target, ns=(src_meta.st_atime_ns, src_meta.st_mtime_ns))
        # copy2 → copystat also copies extended attributes; mirror that
        # (best-effort) so user.*/SELinux metadata survives.
        _copy_fd_xattrs(src_handle.fileno(), dst_target)


def _copy_via_safedir(source: Path, destination: Path) -> None:
    """Parent-rooted symlink-safe copy — leaf ``O_NOFOLLOW`` on both ends (POSIX).

    The **destination** is opened under ``SafeDir.open_root(destination.parent)``
    with ``open_child`` (always ``O_NOFOLLOW``), so a symlink pre-planted *at*
    ``destination`` is refused with ``SymlinkRejected`` instead of followed
    (#322); an existing regular file is still truncated/overwritten (``copy2``
    parity). This is the fallback used when no trusted output root is available
    (custom pipelines); :func:`_copy_via_safedir_anchored` additionally closes
    the symlinked-*ancestor* vector (#1268) when a root is known.

    Raises:
        SymlinkRejected: If *source* or *destination* is a symlink.
        OSError: For other I/O failures.
    """
    src_handle, src_stat = _open_source_nofollow(source)
    with src_handle:
        with SafeDir.open_root(destination.parent) as dst_root:
            dst_fd = dst_root.open_child(
                destination.name, flags=_DST_OPEN_FLAGS, mode=_DST_OPEN_MODE
            )
        _finish_copy(src_handle, src_stat, dst_fd, source, destination)


def _copy_via_safedir_anchored(
    source: Path, output_root: Path, relative: PurePath, destination: Path
) -> None:
    """Anchored symlink-safe copy: descend *relative* from *output_root* (POSIX).

    Closes the symlinked-*ancestor* vector (#1268): the destination is reached
    by descending one component at a time from the trusted ``output_root`` via
    :meth:`SafeDir.open_anchored_writer` (``mkdir`` + ``open_subdir`` per step,
    each ``O_NOFOLLOW``), so a symlinked intermediate directory in the output
    tree is refused with ``SymlinkRejected`` rather than traversed. The leaf is
    opened ``O_WRONLY | O_CREAT | O_NONBLOCK`` (no ``O_TRUNC``) and validated by
    :func:`_finish_copy`, identical to the parent-rooted path.

    Raises:
        SymlinkRejected: If *source*, any ancestor under *output_root*, or the
            leaf is a symlink.
        OSError: For other I/O failures.
    """
    src_handle, src_stat = _open_source_nofollow(source)
    with src_handle:
        with SafeDir.open_root(output_root) as out_root:
            dst_fd = out_root.open_anchored_writer(
                relative, flags=_DST_OPEN_FLAGS, mode=_DST_OPEN_MODE
            )
        _finish_copy(src_handle, src_stat, dst_fd, source, destination)


def _write_destination(source: Path, destination: Path, output_root: Path | None) -> None:
    """Copy *source* to *destination*, anchored at *output_root* when available.

    When ``output_root`` is set and ``destination`` lives under it, the copy
    descends from the trusted root one component at a time, refusing a symlinked
    ancestor (#1268). Otherwise it creates the parent directory and uses the
    parent-rooted leaf-protected copy. Falls back to ``shutil.copy2`` on Windows
    or where SafeDir is unavailable (``NotImplementedError``).

    The trusted root's *own* symlinks are followed (it is the user-supplied
    output directory — the anchor we trust): it is resolved with
    ``Path.resolve()`` before ``open_root`` so a legitimately symlinked output
    directory (e.g. ``~/Organized -> /mnt/data/org``) is honoured rather than
    refused. Only the attacker-influenced segments *below* the root (the
    ``category`` / ``filename`` from analysis) are walked with ``O_NOFOLLOW``.

    A ``SymlinkRejected`` from the anchored path propagates (it is *not* retried
    via the parent-rooted fallback, which could follow the very symlink the
    anchored walk refused).
    """
    try:
        if sys.platform != "win32":
            if output_root is not None:
                # Match lexically against the (unresolved) declared root, since
                # ``destination`` was composed from it.
                try:
                    relative = destination.relative_to(output_root)
                except ValueError:
                    relative = None
                if relative is not None and relative.parts:
                    # Materialize the trusted root itself (the user-supplied
                    # output dir) so it can be resolved + anchored on. The
                    # attacker-controlled segments *below* it (category /
                    # filename) are created via O_NOFOLLOW descent inside
                    # ``open_anchored_writer``, not this mkdir.
                    output_root.mkdir(parents=True, exist_ok=True)
                    # Resolve the trusted root's own symlinks so a symlinked
                    # output directory is honoured, not rejected by open_root's
                    # final-component O_NOFOLLOW; the untrusted ``relative`` tail
                    # is still walked symlink-safe from the resolved anchor.
                    anchor = output_root.resolve()
                    _copy_via_safedir_anchored(source, anchor, PurePath(relative), destination)
                    return
            destination.parent.mkdir(parents=True, exist_ok=True)
            _copy_via_safedir(source, destination)
            return
    except NotImplementedError:  # pragma: no cover - platform skip
        pass
    # Windows / SafeDir unavailable: preserve prior behaviour.
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)  # noqa: safedir-required  # pipeline writer — source/destination are SafeDir-resolved stage paths


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
