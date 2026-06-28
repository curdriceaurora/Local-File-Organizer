"""Durable move helper for undo rollback operations.

F7 (hardening roadmap #159) — replacement for ``shutil.move`` in the
rollback path.

Contract
--------

:func:`durable_move` is:

- **Atomic on same device**: uses ``os.replace`` which is a single
  rename syscall; POSIX and Windows both guarantee either the old
  name or the new name is visible, never both + neither.
- **Durable + idempotent on cross-device (EXDEV)**: writes a journal
  entry before the copy starts, fsyncs the destination data +
  directory before marking the entry as copied, then unlinks the
  source and marks the entry as done. A crash anywhere in the
  sequence leaves the journal in a recoverable state — either the
  destination doesn't exist yet (safe to retry) or it's complete
  (just need to unlink the source).

:func:`sweep` runs at CLI startup and walks the journal to complete
or roll back any unfinished operations. Without the sweep, a crash
mid-move would leave ``.journal`` entries and possibly orphan files
on disk; with it, the invariant is "after startup, no journal
entries exist that refer to files that require action."

"Atomic" is a strong word. This helper is NOT atomic across EXDEV —
there's a window between ``os.replace`` of the copy and ``unlink``
of the source during which both files exist on disk. The journal +
sweep make that window observable and recoverable, not invisible.

Journal format
--------------

JSON lines, one operation per line. Fields:

- ``op`` — always ``"move"`` in this helper. Reserved for future
  operations (``copy``, ``symlink``, etc.) that might share the
  journal.
- ``src``, ``dst`` — absolute paths as strings.
- ``state`` — one of ``"started"``, ``"copied"``, ``"done"``.

States progress monotonically. An entry may appear multiple times
in the journal if it was updated (we append rather than rewrite for
crash safety — the sweep reads the LAST state for each (src, dst)
pair). The sweep truncates the journal once it finishes, so
steady-state size is bounded.

Cross-module consumers of underscore-prefixed helpers
-----------------------------------------------------

The leading underscore on ``_HAS_FCNTL``, ``_locked``,
``_path_in_flight_from_entries``, and ``_read_journal`` signals
*module-private*, but :class:`undo.trash_gc.TrashGC` is an authorized
consumer of all four (CodeRabbit lgMd). The contract:

- ``_locked`` / ``_HAS_FCNTL`` — TrashGC reuses the lock-file
  coordination so its ``LOCK_EX`` mutually-excludes with this
  module's writers. Renaming or relocating these MUST update TrashGC
  in the same change.
- ``_read_journal`` + ``_path_in_flight_from_entries`` — TrashGC
  reads + checks under its already-held ``LOCK_EX`` (the public
  ``is_path_in_flight`` would deadlock on its own LOCK_SH). The
  predicate's collapse rule (§3.1 operation identity) is canonical
  for both this module's ``is_path_in_flight`` and TrashGC's
  ``safe_delete`` — any bug fix must mirror to both call sites.

Promoting the four to a non-underscored API (e.g. into a shared
``undo._journal_lock`` module) is documented future work; today
the underscore-private + cross-module-consumer pattern is the
agreed contract.
"""

from __future__ import annotations

import contextlib
import errno
import hashlib
import json
import logging
import os
import shutil
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from file_organizer.utils.atomic_io import fsync_directory
from file_organizer.utils.atomic_write import append_durable, atomic_write_with

# F9 top-level optional import: ``fcntl`` is POSIX-only. Wrapped in a
# try/except so the module imports cleanly on Windows; functions that
# actually need flock check ``_HAS_FCNTL`` and fall back to the unlocked
# path with the single-CLI-invocation invariant from the module docstring.
try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]
    _HAS_FCNTL = False

logger = logging.getLogger(__name__)

# PR5b / #269: type alias for the inode-identity triple returned by
# durable_move after a successful move on POSIX.  ``None`` on Windows
# (no O_NOFOLLOW / lstat inode semantics) or on any stat failure.
DstInode = tuple[int, int, int]  # (st_dev, st_ino, st_size)

# Heterogeneous collapse-identity tuple. Three shapes per §3.1:
# ``("v2", op, op_id)`` / ``("v1", op, src, dst)`` / ``("unknown", op, _hash16)``.
# ``tuple[object, ...]`` captures the variability without losing strictness.
_OpIdentity = tuple[object, ...]


# Journal state constants. Exposed so callers (and tests) can assert
# against them without stringly-typed literals.
STATE_STARTED = "started"
STATE_COPIED = "copied"
STATE_DONE = "done"

# Journal op constants. ``move`` is the F7 atomic/durable single-file
# helper. ``dir_move`` (round-10 / coderabbit r3140-class) is the
# non-atomic shutil.move-based helper for directories — sweep cannot
# recover from a crash here, but the journal entry exists so concurrent
# :func:`is_path_in_flight` callers (F8 trash GC) see the directory as
# in-flight during the move.
OP_MOVE = "move"
OP_DIR_MOVE = "dir_move"
_KNOWN_OPS = frozenset({OP_MOVE, OP_DIR_MOVE})


_MAX_JOURNAL_LINE_BYTES = 64 * 1024
"""§4.1 rule 7: cap on a single journal line in bytes. Lines above this are
rejected at parse time to prevent pathological payload-size attacks. 64 KiB
leaves ample headroom above realistic path lengths plus the v2 envelope."""


def _hash16(raw: str) -> str:
    """Return the first 16 hex chars of ``sha256(raw)``.

    §3.1 rule 4: used for unknown-op collapse-key identity so semantically-
    distinct future records don't silently conflate when collapsed by this
    binary's v2 parser (which doesn't understand their additional fields).
    16 hex = 64 bits of identity — ample for the per-journal record counts
    the protocol expects (≤ dozens).
    """
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _capture_dst_inode(dst: Path) -> DstInode | None:
    """Lstat *dst* and return its inode identity triple.

    Called immediately after the atomic rename / ``os.replace`` so the
    caller can store ``(st_dev, st_ino, st_size)`` in the history record.
    Using ``lstat`` (not ``stat``) is deliberate: if ``dst`` is a symlink
    (``durable_move`` supports symlink moves), we want the symlink inode,
    not the target.

    Returns ``None`` on Windows or if ``lstat`` fails (caller treats as
    a legacy row — size+hash fallback at undo time).
    """
    if sys.platform == "win32":  # pragma: no cover - Windows
        return None
    try:
        st = os.lstat(dst)
        return st.st_dev, st.st_ino, st.st_size
    except OSError:
        logger.debug("durable_move: lstat failed on %s; cannot capture dst inode", dst)
        return None


@dataclass(frozen=True)
class _JournalEntry:
    """A parsed journal row.

    F7.1 schema v2:

    - ``schema``: 1 for legacy PR #197 records (no ``schema`` field on disk),
      2 for records this binary writes. Writers always emit 2; parsers accept
      both for back-compat.
    - ``op_id``: unique per-invocation UUID (v2 only). ``None`` on v1 records.
      v2 known-op records MUST carry ``op_id`` — parse-time rejected otherwise
      per §4.1 rule 8.
    - ``tmp_path``: absolute path of the EXDEV copy's tmp file/symlink. Only
      populated on v2 ``op=move state=started`` records; ``None`` elsewhere.
      The §7.1 tmp-exists invariant requires it on every such record —
      parse-time rejected otherwise per §4.1 rule 9.
    - ``ts``/``host_pid``: diagnostic metadata written by v2 writers, never
      consulted by the protocol itself (PID reuse makes ``host_pid`` unsafe
      for liveness checks per F2).
    - ``_raw``: for unknown-op records ONLY — the full JSON line as read,
      preserved so compaction re-serializes verbatim (§4.2). Known-op entries
      keep ``_raw = None``; the serializer reconstructs from fields.
    """

    op: str
    src: str
    dst: str
    state: str
    schema: int = 1
    op_id: str | None = None
    tmp_path: str | None = None
    ts: float | None = None
    host_pid: int | None = None
    _raw: str | None = None


def _normalized_path_str(path: Path) -> str:
    r"""Canonicalize *path* for journal storage + comparison.

    Uses ``os.path.abspath`` — resolves relative paths to absolute
    and collapses ``..``/``.`` segments, but does NOT follow symlinks.
    This is deliberate (codex PRRT_kwDOR_Rkws59gRpv): a symlink is a
    first-class file-system entity, and if the caller moves the
    symlink itself, ``sweep`` must unlink that symlink on recovery —
    not the target it happened to point at.

    Wrapped in ``os.path.normcase`` so Windows case-insensitive
    paths compare correctly (codex PRRT_kwDOR_Rkws59hp2G): without
    this, ``C:\foo`` and ``c:\foo`` are the same file but different
    journal strings, so :func:`is_path_in_flight` would miss
    in-flight entries and trash GC could delete a path that an
    active rollback move depended on. ``normcase`` is a no-op on
    POSIX (where the case + separator forms are already canonical),
    so this change has no observable effect on Linux/macOS.

    Coderabbit PRRT_kwDOR_Rkws59fzVv: the same canonicalization
    makes equivalent paths (relative vs absolute, redundant ``..``,
    Windows case) compare as equal in :func:`is_path_in_flight`.
    """
    return os.path.normcase(os.path.abspath(os.fspath(path)))


