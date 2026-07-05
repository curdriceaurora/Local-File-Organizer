"""Symlink-safe ``copy2``-style file copying helpers."""

from __future__ import annotations

import errno
import os
import shutil
import stat
import sys
from pathlib import Path, PurePath
from typing import BinaryIO

from file_organizer.utils.safedir import SafeDir

# errno sets mirror shutil._copyxattr: unsupported filesystems, missing-attr
# races, and protected namespaces (e.g. security.selinux for an unprivileged
# process) are skipped rather than failing the copy -- exactly what copy2 does.
_XATTR_LIST_SKIP = frozenset({errno.ENOTSUP, errno.ENODATA, errno.EINVAL})
_XATTR_SET_SKIP = frozenset({errno.EPERM, errno.EACCES, errno.ENOTSUP, errno.ENODATA, errno.EINVAL})

# Destination open flags shared by both copy paths. WITHOUT O_TRUNC, WITH
# O_NONBLOCK where available: a destination swapped to a reader-less FIFO
# returns ENXIO immediately instead of blocking the worker; ``_finish_copy``
# validates the opened inode (S_ISREG / same-inode) before truncating.
# O_NOFOLLOW is added by ``open_child`` itself. ``_DST_OPEN_MODE`` matches
# ``open()`` (0o644 under a typical 022 umask), not os.open's 0o777 default.
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_DST_OPEN_FLAGS = os.O_WRONLY | os.O_CREAT | _O_NONBLOCK
_DST_OPEN_MODE = 0o666


def _copy_fd_xattrs(src_fd: int, dst_fd: int) -> None:
    """Best-effort copy of extended attributes between two fds (Linux)."""
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
    """Open *source* read-only with ``O_NOFOLLOW`` and return ``(handle, fstat)``."""
    with SafeDir.open_root(source.parent) as src_root:
        src_fd = src_root.open_child(source.name, flags=os.O_RDONLY | _O_NONBLOCK)
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
    """Validate the opened destination fd, then copy data + ``copy2`` metadata."""
    try:
        dst_meta = os.fstat(dst_fd)
        if not stat.S_ISREG(dst_meta.st_mode):
            raise shutil.SpecialFileError(f"`{destination}` is not a regular file")
        if (dst_meta.st_dev, dst_meta.st_ino) == (src_stat.st_dev, src_stat.st_ino):
            raise shutil.SameFileError(f"{source!r} and {destination!r} are the same file")
        os.ftruncate(dst_fd, 0)
        dst_handle = os.fdopen(dst_fd, "wb", closefd=True)
    except OSError:
        os.close(dst_fd)
        raise
    with dst_handle:
        shutil.copyfileobj(src_handle, dst_handle)
        dst_handle.flush()
        src_meta = os.fstat(src_handle.fileno())
        dst_target = dst_handle.fileno()
        os.fchmod(dst_target, stat.S_IMODE(src_meta.st_mode))
        os.utime(dst_target, ns=(src_meta.st_atime_ns, src_meta.st_mtime_ns))
        _copy_fd_xattrs(src_handle.fileno(), dst_target)


def _copy_via_safedir(source: Path, destination: Path) -> None:
    """Parent-rooted symlink-safe copy with leaf ``O_NOFOLLOW`` on both ends."""
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
    """Anchored symlink-safe copy: descend *relative* from *output_root* (POSIX)."""
    src_handle, src_stat = _open_source_nofollow(source)
    with src_handle:
        with SafeDir.open_root(output_root) as out_root:
            dst_fd = out_root.open_anchored_writer(
                relative, flags=_DST_OPEN_FLAGS, mode=_DST_OPEN_MODE
            )
        _finish_copy(src_handle, src_stat, dst_fd, source, destination)


def safe_copy2(source: Path, destination: Path, output_root: Path | None = None) -> None:
    """Copy *source* to *destination*, anchored at *output_root* when available.

    POSIX copies open both the source and destination through SafeDir so symlink
    swaps are refused while preserving ``shutil.copy2`` metadata behavior. On
    Windows, or when SafeDir is unavailable, this falls back to ``copy2``.
    """
    try:
        if sys.platform != "win32":
            if output_root is not None:
                try:
                    relative = destination.relative_to(output_root)
                except ValueError:
                    relative = None
                if relative is not None and relative.parts:
                    output_root.mkdir(parents=True, exist_ok=True)
                    anchor = output_root.resolve()
                    _copy_via_safedir_anchored(source, anchor, PurePath(relative), destination)
                    return
            destination.parent.mkdir(parents=True, exist_ok=True)
            _copy_via_safedir(source, destination)
            return
    except NotImplementedError:  # pragma: no cover - platform skip
        pass
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
