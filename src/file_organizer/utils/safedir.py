r"""POSIX-safe directory-fd filesystem operations.

Implementation of #266 in the security hardening series (#264). The
``SafeDir`` primitive holds an open directory file descriptor and routes
every operation through ``dir_fd=`` + ``O_NOFOLLOW``. PRs 3–6 thread it
through the read-side ingestion, dedupe, undo, and watcher paths.

Design invariants:

- **Every method takes a path *component*, never a path.** Names
  containing ``/``, ``\\``, ``..``, ``.``, NUL, or empty strings are
  rejected with ``ValueError`` before any syscall. This makes
  attacker-controlled segments — file content, AI output, watcher event
  payloads — unable to escape the held directory.
- **``O_NOFOLLOW`` is always set on opens.** On Linux this raises
  ``ELOOP`` when the named entry is a symlink; we translate that to a
  typed ``SymlinkRejected`` (subclass of ``OSError``) so callers can
  catch the security-relevant case specifically while generic
  ``except OSError`` paths continue to work.
- **No path-string reconstruction.** Every syscall uses
  ``dir_fd=self.fd`` with the bare component. There is no code path
  that builds ``str(self.path) + "/" + name`` and hands it to a syscall.
- **fd lifetime is via context manager only.** The ``__exit__`` releases
  the held fd; double-exit is harmless. The class deliberately does not
  expose a public ``close()`` to discourage leak-prone usage patterns.

Platform: POSIX only. Windows has no equivalent for ``dir_fd=`` /
``O_NOFOLLOW``; ``open_root`` raises ``NotImplementedError`` there. PR
CI is Linux; nightly Windows runs skip the dependent test modules. See
#264 for the deferral rationale.
"""

from __future__ import annotations

import contextlib
import errno
import os
import sys
from collections.abc import Iterator
from pathlib import Path, PurePath
from types import TracebackType
from typing import Self

__all__ = ["SafeDir", "SymlinkRejected"]


_INVALID_NAME_CHARS = frozenset({"/", "\\", "\x00"})
_RESERVED_NAMES = frozenset({"", ".", ".."})

# ``O_PATH`` (Linux 2.6.39+) has a surprising interaction with ``O_NOFOLLOW``:
# instead of refusing to dereference a symlink, the pair returns an fd
# referring to the symlink itself. That breaks the documented contract of
# ``open_child`` ("if the entry is a symlink, raises SymlinkRejected") — any
# caller that later uses the resulting fd for an inode-pinning or existence
# check would silently operate on the symlink. Reject the flag at the API
# boundary; if a future caller genuinely needs ``O_PATH`` semantics, ship
# a dedicated method that handles the post-open ``fstat(S_ISLNK)`` check.
# On platforms that don't define ``O_PATH`` (macOS, BSD), the bug doesn't
# exist; the guard falls through harmlessly via the ``getattr`` default.
_O_PATH = getattr(os, "O_PATH", 0)


class SymlinkRejected(OSError):
    """Raised when a SafeDir operation refuses to dereference a symlink.

    Subclasses ``OSError`` so existing ``except OSError`` paths continue
    to work while security-relevant callers can catch this specifically.
    The original ``OSError`` (``errno=ELOOP``) is wrapped, not replaced —
    ``__cause__`` / ``__context__`` carry the underlying error.
    """


def _validate_name(name: str) -> None:
    r"""Reject anything that isn't a single safe path component.

    Raises ``ValueError`` for any of:

    - Reserved (``""``, ``"."``, ``".."``).
    - Contains path-separator characters (``/`` on POSIX, plus ``\\``
      defensively — even on POSIX, ``\\`` in a filename is unusual and
      catching it here matches the Windows-portable invariant if/when
      ``SafeDir`` ships on Windows).
    - Contains NUL.

    This runs *before* any syscall so traversal payloads never reach the
    kernel.
    """
    if not isinstance(name, str):
        raise ValueError(f"name must be str, got {type(name).__name__}")
    if name in _RESERVED_NAMES:
        raise ValueError(f"reserved component name: {name!r}")
    for ch in name:
        if ch in _INVALID_NAME_CHARS:
            raise ValueError(f"name contains forbidden character {ch!r}: {name!r}")