_LOCK_SUFFIX = ".lock"


def _lock_path(journal: Path) -> Path:
    """Return the sibling lock-file path for *journal* (§6.1).

    All ``fcntl.flock`` operations in the protocol acquire on this
    file rather than on ``journal`` directly. The lock file:

    - Is created on first need by :func:`_locked` (zero-byte).
    - Is **never replaced or unlinked** during normal protocol ops, so
      its inode is stable across compactions that ``os.replace`` the
      journal.
    - Carries no data — only its inode exists as a flock target.

    This is the round-1 review blocking fix: locking the journal
    directly meant a compaction's ``os.replace`` could leave a
    concurrent appender holding a lock on the now-unlinked old inode,
    causing its append to land in an unreachable file.
    """
    return journal.with_name(journal.name + _LOCK_SUFFIX)


@contextlib.contextmanager
def _locked(journal: Path, mode: int) -> Iterator[object | None]:
    """Acquire ``fcntl.flock(mode)`` on the journal's lock file.

    POSIX-only. On Windows or when ``fcntl`` is unavailable, yields
    ``None`` and runs the body unlocked — relies on the
    single-CLI-invocation invariant per the module docstring.

    Ensures ``<journal>.parent`` exists and creates the lock file
    (zero-byte) if absent. The lock file's directory entry is durable
    immediately because flock acquisition won't proceed past the OS
    page cache; in practice the lock's role is purely coordination
    so durability isn't a correctness concern.
    """
    if not _HAS_FCNTL:  # pragma: no cover - Windows
        yield None
        return
    journal.parent.mkdir(parents=True, exist_ok=True)
    lock = _lock_path(journal)
    # ``open(..., "a")`` creates the file if absent without truncating
    # it — keeps a stable inode across all callers.
    # atomic-write: ok — fcntl lock file, stable inode required
    fh = open(lock, "a", encoding="utf-8")  # noqa: safedir-required  # undo-journal lock file — path is an internal temp file, not user-supplied
    try:
        fcntl.flock(fh.fileno(), mode)
        try:
            yield fh
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def durable_move(src: Path, dst: Path, *, journal: Path) -> DstInode | None:
    """Move *src* to *dst* atomically (same device) or durably (EXDEV).

    Args:
        src: Source path. Must exist as a regular file or the call
            raises ``FileNotFoundError``. Symlinks are followed.
        dst: Destination path. Parent directories are created if
            missing (matches ``shutil.move`` semantics callers relied
            on pre-F7). If *dst* already exists it is overwritten —
            same as the pre-F7 ``shutil.move`` behavior.
        journal: JSONL journal file for cross-device operations. May
            not exist yet; the file is created on first EXDEV write.
            For same-device moves (the fast path) the journal is
            untouched — no crash recovery is needed because the move
            is one syscall.

    Returns:
        ``(st_dev, st_ino, st_size)`` of *dst* captured via ``lstat``
        immediately after the move on POSIX. ``None`` on Windows or if
        the lstat fails. Callers that record history should pass the
        non-None triple to ``log_operation(dest_dev=..., dest_ino=...)``
        so ``fo undo`` can verify the file identity before replaying
        the move (PR5b / PR5c, #269).

    Raises:
        FileNotFoundError: If *src* doesn't exist.
        OSError: Any other OS-level failure (permission denied, disk
            full, etc.). The journal will contain a ``started`` or
            ``copied`` entry for the interrupted operation;
            :func:`sweep` on next startup cleans up.
    """
    src = Path(src)
    dst = Path(dst)
    journal = Path(journal)

    if not src.exists() and not src.is_symlink():
        raise FileNotFoundError(f"Source does not exist: {src}")
    # Coderabbit PRRT_kwDOR_Rkws59fzVo: reject directories explicitly.
    # The same-device ``os.replace`` path happily renames directories
    # but the EXDEV ``shutil.copyfile`` path raises ``IsADirectoryError``
    # AFTER writing the ``started`` journal entry, stranding the journal
    # in a state sweep can't recover from. Surface the contract
    # violation up front with ``IsADirectoryError`` so callers can
    # handle it without digging through the journal.
    if src.is_dir() and not src.is_symlink():
        raise IsADirectoryError(f"durable_move only supports regular files; {src} is a directory")

    dst.parent.mkdir(parents=True, exist_ok=True)

    # Fast path: same-device rename. ``os.replace`` is atomic on
    # POSIX + Windows for same-filesystem renames. We only fall
    # through to the durable EXDEV path when the rename fails with
    # EXDEV; any other error surfaces to the caller unchanged.
    try:
        os.replace(src, dst)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        _durable_cross_device_move(src, dst, journal=journal)
    return _capture_dst_inode(dst)


def _compute_tmp_path(src: Path, dst: Path) -> Path:
    """Choose the EXDEV tmp/copy path BEFORE it is created.

    #1248: the ``started`` journal marker must carry ``tmp_path`` AND be
    written before the tmp exists (so the in-flight marker precedes any
    GC-visible window). That means the name has to be decided up front
    rather than discovered from ``NamedTemporaryFile``. The PID suffix
    matches the symlink branch's pre-existing naming so the stale-tmp
    defensive cleanup contract is preserved; collisions between distinct
    concurrent processes are impossible (distinct PIDs) and a same-PID
    collision can only be a prior crashed attempt, which the caller
    unlinks defensively. The tmp always lives in ``dst.parent`` so the
    final ``os.replace`` stays same-filesystem.
    """
    suffix = "symlink.tmp" if src.is_symlink() else "tmp"
    return dst.parent / f".{dst.name}.{os.getpid()}.{suffix}"


def _open_started_window(
    src: Path,
    dst: Path,
    journal: Path,
    base_payload: dict[str, Any],
) -> Path:
    """Journal ``started`` then create the tmp, atomically under ``LOCK_EX``.

    #1248 [P1] file-loss race fix. Returns the tmp path that the EXDEV
    copy/symlink work will consume. Sequence while holding the journal
    ``LOCK_EX`` (so it mutually excludes ``TrashGC.safe_delete``):

    1. Append ``started`` carrying ``tmp_path`` — ``src`` is now
       in-flight to any GC that subsequently acquires the lock.
    2. Materialize the tmp (empty regular file via ``O_CREAT|O_EXCL``,
       or ``os.symlink`` for the symlink branch).
    3. ``fsync_directory(dst)`` so the tmp's directory entry is durable
       (``fsync_directory`` syncs its argument's parent) — preserves the
       §7.1 tmp-exists invariant under power loss.

    On non-POSIX (no ``fcntl``) the lock is a no-op and the same steps
    run unlocked per the module's single-CLI-invocation invariant; the
    ordering (marker before tmp) is still maintained for sweep parity.
    """
    tmp_path = _compute_tmp_path(src, dst)
    started_payload = {**base_payload, "state": STATE_STARTED, "tmp_path": str(tmp_path)}

    def _write_marker_then_create_tmp() -> None:
        # Step 1: in-flight marker FIRST so a GC that later wins the lock
        # observes src as in-flight before it can unlink it.
        if _HAS_FCNTL:
            _append_journal_line_locked(journal, started_payload)
        else:  # pragma: no cover - Windows / no fcntl
            append_durable(journal, json.dumps(started_payload))
        # Step 2: materialize the tmp. A stale tmp at this PID-suffixed
        # path can only be a prior same-PID crashed attempt (distinct
        # processes have distinct PIDs); unlink it defensively so the
        # exclusive create / symlink below can't raise FileExistsError.
        if os.path.lexists(tmp_path):
            _remove_tmp_path(tmp_path)
        if src.is_symlink():
            # Codex P1 PRRT_kwDOR_Rkws59gnab: preserve symlink identity on
            # EXDEV moves. ``readlink`` keeps absolute-vs-relative form.
            target = os.readlink(src)
            os.symlink(target, tmp_path)
        else:
            # Empty regular file, exclusive create. ``O_EXCL`` surfaces a
            # collision rather than silently reusing another op's tmp.
            fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
        # Step 3: §7.1 — fsync the tmp's directory entry so the
        # tmp-exists invariant is crash-durable.
        fsync_directory(dst)

    if _HAS_FCNTL:
        journal.parent.mkdir(parents=True, exist_ok=True)
        with _locked(journal, fcntl.LOCK_EX):
            _write_marker_then_create_tmp()
    else:  # pragma: no cover - Windows / no fcntl
        journal.parent.mkdir(parents=True, exist_ok=True)
        _write_marker_then_create_tmp()
    return tmp_path


def _durable_cross_device_move(src: Path, dst: Path, *, journal: Path) -> None:
    """EXDEV branch: copy + fsync + os.replace + unlink, with v2 journal.

    Step 6 / §7.2 (regular file) + §7.3 (symlink) sequence:

    1. Allocate ``op_id``, build the v2 payload base (``schema=2``,
       ``op_id``, ``ts``, ``host_pid``).
    2. #1248 [P1]: :func:`_open_started_window` — under a single journal
       ``LOCK_EX`` — appends ``started`` with ``tmp_path`` populated,
       THEN creates the tmp (regular: empty file via ``O_CREAT|O_EXCL``;
       symlink: ``os.symlink``), THEN ``fsync_directory(dst)`` so the
       tmp's directory entry is durable (``fsync_directory`` syncs
       its argument's parent; §7.1 tmp-exists invariant).
       The marker is journaled before the tmp exists so a concurrent
       ``TrashGC.safe_delete`` that wins the lock always observes ``src``
       in-flight before it can unlink it.
    3. Copy + fsync (regular only — symlink target lives in the inode);
       the data fsync happens before ``copystat`` (#1248 [P2]) so a
       read-only source mode can't EACCES the fsync reopen.
    4. ``os.replace(tmp, dst)`` — consumes tmp atomically into dst.
    5. ``fsync_directory(dst)`` so the new directory entry is durable
       before we log ``copied`` (codex P1 fwMG).
    6. Append ``copied`` with the same ``op_id``.
    7. ``os.unlink(src)`` + ``fsync_directory(src)`` (codex P2 gnah:
       unlink durability before the ``done`` write).
    8. Append ``done`` with the same ``op_id``.

    §7.4: this function does NOT remove tmp on exception. If anything
    after the tmp is created raises, tmp persists on disk and sweep observes
    ``lexists(tmp_path)`` to disambiguate pre-replace (tmp present) from
    post-replace (tmp absent) crashes. The tmp-cleanup that PR #197 had
    here would have broken that invariant.
    """
    # Resolve to absolute paths before journaling. ``is_path_in_flight``
    # will match on ``str()`` of the resolved form, so callers passing
    # unresolved / relative / symlinked paths still get the right
    # match (coderabbit PRRT_kwDOR_Rkws59fzVv).
    op_id = uuid.uuid4().hex
    base_payload: dict[str, Any] = {
        "schema": 2,
        "op": OP_MOVE,
        "op_id": op_id,
        "src": _normalized_path_str(src),
        "dst": _normalized_path_str(dst),
        "ts": time.time(),
        "host_pid": os.getpid(),
    }

    # #1248 fix [P1] — close the pre-journal file-loss race. Previously
    # the tmp file was created and its dir fsynced BEFORE the ``started``
    # in-flight marker was appended. In that window a concurrent
    # ``TrashGC.safe_delete()`` could take the journal ``LOCK_EX``, see no
    # active entry for ``src``, and unlink it — the move then fails and
    # sweep removes only the orphan tmp, so the user's file is lost.
    #
    # The marker MUST become GC-visible BEFORE any GC check can pass.
    # ``_open_started_window`` acquires ``LOCK_EX`` ONCE and, while
    # holding it, (a) appends ``started`` (carrying the tmp_path the §7.1
    # invariant requires for sweep disambiguation), then (b) materializes
    # the tmp file/symlink and fsyncs its directory. Because the marker is
    # journaled under the same lock that GC must acquire, any GC that wins
    # the race waits on the lock and then sees ``src`` in-flight; any GC
    # that lost it already finished before the window opened. Crash
    # recovery is preserved: the ``started`` row carries ``tmp_path`` and
    # sweep keys off ``lexists(tmp_path)`` (present ⇒ orphan tmp dropped,
    # src canonical; absent + dst absent ⇒ retained, src canonical).
    tmp_path = _open_started_window(src, dst, journal, base_payload)

    if src.is_symlink():
        # No file data to fsync for a symlink — the target string lives
        # in the inode itself on most filesystems. The dst.parent fsync
        # before the started write already covered the tmp's dir entry.
        os.replace(tmp_path, dst)
        fsync_directory(dst)
    else:
        shutil.copyfile(src, tmp_path)  # noqa: safedir-required  # undo-journal atomic copy — src/dst are temp paths managed within the subsystem
        # #1248 fix [P2]: fsync the copied DATA before copying mode bits.
        # The previous order ran ``copystat`` first, which can stamp a
        # read-only mode (e.g. 0444) onto the tmp; the subsequent
        # ``os.open(tmp_path, os.O_RDWR)`` fsync reopen then raises
        # EACCES for a non-root caller. We open the still-writable tmp
        # (created mode 0600 / copyfile default) for the data fsync, and
        # only AFTER do we copy the source mode bits.
        #
        # O_RDWR (not O_RDONLY) is kept so FlushFileBuffers succeeds on
        # Windows — fsync on a read-only handle raises EBADF there. On
        # POSIX, fsync doesn't require write permission, but opening
        # before the mode copy guarantees the handle is always writable.
        fd = os.open(tmp_path, os.O_RDWR)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        # Preserve mode bits so daemons that rely on chmod survive the
        # copy (matches pre-F7 ``shutil.move`` behavior on cross-device
        # moves, which uses copy2 internally). Done LAST so a read-only
        # source mode can't block the data fsync above. The final dst
        # mode equals the source mode (copystat parity).
        try:
            shutil.copystat(src, tmp_path)  # noqa: safedir-required  # undo-journal atomic copy — src/dst are temp paths managed within the subsystem
        except OSError:
            # copystat failures are non-fatal — better to complete the
            # move with default mode than fail.
            logger.debug(
                "copystat failed for %s → %s; proceeding with default mode",
                src,
                tmp_path,
                exc_info=True,
            )
        # fsync parent dir before the rename so a power loss after
        # ``os.replace`` can't leave the new directory entry pointing at
        # an inode with unflushed pages.
        fsync_directory(dst)
        os.replace(tmp_path, dst)
        # Codex P1 PRRT_kwDOR_Rkws59fwMG: fsync ``dst.parent`` AGAIN
        # after the rename so the new directory entry is durable before
        # we log ``copied`` and unlink the source.
        fsync_directory(dst)

    # Destination is complete. Log copied BEFORE unlinking src so a
    # crash here is recoverable by sweep (it sees ``copied`` and
    # finishes by unlinking src). Same op_id as started.
    _append_journal(journal, {**base_payload, "state": STATE_COPIED})

    try:
        os.unlink(src)
    except FileNotFoundError:
        # Source already gone — treat as done.
        pass

    # Codex P2 PRRT_kwDOR_Rkws59gnah: fsync ``src.parent`` so the unlink
    # itself is crash-durable before we log ``done``.
    fsync_directory(src)

    _append_journal(journal, {**base_payload, "state": STATE_DONE})


def directory_move(src: Path, dst: Path, *, journal: Path) -> None:
    """Non-atomic directory move with journal coordination for F8.

    Coderabbit (round-10): ``RollbackExecutor._move()`` previously
    called ``shutil.move`` directly for directories, bypassing the
    durable_move journal entirely. That left a window where
    concurrent trash GC (via :func:`is_path_in_flight`) saw no
    in-flight entry for the directory and could delete the trash
    path mid-restore — exactly the F8 race ``durable_move`` was
    introduced to prevent.

    This helper writes ``op="dir_move"`` started/done entries
    around a non-atomic ``shutil.move``. The entry exists ONLY for
    coordination, NOT for crash recovery — directory moves are
    not idempotent, so a crash mid-shutil.move leaves operator-
    inspectable on-disk state. Sweep drops ``dir_move`` entries
    (with a warning if state != done) since it cannot safely
    re-run the move.

    Args:
        src: Source directory. Must exist as a directory; symlinks
            should route through :func:`durable_move` instead since
            the symlink itself is a single inode.
        dst: Destination directory path. Parent is created if absent.
        journal: Same journal used by :func:`durable_move` calls so
            :func:`is_path_in_flight` sees a unified view.
    """
    src = Path(src)
    dst = Path(dst)
    payload = {
        "op": OP_DIR_MOVE,
        "src": _normalized_path_str(src),
        "dst": _normalized_path_str(dst),
        "state": STATE_STARTED,
    }
    _append_journal(journal, payload)
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))  # noqa: safedir-required  # undo-journal atomic move — src/dst are temp paths managed within the subsystem
    finally:
        # ``done`` is appended even if shutil.move raised, so a
        # caught exception still clears the in-flight marker for
        # GC. If shutil.move partially completed before raising,
        # the operator must reconcile on-disk state — there's no
        # safe automated recovery for directory moves.
        _append_journal(journal, {**payload, "state": STATE_DONE})