def _wrap_open_errno(err: OSError, name: str) -> OSError:
    """Translate symlink-related open failures into ``SymlinkRejected``.

    On Linux, ``os.open(path, O_DIRECTORY | O_NOFOLLOW)`` against a
    symlink-to-directory returns ``ENOTDIR`` (because the symlink inode
    itself isn't a directory) rather than ``ELOOP``. On a regular-file
    target with ``O_NOFOLLOW`` you get ``ELOOP``. Callers can't tell
    these apart from the errno alone, so we map both through this
    helper. Non-symlink causes (``ENOTDIR`` against a regular file when
    ``O_DIRECTORY`` was set) are passed through unchanged.

    Disambiguation requires an extra ``lstat`` — see
    ``_check_symlink_under`` below.
    """
    if err.errno == errno.ELOOP:
        wrapped = SymlinkRejected(
            err.errno,
            f"refused to open symlinked entry: {name!r}",
            err.filename,
        )
        wrapped.__cause__ = err
        return wrapped
    return err


def _raise_symlink_rejected(name: str, cause: OSError) -> None:
    """Raise ``SymlinkRejected`` chained to *cause*."""
    wrapped = SymlinkRejected(
        cause.errno,
        f"refused to open symlinked entry: {name!r}",
        cause.filename,
    )
    wrapped.__cause__ = cause
    raise wrapped


def _is_symlink_at(name: str, dir_fd: int) -> bool:
    """True if *name* under *dir_fd* is a symlink, False otherwise.

    Used after an open fails to disambiguate ``ENOTDIR``-on-symlink from
    ``ENOTDIR``-on-regular-file. Returns False on any stat failure (the
    entry vanished, permissions changed, etc.) — the caller will then
    re-raise the original open error, which is the correct behavior:
    the open didn't follow a symlink, so we don't owe a
    ``SymlinkRejected``.
    """
    try:
        st = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
    except OSError:
        return False
    import stat as _stat

    return _stat.S_ISLNK(st.st_mode)