def sweep(journal: Path) -> None:
    """Complete or roll back interrupted :func:`durable_move` ops.

    Walks the journal, collapses entries to the latest state per
    (src, dst) pair, and acts:

    - ``started``: crash before destination was ready. Delete any
      partial destination, leave source intact.
    - ``copied``: crash after destination was written but before
      source was cleaned up. Unlink source (destination is already
      in place).
    - ``done``: operation already completed; drop the entry.

    Reconciled entries are dropped from the journal; entries whose
    cleanup raised ``OSError`` (transient permission/lock issues) are
    retained so the next startup can retry. Without that retention,
    a single failed sweep would strand the operation forever (codex
    P1 PRRT_kwDOR_Rkws59fwMK).

    Args:
        journal: JSONL journal from a prior :func:`durable_move` run.
            Missing or empty journal is a no-op.
    """
    journal = Path(journal)
    if not journal.exists():
        return

    # Coordinate via ``<journal>.lock`` (§6.1, step 4): the lock subject
    # is a stable-inode sibling file, NEVER replaced by sweep. Locking
    # the journal directly would let a future compaction's ``os.replace``
    # invalidate concurrent appenders' locks. ``fcntl.flock`` is
    # POSIX-only; on Windows ``_locked`` yields without coordinating
    # and the unlocked sweep body runs (single-CLI-invocation invariant
    # per the module docstring).
    if _HAS_FCNTL:
        with _locked(journal, fcntl.LOCK_EX):
            try:
                # #1248 fix: explicit UTF-8 so the locked sweep read matches
                # the UTF-8 writers; platform-default decoding could corrupt
                # non-ASCII journal paths during reconciliation.
                fh = open(journal, "r+", encoding="utf-8")  # noqa: safedir-required  # undo-journal reader — journal path is an internal file
            except FileNotFoundError:
                # Journal disappeared between ``exists()`` and ``open()`` —
                # nothing to sweep. Narrow scope: don't swallow OSError
                # raised by the body (e.g. ``os.replace`` failures during
                # compaction must propagate so callers can react).
                return
            try:
                _sweep_locked_body(journal, fh)
            finally:
                fh.close()
        return
    _sweep_unlocked_body(journal)


_MAX_JOURNAL_SIZE_BYTES = 16 * 1024 * 1024
"""§6.6 size cap. Journals above this are skipped during compaction with
a WARNING. Steady-state journals are bounded by the in-flight count
(currently ≤1 per CLI invocation), so this is belt-and-suspenders against
pathological growth (a misconfigured retry loop, an external writer,
etc.). 16 MiB is well above the realistic ceiling."""


def _sweep_locked_body(journal: Path, fh) -> None:  # type: ignore[no-untyped-def]
    """Sweep body executed while holding an exclusive flock on the lock file.

    Coderabbit round-10 / step-5 atomic compaction (§6.2): retained
    entries are written to ``<journal>.<pid>.compact.tmp`` then
    ``os.replace``'d into the journal path. A crash mid-compaction
    leaves either the OLD journal intact (if the replace hadn't
    happened) or the NEW journal complete (if it had). No
    truncated-with-pending-entries window.

    The ``journal`` path is carried through for diagnostic logging
    (coderabbit PRRT_kwDOR_Rkws59hgCS) and now also for the compact-
    tmp file path; ``fh`` is the journal-file fd opened by the caller
    for the read step. Writes go through the compact-tmp + replace
    path, NOT through ``fh``.
    """
    fh.seek(0)
    journal_text = fh.read()
    # §6.6 size cap — skip compaction with a WARNING.
    if len(journal_text.encode("utf-8")) > _MAX_JOURNAL_SIZE_BYTES:
        logger.warning(
            "sweep: skipping compaction — journal %s exceeds size cap (%d bytes > %d). "
            "Steady-state journals should be bounded by in-flight count; "
            "investigate runaway append behavior.",
            journal,
            len(journal_text.encode("utf-8")),
            _MAX_JOURNAL_SIZE_BYTES,
        )
        return
    entries = _parse_journal_text(journal_text)
    if not entries:
        return
    retained = _reconcile_entries(entries)
    if not retained and not journal_text.strip():
        # Already empty + nothing to write.
        return
    _atomic_compact_journal(journal, retained)


def _atomic_compact_journal(journal: Path, retained: list[_JournalEntry]) -> None:
    """Replace *journal* atomically with the serialized *retained* entries.

    §6.2 algorithm:

    1. Write to ``<journal>.<pid>.compact.tmp`` via ``open("x")`` so a
       stale tmp from a prior crashed sweep is detected.
    2. ``write + flush + fsync(tmp_fd)``.
    3. ``fsync_directory(journal.parent)`` — durable tmp dir entry.
    4. ``os.replace(tmp, journal)`` — atomic.
    5. ``fsync_directory(journal.parent)`` — durable replace.

    On stale-tmp ``FileExistsError`` (§6.4), unlinks the stale and
    retries once. Two failures in a row indicates a permissions
    pathology that sweep shouldn't paper over — re-raise.

    Caller must hold the ``<journal>.lock`` ``LOCK_EX`` (i.e. only
    invoke from inside ``_sweep_locked_body`` or another locked
    context).
    """
    tmp = journal.with_name(f"{journal.name}.{os.getpid()}.compact.tmp")
    payload = "\n".join(_serialize_entry(e) for e in retained)
    if payload:
        payload += "\n"
    try:
        _write_compact_tmp(tmp, payload)
    except FileExistsError:
        # §6.4: stale tmp from prior crashed sweep — unlink + retry once.
        logger.warning("sweep: removing stale compact-tmp %s and retrying once", tmp)
        with contextlib.suppress(FileNotFoundError):
            tmp.unlink()
        _write_compact_tmp(tmp, payload)
    fsync_directory(journal)
    os.replace(tmp, journal)
    fsync_directory(journal)
    logger.debug(
        "sweep: compacted %s — %d retained entr%s",
        journal,
        len(retained),
        "y" if len(retained) == 1 else "ies",
    )


def _write_compact_tmp(tmp: Path, payload: str) -> None:
    """Open ``tmp`` exclusively (``open("x")``), write *payload*, fsync, close.

    Extracted for reuse by the §6.4 stale-tmp retry. Raises
    ``FileExistsError`` if the tmp already exists — caller decides
    whether to clean and retry.
    """
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        if payload:
            # #1248 fix [P2]: os.write may perform a SHORT write and
            # return fewer bytes than requested. The previous code
            # ignored the return value, so a partial write followed by
            # os.replace could publish a truncated journal and silently
            # drop retained entries. Loop until every byte is flushed.
            data = payload.encode("utf-8")
            written = 0
            while written < len(data):
                n = os.write(fd, data[written:])
                if n == 0:  # pragma: no cover - defensive: 0 implies no progress
                    raise OSError(
                        f"sweep: os.write made no progress writing compact tmp {tmp} "
                        f"({written}/{len(data)} bytes)"
                    )
                written += n
        os.fsync(fd)
    finally:
        os.close(fd)


def _sweep_unlocked_body(journal: Path) -> None:
    """Sweep body for Windows / environments without ``fcntl``.

    Best-effort — callers rely on single-invocation serialization
    for crash safety; see the module docstring.
    """
    # §6.6 size cap — same guard as _sweep_locked_body; skip compaction
    # on pathologically large journals to avoid OOM on the read-modify-write.
    # Guard the read: journal may disappear between sweep()'s exists() check
    # and this read (same TOCTOU that _sweep_locked_body handles via its own
    # FileNotFoundError catch on open()).
    try:
        journal_text = journal.read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    if len(journal_text.encode("utf-8")) > _MAX_JOURNAL_SIZE_BYTES:
        logger.warning(
            "sweep: skipping compaction — journal %s exceeds size cap (%d bytes > %d). "
            "Steady-state journals should be bounded by in-flight count; "
            "investigate runaway append behavior.",
            journal,
            len(journal_text.encode("utf-8")),
            _MAX_JOURNAL_SIZE_BYTES,
        )
        return
    entries = _parse_journal_text(journal_text)
    if not entries:
        return
    retained = _reconcile_entries(entries)
    # The unlocked path (no fcntl, e.g. Windows) cannot rely on advisory
    # locking, so we use the atomic temp-file + os.replace primitive to
    # guarantee a crashed compaction never leaves a half-written journal.
    # CodeRabbit r219 caught the previous in-place ``Path.write_text`` here
    # which could truncate-then-fail and corrupt recovery state.
    payload = "\n".join(_serialize_entry(e) for e in retained)
    if payload:
        payload += "\n"
    atomic_write_with(journal, lambda fh: fh.write(payload), mode="w")


_PlannedVerb = Literal[
    "drop",
    "retain",
    "unlink_src_then_drop",
    "drop_tmp_then_drop",
]
"""Closed verb set per §5.1.

- ``drop`` / ``retain`` / ``unlink_src_then_drop`` — PR #197 subset (step 2).
- ``drop_tmp_then_drop`` — step 6, v2 ``move started`` + ``lexists(tmp_path)``
  pre-replace row: unlink the orphan tmp, then drop the entry.
"""


@dataclass(frozen=True)
class _PlannedAction:
    """A single sweep decision + the entry it applies to.

    Produced by :func:`plan_recovery_actions` (pure, no mutation), executed
    by :func:`_apply_planned_actions`. Round-3 spec §8.1: keeping these
    separate means ``fo undo recover`` and sweep agree on what would
    happen — the CLI calls the planner and renders; sweep calls the
    planner and executes. No "report-only mode" branch can drift.
    """

    identity: _OpIdentity
    entry: _JournalEntry
    verb: _PlannedVerb
    reason: str
    log_level: int = logging.DEBUG


def _identity(entry: _JournalEntry) -> _OpIdentity:
    """Operation identity for collapse-key reduction (§3.1).

    Three rules in order:

    1. v2 known-op record (``schema == 2``, op ∈ ``_KNOWN_OPS``,
       ``op_id`` present): identity is ``("v2", op, op_id)`` — a single
       invocation; different retries of the same move stay distinct.
       The parser enforces ``op_id`` presence (§4.1 rule 8) so a v2
       known-op entry without ``op_id`` never reaches this point.
    2. v1 known-op record (no ``schema`` field on disk): identity is
       ``("v1", op, src, dst)`` — path-keyed fallback matching PR #197
       behavior. The ``"v1"`` discriminator means a v1 record cannot
       collapse with a v2 record sharing the same ``(op, src, dst)``,
       so v2's stronger identity is never silently downgraded.
    3. Unknown op: identity is ``("unknown", op, _hash16(_raw))`` —
       hashed from the full raw line so semantically-distinct future
       records (with fields our parser doesn't understand) don't
       conflate. The parser captures ``_raw`` for unknown ops via
       §4.2; a defensive ``or ""`` covers the ``_raw is None`` case
       a hand-constructed test entry might create.

    Closes codex iy4u (same-path different-op masking) per #201.
    """
    if entry.op in _KNOWN_OPS:
        if entry.schema == 2 and entry.op_id is not None:
            return ("v2", entry.op, entry.op_id)
        return ("v1", entry.op, entry.src, entry.dst)
    return ("unknown", entry.op, _hash16(entry._raw or ""))


def plan_recovery_actions(
    entries: list[_JournalEntry],
    fs_observer: Callable[[str], bool] = os.path.lexists,
) -> list[_PlannedAction]:
    """Pure planner: decide what sweep would do for each retained entry.

    Round-3 design §8.1: this function performs ZERO disk mutation. It
    collapses ``entries`` by the §3.1 identity (step 2 uses PR #197's
    ``(src, dst)``; step 3 will swap in op_id-aware identity), observes
    on-disk state via ``fs_observer`` (defaults to ``os.path.lexists``;
    tests stub for deterministic table coverage), and returns a list of
    :class:`_PlannedAction` that :func:`_apply_planned_actions` then
    executes.

    Both sweep and ``fo undo recover`` (step 8) call this function with
    the same inputs — sweep proceeds to the executor, the CLI just
    renders. That keeps "what sweep would do" and "what the CLI shows"
    bit-identical.

    Args:
        entries: parsed journal entries (from
            :func:`_parse_journal_text` or :func:`_read_journal`).
        fs_observer: callable taking a path string and returning whether
            the path exists. Defaults to ``os.path.lexists`` so dangling
            symlinks count as "present" (matches PR #197 round-6 codex
            hGWW guard).

    Returns:
        One :class:`_PlannedAction` per collapsed identity, in iteration
        order. Verb selection mirrors PR #197 step-2 behavior; the §5.1
        recovery state table covers the full row matrix that step 6 +
        future steps will fill in.
    """
    latest: dict[_OpIdentity, _JournalEntry] = {}
    for entry in entries:
        latest[_identity(entry)] = entry
    plan: list[_PlannedAction] = []
    for identity, entry in latest.items():
        plan.append(_plan_one(identity, entry, fs_observer))
    return plan


def _plan_one(
    identity: _OpIdentity,
    entry: _JournalEntry,
    fs_observer: Callable[[str], bool],
) -> _PlannedAction:
    """Decision matrix for a single collapsed entry.

    PR #197 step-2 subset of §5.1. Step 6 will extend the ``move started``
    row to consult ``fs_observer(entry.tmp_path)`` for disambiguation.
    """
    # Unknown op: future binary's handler owns it; preserve raw payload
    # via _raw (already captured by the parser per §4.2).
    if entry.op not in _KNOWN_OPS:
        return _PlannedAction(
            identity=identity,
            entry=entry,
            verb="retain",
            reason=(
                f"unknown op {entry.op!r} (state={entry.state!r}); waiting for "
                f"a binary that knows this op. Known ops: {sorted(_KNOWN_OPS)}"
            ),
            log_level=logging.WARNING,
        )
    # dir_move: coordination-only (round-10). Sweep can't safely retry
    # shutil.move; drop in any state. WARN if state != done so operator
    # knows on-disk state may need inspection.
    if entry.op == OP_DIR_MOVE:
        if entry.state == STATE_DONE:
            return _PlannedAction(
                identity=identity,
                entry=entry,
                verb="drop",
                reason="dir_move done — coordination complete",
            )
        return _PlannedAction(
            identity=identity,
            entry=entry,
            verb="drop",
            reason=(
                f"dir_move entry {entry.src} -> {entry.dst} in state "
                f"{entry.state!r} — directory moves are non-atomic; "
                f"on-disk state needs operator inspection. Dropping "
                f"entry to release the in-flight marker."
            ),
            log_level=logging.WARNING,
        )
    # entry.op == OP_MOVE — the F7 atomic/durable single-file path.
    if entry.state == STATE_STARTED:
        # §7.1 disambiguation (step 6): v2 records carry ``tmp_path`` and
        # uphold the tmp-exists invariant, so observing ``lexists(tmp_path)``
        # tells sweep which side of the ``os.replace`` boundary the crash
        # landed on. v1 records (no schema, no tmp_path) lack the metadata
        # and preserve PR #197 retain-as-ambiguous behavior.
        if entry.schema == 2 and entry.tmp_path is not None:
            if fs_observer(entry.tmp_path):
                # Pre-replace crash: tmp orphan, replace never ran. src is
                # still the canonical copy. Unlink tmp; drop entry.
                return _PlannedAction(
                    identity=identity,
                    entry=entry,
                    verb="drop_tmp_then_drop",
                    reason=(
                        f"started entry {entry.src} -> {entry.dst} (tmp "
                        f"{entry.tmp_path} present) — pre-replace crash; "
                        "unlinking orphan tmp, src remains canonical"
                    ),
                )
            # Tmp absent — usually post-replace, but only safe to unlink
            # src if dst actually exists. Codex P1 lCbU: tmp-absent is
            # NOT proof that ``os.replace`` ran; tmp could also have been
            # cleaned out-of-band by an operator. If dst is also missing,
            # src is the canonical copy and unlinking it is data loss.
            # Mirror the codex hGWW guard from the COPIED row.
            if not fs_observer(entry.dst):
                return _PlannedAction(
                    identity=identity,
                    entry=entry,
                    verb="retain",
                    reason=(
                        f"started entry {entry.src} -> {entry.dst} (tmp "
                        f"{entry.tmp_path} absent, dst absent) — cannot prove "
                        "post-replace; unlinking src would destroy the last "
                        "remaining copy. Retaining for operator inspection."
                    ),
                    log_level=logging.WARNING,
                )
            # Post-replace crash confirmed: tmp absent + dst present means
            # ``os.replace`` consumed tmp into dst. Same finishing step as
            # the COPIED row — unlink src.
            return _PlannedAction(
                identity=identity,
                entry=entry,
                verb="unlink_src_then_drop",
                reason=(
                    f"started entry {entry.src} -> {entry.dst} (tmp "
                    f"{entry.tmp_path} absent, dst present) — post-replace "
                    "crash; finishing by unlinking src"
                ),
            )
        # v1 fallback: no tmp_path metadata to disambiguate.
        return _PlannedAction(
            identity=identity,
            entry=entry,
            verb="retain",
            reason=(
                f"v1 started entry {entry.src} -> {entry.dst} is ambiguous "
                "(crash in copy→replace window); cannot reconcile without "
                "content comparison — operator or retry must resolve"
            ),
            log_level=logging.WARNING,
        )
    if entry.state == STATE_COPIED:
        # Codex hGWW: dst-presence guard. Missing dst means out-of-band
        # cleanup happened between the journal write and now; unlinking
        # src would destroy the last copy.
        if not fs_observer(entry.dst):
            return _PlannedAction(
                identity=identity,
                entry=entry,
                verb="retain",
                reason=(
                    f"copied entry {entry.src} -> {entry.dst} — dst is missing; "
                    "unlinking src would destroy the last remaining copy"
                ),
                log_level=logging.WARNING,
            )
        return _PlannedAction(
            identity=identity,
            entry=entry,
            verb="unlink_src_then_drop",
            reason=f"copied entry {entry.src} -> {entry.dst}; finishing by unlinking src",
        )
    if entry.state == STATE_DONE:
        return _PlannedAction(
            identity=identity,
            entry=entry,
            verb="drop",
            reason=f"done entry {entry.src} -> {entry.dst}; nothing to do",
        )
    # §5.1 "known-op unknown state": retain + warn. Codex / coderabbit
    # PRRT_kwDOR_Rkws59lDD8: dropping the entry would lose the recovery
    # record AND let ``is_path_in_flight()`` stop protecting the path —
    # even though a newer binary that knows the new state may still need
    # it. Retaining is the safe default; the operator inspects the
    # warning and either upgrades the binary or hand-resolves the entry.
    return _PlannedAction(
        identity=identity,
        entry=entry,
        verb="retain",
        reason=(
            f"unknown state {entry.state!r} for op {entry.op!r}; retaining "
            "so a newer binary can resolve and is_path_in_flight() keeps "
            "protecting the path"
        ),
        log_level=logging.WARNING,
    )