class SafeDir:
    """Holds an open directory fd; every operation uses ``dir_fd=`` + ``O_NOFOLLOW``.

    Construct via ``SafeDir.open_root(path)`` — direct construction is
    not part of the public API. Always use as a context manager so the
    fd is released:

        with SafeDir.open_root(organize_root) as sd:
            with sd.open_subdir("documents") as sub:
                for entry in sub.scandir():
                    ...
    """

    __slots__ = ("_fd", "_closed")

    def __init__(self, fd: int) -> None:
        """Wrap an already-open directory fd.

        Internal — public construction goes through ``open_root``;
        ``open_subdir`` uses this directly to wrap the fd it has just
        opened. The constructor does not validate that *fd* is a
        directory fd; callers must.
        """
        self._fd = fd
        self._closed = False

    # ------------------------------------------------------------------
    # Construction & lifecycle
    # ------------------------------------------------------------------

    @classmethod
    def open_root(cls, path: str | os.PathLike[str]) -> Self:
        """Open *path* as the root of a SafeDir.

        *path* is the only place a multi-component path enters this API —
        every subsequent operation must use single component names.
        Accepts ``str`` and ``os.PathLike`` (including ``pathlib.Path``);
        the value is normalized to ``Path`` at the entry boundary.

        Raises:
            NotImplementedError: On Windows. ``dir_fd=`` and
                ``O_NOFOLLOW`` are POSIX-only; the Windows port is
                deferred (see #264).
            SymlinkRejected: If *path* itself is a symlink. The caller
                must hand a real directory; we don't follow whatever it
                might point at.
            OSError: If *path* doesn't exist, isn't a directory, or
                can't be opened.
        """
        if sys.platform == "win32":  # pragma: no cover - platform skip
            raise NotImplementedError(
                "SafeDir requires POSIX dir_fd / O_NOFOLLOW support; Windows port deferred (#264)"
            )
        # Normalize at the boundary so str/PathLike callers (CLI args,
        # un-typed config values) don't trip on ``path.is_symlink()`` below
        # with AttributeError instead of the documented SymlinkRejected /
        # OSError. The conversion is idempotent for an existing Path.
        path = Path(path)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            fd = os.open(str(path), flags)
        except OSError as exc:
            # ``O_DIRECTORY | O_NOFOLLOW`` against a symlink-to-dir returns
            # ENOTDIR on Linux (the symlink inode isn't a directory).
            # Disambiguate via lstat — symlink → SymlinkRejected, anything
            # else → propagate.
            if exc.errno == errno.ELOOP or (exc.errno == errno.ENOTDIR and path.is_symlink()):
                _raise_symlink_rejected(str(path), exc)
            raise _wrap_open_errno(exc, str(path)) from exc
        return cls(fd)

    @property
    def fd(self) -> int:
        """Underlying directory fd (read-only, intended for diagnostics).

        Callers should *not* perform syscalls on this fd directly — use
        the methods on this class instead, which keep the
        ``dir_fd=`` + ``O_NOFOLLOW`` invariant.

        Raises ``ValueError`` if the SafeDir has been closed: the
        stored fd would be -1, and reading it would invite the caller
        into operating on whatever (unrelated) directory POSIX
        eventually recycles the original fd number for.
        """
        self._check_open()
        return self._fd

    def _check_open(self) -> None:
        """Raise ``ValueError`` if this SafeDir has already been closed.

        POSIX fd numbers are recycled — if a caller retains a
        ``SafeDir`` past its ``__exit__`` and then invokes a method on
        it, the underlying ``dir_fd=`` would address whatever
        directory the kernel reassigned the fd to (any subsequent
        ``os.open``, including unrelated ones inside the same process).
        That's a silent correctness bug: ``scandir`` / ``unlink`` /
        ``rename_into`` would operate on the wrong directory rather
        than failing with ``EBADF``. Every public method calls this
        first so the failure is loud and immediate.
        """
        if self._closed:
            raise ValueError("SafeDir has been closed; cannot use after context-manager exit")

    def __enter__(self) -> Self:
        """Enter the context manager; return *self* unchanged."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Release the held directory fd. Idempotent on double-exit.

        Closing an already-closed fd would raise ``EBADF``, which is
        noise in failure-path teardown; suppress it.
        """
        if self._closed:
            return
        self._closed = True
        fd_to_close = self._fd
        # Invalidate the stored fd so accidental late access via
        # ``self._fd`` can't reach a recycled directory. Even if
        # ``_check_open`` is bypassed (e.g. via direct attribute access),
        # a syscall using -1 fails immediately with ``EBADF``.
        self._fd = -1
        try:
            os.close(fd_to_close)
        except OSError:  # pragma: no cover - defensive
            pass

    # ------------------------------------------------------------------
    # Open: file / subdirectory / reader-fd
    # ------------------------------------------------------------------

    def open_child(self, name: str, *, flags: int = os.O_RDONLY, mode: int = 0o666) -> int:
        """Open the entry *name* under this directory.

        Always sets ``O_NOFOLLOW``; if the entry is a symlink, raises
        ``SymlinkRejected``. *flags* is OR-ed in on top so callers can
        request e.g. ``os.O_WRONLY | os.O_CREAT`` for non-create
        operations (the SafeDir invariant still holds: the open is
        anchored to ``self.fd`` and never follows a symlink).

        *mode* is the file permission mode for newly created files (only
        consulted when ``O_CREAT`` is in *flags*). Defaults to
        ``0o666`` — matching the high-level ``open()`` builtin so files
        end up at ``0o644`` under the typical ``022`` umask, NOT
        ``0o755`` (which the lower-level ``os.open`` would produce with
        its surprising ``0o777`` default). Callers needing private
        files can pass ``mode=0o600`` explicitly.

        ``os.O_PATH`` is rejected — on Linux it changes ``O_NOFOLLOW``
        semantics so the symlink itself is opened rather than refused
        (see the ``_O_PATH`` module-level note). Callers that need
        ``O_PATH`` should add a dedicated method that handles the
        post-open ``S_ISLNK`` check.

        Three errno cases shadow the documented "symlink →
        SymlinkRejected" contract because their flag combinations fire
        before the ``O_NOFOLLOW`` path:

        - ``EEXIST`` from ``O_CREAT | O_EXCL`` against an existing
          symlink — the kernel reports "name taken" before honouring
          O_NOFOLLOW.
        - ``ENOTDIR`` from ``O_DIRECTORY`` against a symlink — the
          symlink inode itself isn't a directory.
        - ``ELOOP`` — the direct rejection path for the simple
          ``O_RDONLY | O_NOFOLLOW`` case.

        All three are disambiguated via ``lstat``: if the entry is a
        symlink, raise ``SymlinkRejected``; otherwise propagate the
        original error (legitimate "already exists" / "wrong type" cases
        on non-symlinks). Same pattern as ``open_subdir`` and
        ``open_root``.

        Returns the opened fd. Caller is responsible for closing it
        (use ``os.fdopen`` / ``os.close`` / ``contextlib.closing``).
        """
        self._check_open()
        _validate_name(name)
        if _O_PATH and (flags & _O_PATH):
            raise ValueError(
                "open_child does not support O_PATH: O_PATH|O_NOFOLLOW "
                "would return an fd for the symlink instead of refusing it"
            )
        try:
            return os.open(name, flags | os.O_NOFOLLOW, mode=mode, dir_fd=self._fd)
        except OSError as exc:
            # ELOOP is the direct symlink-rejection path. EEXIST shadows
            # it under O_CREAT|O_EXCL; ENOTDIR shadows it under
            # O_DIRECTORY. Disambiguate via lstat. Tolerating the
            # one-syscall TOCTOU between failed open and lstat is fine:
            # the open already didn't follow a symlink, and a same-name
            # swap-in just means the entry IS now a symlink, which is
            # still the security-relevant case.
            shadowed_by_symlink = exc.errno in (
                errno.EEXIST,
                errno.ENOTDIR,
            ) and _is_symlink_at(name, self._fd)
            if exc.errno == errno.ELOOP or shadowed_by_symlink:
                _raise_symlink_rejected(name, exc)
            raise _wrap_open_errno(exc, name) from exc

    def open_for_reader(self, name: str) -> int:
        """Open *name* read-only with ``O_NOFOLLOW`` and return its fd.

        The canonical 'pass to a content reader' helper. Wrap with
        ``os.fdopen(fd, "rb")`` and hand to ``fitz.open(stream=...)`` /
        ``Image.open(...)`` / ``pypdf.PdfReader(...)`` / etc.

        Raises:
            ValueError: If *name* isn't a safe component.
            SymlinkRejected: If *name* is a symlink.
            FileNotFoundError: If *name* doesn't exist.
            OSError: For other open failures (permission, etc.).
        """
        return self.open_child(name, flags=os.O_RDONLY)

    def open_subdir(self, name: str) -> SafeDir:
        """Open subdirectory *name* and return a new SafeDir wrapping its fd.

        Use as a context manager so the new fd is released:

            with sd.open_subdir("category") as sub:
                ...
        """
        self._check_open()
        _validate_name(name)
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        try:
            fd = os.open(name, flags, dir_fd=self._fd)
        except OSError as exc:
            # ENOTDIR can mean "the entry is a symlink (whose own inode
            # isn't a directory)" or "the entry is a regular file".
            # ``_is_symlink_at`` resolves the ambiguity.
            if exc.errno == errno.ELOOP or (
                exc.errno == errno.ENOTDIR and _is_symlink_at(name, self._fd)
            ):
                _raise_symlink_rejected(name, exc)
            raise _wrap_open_errno(exc, name) from exc
        return SafeDir(fd)

    def open_anchored_reader(self, relative_path: str | os.PathLike[str]) -> int:
        """Walk *relative_path* from this SafeDir and open the leaf as a reader fd.

        Each intermediate component is opened via :meth:`open_subdir` (which
        uses ``O_NOFOLLOW``), and the leaf is opened via
        :meth:`open_for_reader`. An attacker-controlled ancestor swapped to
        a symlink between directory enumeration and this read is refused with
        :class:`SymlinkRejected`, not dereferenced — closes the nested-
        ancestor TOCTOU window (#286) that the parent-rooted pattern leaves
        open.

        Args:
            relative_path: A relative path under this SafeDir. Must not be
                absolute and must not contain ``..`` components. May be a
                ``str`` or any ``os.PathLike`` (typically ``PurePath`` /
                ``Path``).

        Returns:
            The reader file descriptor for the leaf. Caller owns lifetime —
            wrap with ``os.fdopen(fd, "rb", closefd=True)`` and close on
            ``fdopen`` failure (``os.close(fd)``). The intermediate subdir
            fds opened during traversal are released before this returns.

        Raises:
            ValueError: If *relative_path* is absolute, contains ``..``, is
                empty, or any component fails :func:`_validate_name`.
            SymlinkRejected: If any component (intermediate or leaf) is a
                symlink at open time.
            OSError: For other open failures (permission denied, missing
                component, etc.).
        """
        self._check_open()
        rel = PurePath(relative_path) if not isinstance(relative_path, PurePath) else relative_path
        if rel.is_absolute():
            raise ValueError(f"open_anchored_reader requires a relative path, got absolute {rel!r}")
        parts = rel.parts
        if not parts:
            raise ValueError("open_anchored_reader requires a non-empty relative path")
        if any(part == ".." for part in parts):
            raise ValueError(f"open_anchored_reader refuses '..' components in {rel!r}")
        # Walk intermediates inside an ExitStack so any subdir fd is closed
        # exactly once even if a later component raises. The leaf fd is
        # handed back open — caller owns its lifetime (see Returns above).
        with contextlib.ExitStack() as stack:
            current = self
            for component in parts[:-1]:
                current = stack.enter_context(current.open_subdir(component))
            return current.open_for_reader(parts[-1])

    # ------------------------------------------------------------------
    # Inspect / list / stat
    # ------------------------------------------------------------------

    def scandir(self) -> Iterator[str]:
        """Yield names (``str``) of non-symlink entries in this directory.

        **Returns plain names, not ``os.DirEntry`` objects.** Exposing
        ``DirEntry`` would let callers reach ``entry.is_file()``,
        ``entry.is_dir()``, and ``entry.stat()`` — all of which default
        to ``follow_symlinks=True``. Even after filtering symlinks at
        scan time, a TOCTOU swap (regular file → symlink) between
        ``is_symlink()`` and a downstream ``entry.stat()`` would let
        the caller classify or stat the attacker's target. Returning
        only the name keeps that footgun out of reach: any subsequent
        operation must route through SafeDir's own methods, which all
        enforce ``follow_symlinks=False`` / ``O_NOFOLLOW``.

        Callers needing type/metadata for a yielded name should call
        ``self.lstat(name)`` and inspect ``S_ISREG`` / ``S_ISDIR`` etc.
        explicitly. Reads use ``self.open_for_reader(name)``;
        subdirectories use ``self.open_subdir(name)``. Both are
        symlink-safe under SafeDir's invariants.

        Symlinks present at scan time are filtered out via the cached
        ``DirEntry.is_symlink()``. The check uses ``readdir``-cached
        ``d_type`` rather than a fresh ``lstat``, so a *post*-scan
        swap-in could still yield a name that has since become a
        symlink — but that's the caller's atomic check via
        ``lstat`` / ``open_for_reader`` to handle correctly, and
        SafeDir's other operations already refuse symlinks.

        The underlying ``os.scandir(self.fd)`` reads the directory by
        file descriptor (no path-string lookup that could be
        intercepted). **Names are materialized eagerly** rather than
        yielded lazily: ``os.scandir(fd)`` internally ``dup``-s the fd,
        so the ``ScandirIterator`` has its own handle that would
        survive ``SafeDir.__exit__``. A lazy generator could keep
        yielding names after the context closed — violating the
        lifecycle guarantee that operations are bounded by the
        ``with`` block. Eager materialization also ensures the
        ``ScandirIterator`` is closed before this method returns, so
        the dup'd fd doesn't leak.

        For typical SafeDir trees (a user's organize root) directory
        sizes are bounded by ``safe_walk``-style enumeration limits;
        materializing N names of average length ~50 bytes costs N×50
        bytes which is negligible up to ~100K entries.
        """
        self._check_open()
        names: list[str] = []
        with os.scandir(self._fd) as it:
            for entry in it:
                try:
                    if entry.is_symlink():
                        continue
                except OSError:
                    # Per-entry stat failure (race with deletion,
                    # permission flip, etc.) — skip defensively. Matches
                    # safe_walk's stance.
                    continue
                names.append(entry.name)
        return iter(names)

    def lstat(self, name: str) -> os.stat_result:
        """Stat *name* without following symlinks (``lstat`` semantics).

        Useful for inode-pinning workflows (PR4 / PR5): capture
        ``(st_dev, st_ino, st_size)`` here, then re-call before any
        destructive operation and refuse on mismatch.
        """
        self._check_open()
        _validate_name(name)
        return os.stat(name, dir_fd=self._fd, follow_symlinks=False)

    # ------------------------------------------------------------------
    # Mutate: create / remove / rename
    # ------------------------------------------------------------------

    def mkdir(self, name: str, mode: int = 0o755) -> None:
        """Create a subdirectory *name* relative to this dir's fd.

        The created directory is *not* opened or returned; call
        ``open_subdir(name)`` afterwards if you need to operate on it.
        Separating create from open lets the caller decide whether to
        re-stat or use ``O_DIRECTORY | O_NOFOLLOW`` semantics on the
        follow-up open.
        """
        self._check_open()
        _validate_name(name)
        os.mkdir(name, mode=mode, dir_fd=self._fd)

    def unlink(self, name: str) -> None:
        """Remove a file (not a directory) *name* relative to this dir's fd.

        Uses ``os.unlink`` with ``dir_fd=`` so the unlink target is
        resolved through the held directory — not via a path string
        that could be intercepted.
        """
        self._check_open()
        _validate_name(name)
        os.unlink(name, dir_fd=self._fd)

    def rename_into(self, name: str, other: SafeDir, other_name: str) -> None:
        """Rename ``self/name`` to ``other/other_name`` atomically.

        Uses ``os.rename(name, other_name, src_dir_fd=self.fd,
        dst_dir_fd=other.fd)`` — atomic on POSIX within the same
        filesystem. Both component names are validated.

        **Source is lstat'd before rename and a symlink raises
        ``SymlinkRejected``.** ``os.rename`` has no ``O_NOFOLLOW``
        equivalent — if a caller enumerates via ``scandir`` (which
        filters symlinks) and then a TOCTOU attacker swaps ``name``
        for a symlink before the rename, the symlink would be moved
        into the managed destination, contaminating the trusted output
        tree with a pointer outside the SafeDir root. The lstat check
        narrows that window from "scan-to-rename" (caller-dependent
        duration) down to "lstat-to-rename" (~one syscall) — the
        residual race is acknowledged and acceptable given the kernel
        offers no atomic alternative.

        Caller is responsible for ensuring ``other`` is on the same
        filesystem; cross-filesystem renames will raise ``OSError``
        (``EXDEV``) and the caller must fall back to copy + unlink (see
        ``undo/durable_move.py`` for the existing pattern).
        """
        self._check_open()
        other._check_open()
        _validate_name(name)
        _validate_name(other_name)
        if _is_symlink_at(name, self._fd):
            cause = OSError(errno.ELOOP, "refused to rename a symlinked source")
            _raise_symlink_rejected(name, cause)
        os.rename(name, other_name, src_dir_fd=self._fd, dst_dir_fd=other._fd)