def _apply_planned_actions(plan: list[_PlannedAction]) -> list[_JournalEntry]:
    """Execute each :class:`_PlannedAction`, returning the retained entries.

    Round-3 §8.1: companion to :func:`plan_recovery_actions`. The planner
    decided WHAT to do; this function does it. Mutations are confined
    here so the planner stays pure and the CLI/sweep parity contract
    holds.

    Verbs:

    - ``drop``: log at the planner-chosen level, drop the entry.
    - ``retain``: log at the planner-chosen level, keep the entry.
    - ``unlink_src_then_drop``: unlink src + fsync(src.parent), then drop.
      ``FileNotFoundError`` on unlink is swallowed (already gone). Other
      ``OSError`` falls back to retain — the next sweep retries
      (codex fwMK + PR #197 round-5).
    - ``drop_tmp_then_drop`` (step 6, §7.1 pre-replace row): unlink the
      v2 ``tmp_path`` orphan, then drop the entry. Same OSError-retains
      semantics as ``unlink_src_then_drop``.
    """
    retained: list[_JournalEntry] = []
    for action in plan:
        if action.log_level >= logging.INFO:
            logger.log(action.log_level, "sweep: %s", action.reason)
        if action.verb == "retain":
            retained.append(action.entry)
            continue
        if action.verb == "drop":
            continue
        if action.verb == "unlink_src_then_drop":
            if not _execute_unlink_src(action.entry):
                retained.append(action.entry)
            continue
        if action.verb == "drop_tmp_then_drop":
            if not _execute_unlink_tmp(action.entry):
                retained.append(action.entry)
            continue
        # Defensive: an unknown verb is a programming error, not an
        # input concern — log and retain so we don't silently swallow it.
        logger.error(
            "sweep: unknown planned verb %r on entry %r; retaining defensively",
            action.verb,
            action.entry,
        )
        retained.append(action.entry)
    return retained


def _execute_unlink_src(entry: _JournalEntry) -> bool:
    """Unlink ``entry.src`` and fsync ``src.parent``.

    Returns True on success (entry should drop), False on transient
    ``OSError`` (entry should retain). Extracted from
    :func:`_apply_planned_actions` for testability and to keep the
    executor's main loop within the cyclomatic budget.
    """
    src = Path(entry.src)
    try:
        src.unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning(
            "sweep: failed to unlink source after copied state %s: %s",
            src,
            exc,
            exc_info=True,
        )
        return False
    # Codex P2 PRRT_kwDOR_Rkws59hT9b: fsync src.parent so the unlink
    # is crash-durable BEFORE sweep truncates this entry out of the
    # journal. fsync OSError on unusual FS is non-fatal — the unlink
    # already succeeded.
    try:
        fsync_directory(src)
    except OSError as exc:
        logger.debug(
            "sweep: fsync of src.parent after unlink failed: %s",
            exc,
            exc_info=True,
        )
    return True


def _execute_unlink_tmp(entry: _JournalEntry) -> bool:
    """Unlink ``entry.tmp_path`` (v2 STARTED orphan) and fsync its parent.

    Returns True on success (entry should drop), False on transient
    ``OSError`` (entry should retain — same retry semantics as
    :func:`_execute_unlink_src`). ``FileNotFoundError`` is success:
    if an operator already cleaned the orphan, sweep is idempotent.

    Defensive: ``entry.tmp_path is None`` shouldn't reach here (the
    planner only emits ``drop_tmp_then_drop`` for v2 records with
    ``tmp_path``), but if it does, log + retain.
    """
    if entry.tmp_path is None:  # pragma: no cover - planner invariant
        logger.error(
            "sweep: drop_tmp_then_drop on entry without tmp_path %r; retaining",
            entry,
        )
        return False
    tmp = Path(entry.tmp_path)
    try:
        _remove_tmp_path(tmp)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning(
            "sweep: failed to unlink tmp orphan %s after pre-replace crash: %s",
            tmp,
            exc,
            exc_info=True,
        )
        return False
    # Match _execute_unlink_src: fsync the parent so the unlink is
    # crash-durable before sweep compacts this entry out of the journal.
    try:
        fsync_directory(tmp)
    except OSError as exc:
        logger.debug(
            "sweep: fsync of tmp.parent after unlink failed: %s",
            exc,
            exc_info=True,
        )
    return True


def _remove_tmp_path(tmp_path: Path) -> None:
    """Remove an orphan/stale EXDEV tmp path without following symlinks.

    A tmp path is normally a file or symlink, but a crash, manual repair, or
    hostile local filesystem state can leave a directory at the reserved tmp
    name. ``Path.unlink()`` would raise ``IsADirectoryError`` after the
    ``started`` marker is already journaled, wedging both live move and sweep
    recovery. Treat a real directory as a stale tmp container and remove it
    recursively; symlinks to directories stay on the unlink path.
    """
    if tmp_path.is_dir() and not tmp_path.is_symlink():
        shutil.rmtree(tmp_path)
        return
    tmp_path.unlink()


def _reconcile_entries(entries: list[_JournalEntry]) -> list[_JournalEntry]:
    """Plan + execute reconciliation in one call.

    Thin wrapper preserving the existing sweep call site. The work is
    split between :func:`plan_recovery_actions` (pure decision) and
    :func:`_apply_planned_actions` (mutation). Step 8's ``fo undo
    recover`` calls just the planner.
    """
    return _apply_planned_actions(plan_recovery_actions(entries))


def _serialize_entry(e: _JournalEntry) -> str:
    """JSON-serialize a journal entry for write-back.

    F7.1 §4.2: unknown-op entries are re-serialized VERBATIM from ``_raw``
    so a future binary with a handler for the op receives every field the
    writer persisted — NOT just the v2 parser's known core. Known-op entries
    reconstruct from fields.

    v2 entries (``schema == 2``) emit the extended v2 envelope; v1 entries
    (``schema == 1``, PR #197 back-compat) emit the legacy 4-field form so
    round-trip identity holds across a compaction.
    """
    # Unknown op: verbatim round-trip via the captured raw line.
    if e._raw is not None:
        return e._raw
    if e.schema == 1:
        return json.dumps({"op": e.op, "src": e.src, "dst": e.dst, "state": e.state})
    # v2 envelope. Omit diagnostic fields when None so we don't bloat the
    # journal; the parser treats missing diagnostic fields as None on read.
    payload: dict[str, object] = {
        "schema": e.schema,
        "op": e.op,
        "op_id": e.op_id,
        "src": e.src,
        "dst": e.dst,
        "state": e.state,
    }
    if e.tmp_path is not None:
        payload["tmp_path"] = e.tmp_path
    if e.ts is not None:
        payload["ts"] = e.ts
    if e.host_pid is not None:
        payload["host_pid"] = e.host_pid
    return json.dumps(payload)


def _parse_journal_text(text: str) -> list[_JournalEntry]:
    """Parse JSONL journal text into typed entries.

    Applies the §4.1 rejection rules — every malformed line is logged +
    skipped; no input can cause the parser to raise. v1 records
    (``schema`` absent) and v2 records (``schema == 2``) both accepted.
    Unknown-op entries retain their full raw JSON line on ``_raw`` per
    §4.2 for verbatim forward-compat.
    """
    entries: list[_JournalEntry] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        entry = _parse_one_journal_line(line)
        if entry is not None:
            entries.append(entry)
    return entries


class _ParseReject(Exception):
    """Internal sentinel: a field validator rejected the line.

    Validators raise this with the line already logged so the top-level
    parser can ``except _ParseReject: return None`` without nested
    logging concerns. Not exposed outside the module.
    """


def _reject(msg: str, *args: object, line: str) -> _ParseReject:
    """Log a rejection reason + truncated line and return a sentinel exception.

    Keeps every rejection site one-liner-ish so
    :func:`_parse_one_journal_line` stays within the cyclomatic budget. The
    caller raises the returned value so control flow stays explicit.
    """
    logger.warning(msg + ": %r", *args, line[:200])
    return _ParseReject()


def _validate_core_fields(data: dict[str, Any], line: str) -> tuple[str, str, str, str]:
    """§4.1 rules 3 + 4: op/src/dst/state present and string-typed."""
    op = data.get("op")
    src = data.get("src")
    dst = data.get("dst")
    state = data.get("state")
    if not (
        isinstance(op, str)
        and isinstance(src, str)
        and isinstance(dst, str)
        and isinstance(state, str)
    ):
        raise _reject("sweep: dropping malformed journal entry", line=line)
    return op, src, dst, state


def _validate_schema(data: dict[str, Any], line: str) -> int:
    """§4.1 rule 6: schema is absent (→ 1) or a positive int."""
    schema_raw = data.get("schema")
    if schema_raw is None:
        return 1
    if isinstance(schema_raw, bool) or not isinstance(schema_raw, int) or schema_raw < 1:
        raise _reject("sweep: dropping entry with invalid schema %r", schema_raw, line=line)
    return int(schema_raw)


def _validate_op_id(data: dict[str, Any], line: str) -> str | None:
    """Parse ``op_id``. None if absent, string if typed, rejection otherwise."""
    raw = data.get("op_id")
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    raise _reject("sweep: dropping entry with non-string op_id %r", raw, line=line)


def _validate_tmp_path(data: dict[str, Any], line: str) -> str | None:
    """Parse ``tmp_path``. None if absent, string if typed, rejection otherwise."""
    raw = data.get("tmp_path")
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    raise _reject("sweep: dropping entry with non-string tmp_path %r", raw, line=line)


def _validate_ts(data: dict[str, Any], line: str) -> float | None:
    """Parse diagnostic ``ts``. None/float; reject bool (bool is int subclass)."""
    raw = data.get("ts")
    if raw is None:
        return None
    if isinstance(raw, bool):
        raise _reject("sweep: dropping entry with bool ts", line=line)
    if isinstance(raw, (int, float)):
        return float(raw)
    raise _reject("sweep: dropping entry with non-numeric ts %r", raw, line=line)


def _validate_host_pid(data: dict[str, Any], line: str) -> int | None:
    """Parse diagnostic ``host_pid``. None/int; reject bool."""
    raw = data.get("host_pid")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise _reject("sweep: dropping entry with non-int host_pid %r", raw, line=line)
    return int(raw)


def _parse_one_journal_line(line: str) -> _JournalEntry | None:
    """Parse a single stripped journal line per §4.1 rejection rules.

    Returns ``None`` (and logs WARNING) on any rejection case. Returns a
    typed :class:`_JournalEntry` on success. Rejection sites delegate
    to per-field ``_validate_*`` helpers to keep this function within
    the project's cyclomatic complexity budget.
    """
    # §4.1 rule 7: oversized line cap (measured in bytes so UTF-8 payloads
    # can't slip past via multi-byte characters).
    encoded = line.encode("utf-8")
    if len(encoded) > _MAX_JOURNAL_LINE_BYTES:
        logger.warning(
            "sweep: dropping oversized journal line (%d bytes > %d cap): %r",
            len(encoded),
            _MAX_JOURNAL_LINE_BYTES,
            line[:200],
        )
        return None
    # §4.1 rule 1: JSON parse error.
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        logger.warning("sweep: dropping unparsable journal line: %r", line[:200])
        return None
    # §4.1 rule 2 (codex iy4w): valid JSON but not an object.
    if not isinstance(data, dict):
        logger.warning(
            "sweep: dropping non-object journal line (got %s): %r",
            type(data).__name__,
            line[:200],
        )
        return None
    # Per-field validation via helpers — each raises _ParseReject with the
    # line already logged.
    try:
        op, src, dst, state = _validate_core_fields(data, line)
        schema = _validate_schema(data, line)
        if schema == 1 and op not in _KNOWN_OPS:
            raise _reject(
                "sweep: dropping v1 entry with unknown op %r (v1 records must be in %s)",
                op,
                sorted(_KNOWN_OPS),
                line=line,
            )
        op_id = _validate_op_id(data, line)
        if schema == 2 and op in _KNOWN_OPS and op_id is None:
            raise _reject("sweep: dropping v2 known-op entry missing op_id", line=line)
        tmp_path = _validate_tmp_path(data, line)
        if schema == 2 and op == OP_MOVE and state == STATE_STARTED and tmp_path is None:
            raise _reject(
                "sweep: dropping v2 move-started entry missing tmp_path (§7.1 invariant)",
                line=line,
            )
        ts = _validate_ts(data, line)
        host_pid = _validate_host_pid(data, line)
    except _ParseReject:
        return None
    # §4.2: unknown ops retain the raw line verbatim for forward-compat.
    # Known ops drop extra fields silently.
    raw_for_unknown_op = line if op not in _KNOWN_OPS else None
    return _JournalEntry(
        op=op,
        src=src,
        dst=dst,
        state=state,
        schema=schema,
        op_id=op_id,
        tmp_path=tmp_path,
        ts=ts,
        host_pid=host_pid,
        _raw=raw_for_unknown_op,
    )


def read_journal_under_shared_lock(journal: Path) -> list[_JournalEntry]:
    """Public reader for ``fo recover`` and other read-only consumers (§8.2).

    Acquires ``LOCK_SH`` on ``<journal>.lock`` (per §6.5) so the read
    blocks while any writer or compaction holds ``LOCK_EX``, and
    returns parsed entries. Missing or empty journal → empty list
    (no-op — the caller treats it as "nothing to recover").

    Distinct from :func:`is_path_in_flight` which collapses to the
    latest state per identity for membership queries; this returns
    raw entries so callers can pass them straight to
    :func:`plan_recovery_actions`.

    On non-POSIX (Windows, no ``fcntl``), falls back to an unlocked
    read consistent with the module docstring's single-CLI-invocation
    invariant.
    """
    journal = Path(journal)
    if not journal.exists():
        return []
    if _HAS_FCNTL:
        try:
            with _locked(journal, fcntl.LOCK_SH), open(journal, encoding="utf-8") as fh:  # noqa: safedir-required  # undo-journal reader — journal path is an internal file
                return _parse_journal_text(fh.read())
        except FileNotFoundError:  # pragma: no cover - exists()→open() race
            return []
    return _read_journal(journal)  # pragma: no cover - Windows-only path


def is_path_in_flight(path: Path, *, journal: Path) -> bool:
    """Return True iff *path* is the src or dst of an uncompleted move.

    F8 (hardening roadmap #159): exposes the durable_move journal as
    a coordination point for concurrent access to paths. Any consumer
    that wants to delete or mutate a file that might simultaneously
    be the subject of an in-flight :func:`durable_move` (trash GC,
    dedup cleanup, manual ``rm``) should call this first and skip the
    path if True.

    "In-flight" means the journal's latest state entry for the
    (src, dst) pair is ``started`` or ``copied`` — neither ``done``
    nor absent. An operation in those states leaves files on disk
    whose lifecycle the sweep will complete on next startup;
    deleting one of them out from under the sweep would strand the
    operation permanently.

    Codex P2 PRRT_kwDOR_Rkws59ir1P: this read MUST acquire ``LOCK_SH``
    on the journal before parsing. Writers
    (:func:`_append_journal`, :func:`sweep`) hold ``LOCK_EX`` while
    appending or truncating; without a corresponding shared lock here
    the reader can observe a stale journal between a writer's
    ``open(..., "a")`` and the actual append, returning ``False`` for
    a path that's about to be marked in-flight. In the F8 trash-GC
    flow that race is the entire data-loss vector this function
    exists to prevent.

    Args:
        path: Absolute path to check.
        journal: Same journal used by the matching ``durable_move``
            calls. Missing/empty journal → ``False`` (nothing in
            flight).
    """
    journal = Path(journal)
    if not journal.exists():
        return False

    # Coordinate via ``<journal>.lock`` (§6.1, step 4) — same lock as
    # writers. ``LOCK_SH`` blocks while any ``LOCK_EX`` is held by an
    # appender or compaction, so the reader never observes a journal
    # state mid-write (the F8 GC race protection).
    entries: list[_JournalEntry] = []
    if _HAS_FCNTL:
        try:
            with _locked(journal, fcntl.LOCK_SH), open(journal, encoding="utf-8") as fh:  # noqa: safedir-required  # undo-journal reader — journal path is an internal file
                entries = _parse_journal_text(fh.read())
        except FileNotFoundError:  # pragma: no cover - exists()→open() race
            # Journal disappeared between exists() and open() — treat
            # the same as missing-journal. No coordination needed since
            # no writer can touch a deleted file.
            return False
    else:  # pragma: no cover - Windows-only
        # Windows: fall back to unlocked read; relies on the single-
        # CLI-invocation invariant per the module docstring.
        entries = _read_journal(journal)
    return _path_in_flight_from_entries(path, entries)


def _path_in_flight_from_entries(path: Path, entries: list[_JournalEntry]) -> bool:
    """Lock-free predicate: is *path* the src or dst of an active move?

    Extracted from :func:`is_path_in_flight` so callers that ALREADY
    hold the journal lock (e.g. F8.1 ``TrashGC.safe_delete`` under
    ``LOCK_EX``) can run the same membership check without re-acquiring
    ``LOCK_SH`` on the same lock file (which would deadlock on a
    different fd against the held LOCK_EX on the inode).

    The collapse rule is identical to :func:`is_path_in_flight`: §3.1
    operation identity, NOT path-keyed reduction. Any bug fix to one
    must mirror to the other — this function is the canonical predicate.

    #1248 fix [P2]: ``dir_move`` entries protect their DESCENDANTS, not
    just the exact directory path. A non-atomic ``directory_move`` of
    ``trash/A`` to ``dst/A`` leaves every child of ``trash/A`` mid-flight;
    a GC deleting ``trash/A/child.txt`` while the move is in progress
    would race the ``shutil.move``. Single-file ``move`` entries keep
    exact-match semantics (a file has no descendants).
    """
    if not entries:
        return False
    # Normalize the query path the same way writers do so the compare
    # works on equivalent paths (coderabbit PRRT_kwDOR_Rkws59fzVv).
    path_str = _normalized_path_str(path)
    # §3.1: collapse by the operation identity ("v2"/op/op_id, "v1"/op/src/dst,
    # or "unknown"/op/_hash16) — same key the planner uses. Path-keyed collapse
    # would re-introduce the codex iy4u masking bug for F8 trash-GC.
    latest: dict[_OpIdentity, _JournalEntry] = {}
    for entry in entries:
        latest[_identity(entry)] = entry
    for entry in latest.values():
        if entry.state == STATE_DONE:
            continue
        # Normalize stored paths the same way the query path is normalized.
        # Production writers always store normcased paths via
        # ``_normalized_path_str``, but test helpers and old journals may
        # store the original case.  Applying normcase here makes the compare
        # case-insensitive on Windows (normcase is a no-op on POSIX).
        entry_src = os.path.normcase(entry.src)
        entry_dst = os.path.normcase(entry.dst)
        if entry_src == path_str or entry_dst == path_str:
            return True
        # #1248 [P2]: dir_move protects descendants of src/dst too.
        if entry.op == OP_DIR_MOVE and (
            _is_descendant(path_str, entry_src) or _is_descendant(path_str, entry_dst)
        ):
            return True
    return False


def _is_descendant(path_str: str, ancestor: str) -> bool:
    """Return True iff *path_str* lies strictly under directory *ancestor*.

    #1248 [P2]: both arguments are already normcased + absolute (the
    caller normalizes via :func:`_normalized_path_str` / ``normcase``).
    Comparison is on path components (``os.sep`` boundary) so a sibling
    sharing a name prefix (``/trash/Abc`` vs ancestor ``/trash/A``) is
    NOT treated as a descendant. ``os.path.relpath`` would be ambiguous
    across drives on Windows, so we use an explicit separator-anchored
    prefix check.
    """
    if path_str == ancestor:
        return False
    prefix = ancestor if ancestor.endswith(os.sep) else ancestor + os.sep
    return path_str.startswith(prefix)


def _append_journal(journal: Path, payload: Mapping[str, object]) -> None:
    """Append one JSON line to the journal with flock + fsync durability.

    Codex P1 PRRT_kwDOR_Rkws59gbdH: :func:`sweep` holds an exclusive
    ``fcntl.flock`` on the journal for the entire read-modify-truncate
    cycle. This helper MUST acquire the same advisory lock before
    writing — otherwise a concurrent writer can append a ``started``
    entry between sweep's read and its truncate, and sweep will then
    silently wipe that record. If the writer then crashes mid-move,
    recovery metadata is lost and the orphan files on disk have no
    journal entry sweep can use to reconcile them on the next startup.

    POSIX path: open the journal in append mode, acquire ``LOCK_EX``
    on the descriptor, write + flush + fsync the data, fsync the
    parent directory, then release the lock. ``O_APPEND`` makes the
    offset advance atomically, but the lock (not the offset) is what
    serializes us with sweep's truncate.

    Non-POSIX fallback: :func:`utils.atomic_write.append_durable`.
    Crash-safety relies on the module-docstring "single CLI
    invocation" invariant; Windows sweep uses the unlocked body too.
    """
    journal.parent.mkdir(parents=True, exist_ok=True)
    # Coordinate via ``<journal>.lock`` (§6.1, step 4): same lock as
    # sweep + readers. The journal file itself may be replaced by a
    # future compaction (step 5); the lock file's stable inode means
    # this appender's lock acquisition coordinates with that
    # compaction without depending on the journal inode.
    if _HAS_FCNTL:
        with _locked(journal, fcntl.LOCK_EX):
            _append_journal_line_locked(journal, payload)
        return
    append_durable(journal, json.dumps(payload))


def _append_journal_line_locked(journal: Path, payload: Mapping[str, object]) -> None:
    """Append one JSON line + fsync, with the journal ``LOCK_EX`` ALREADY held.

    #1248: extracted from :func:`_append_journal` so callers that must
    perform additional work atomically with the append (the EXDEV
    started-window in :func:`_open_started_window`) can do so without
    releasing and re-acquiring the lock between the journal write and
    the dependent file-system mutation. The caller is responsible for
    holding ``_locked(journal, fcntl.LOCK_EX)`` around this call.
    """
    line = json.dumps(payload) + "\n"
    # atomic-write: ok — append_durable pattern (LOCK_EX held by caller + fsync below)
    with open(journal, "a", encoding="utf-8") as fh:  # noqa: safedir-required  # undo-journal writer — journal path is an internal file
        fh.write(line)
        fh.flush()
        os.fsync(fh.fileno())
    fsync_directory(journal)


def _read_journal(journal: Path) -> list[_JournalEntry]:
    """Parse the JSONL journal into typed entries. Missing/empty → [].

    F7.1 consolidation: previously duplicated the parse body from
    :func:`_parse_journal_text`, which caused the round-8 ``isinstance(data,
    dict)`` fix to be applied to only one of the two parsers (codex iy4w
    flagged this in the #201 body — "the same pattern appears in
    ``_read_journal``"). Now a thin wrapper over the shared parser so the
    §4.1 rejection rules cover both call sites.
    """
    if not journal.exists():
        return []
    # #1248 fix: writers always encode UTF-8 (see _append_journal_line_locked
    # / _write_compact_tmp), so the reader MUST decode UTF-8 too. Relying on
    # the platform default could mojibake non-ASCII paths on locales whose
    # default codec isn't UTF-8, corrupting the in-flight predicate.
    return _parse_journal_text(journal.read_text(encoding="utf-8"))
