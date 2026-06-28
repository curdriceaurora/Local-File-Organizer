"""PID file management for the daemon.

Provides the PidFileManager class for creating, reading, and removing
PID files, plus checking whether a recorded process is still alive.

F2 (hardening roadmap #159) — PID-reuse race protection:
Pre-F2 PID files stored only the integer PID. When a daemon crashed
and the OS later recycled its PID for an unrelated process, the next
call to ``is_running`` reported the daemon as alive — because the PID
still existed, just for a different process. F2 introduces a JSON
record format that also captures the process start-time
(``psutil.Process(pid).create_time()``); ``is_running`` rejects records
whose PID is alive but whose start-time doesn't match.

F4 (hardening roadmap #159) — check-then-act atomicity:
``is_running`` + ``write_pid_record`` is a check-then-act pair that
exhibits a TOCTOU race: two daemon processes can both observe the PID
file as absent (or stale), pass the liveness check, and then both
proceed to write their PIDs — the second silently overwriting the
first.  ``claim_pid_file`` closes this window by using ``open(path,
"x")`` which is atomic on POSIX: the OS creates the file and returns
the fd in a single syscall, and raises ``FileExistsError`` for every
concurrent opener after the first.

Backward compat: legacy text-only PID files still read and work (with
a documented degradation — no recycling detection for those).
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import psutil

from file_organizer.utils.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)

# Tolerance for matching create_time. psutil typically returns
# microsecond precision on Linux and millisecond precision on macOS;
# 0.5s is generous but avoids false mismatches from rounding.
_CREATE_TIME_TOLERANCE_S = 0.5


@dataclass(frozen=True)
class PidRecord:
    """A PID record loaded from disk.

    Attributes:
        pid: The recorded process ID.
        create_time: ``psutil.Process.create_time()`` of the process that
            wrote the record, in seconds since epoch. ``None`` for
            legacy text-only PID files — callers fall back to
            ``psutil.pid_exists`` only, losing recycling protection.
    """

    pid: int
    create_time: float | None


class PidFileManager:
    """Manages PID files for daemon process tracking.

    PID files record the process ID of a running daemon so that
    other processes (or the user) can detect whether the daemon is
    active and send it signals.

    Example:
        >>> manager = PidFileManager()
        >>> pid_path = Path("/run/daemon.pid")
        >>> manager.write_pid_record(pid_path)
        >>> assert manager.is_running(pid_path)
        >>> manager.remove_pid(pid_path)
    """

    def write_pid(self, pid_file: Path | str, pid: int | None = None) -> None:
        """Write the process ID to a PID file (legacy format).

        Args:
            pid_file: Path to the PID file.
            pid: Process ID to write. Defaults to the current process.
        """
        pid = pid if pid is not None else os.getpid()
        pid_file = Path(pid_file)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(pid_file, str(pid))

    def read_pid(self, pid_file: Path) -> int | None:
        """Read the process ID from a PID file.

        Args:
            pid_file: Path to the PID file.

        Returns:
            The process ID as an integer, or None if the file does not
            exist or contains invalid content.
        """
        pid_file = Path(pid_file)

        if not pid_file.exists():
            return None

        try:
            content = pid_file.read_text().strip()
            if not content:
                return None
            return int(content)
        except (ValueError, OSError) as exc:
            logger.warning("Failed to read PID from %s: %s", pid_file, exc, exc_info=True)
            return None

    def remove_pid(self, pid_file: Path, expected_record: PidRecord | None = None) -> bool:
        """Remove a PID file.

        Args:
            pid_file: Path to the PID file to remove.
            expected_record: If provided, only remove the PID file if its current on-disk
                record matches expected_record (to avoid unlinking a file newly claimed by another process).

        Returns:
            True if the file was removed, False if it did not exist or record did not match.
        """
        pid_file = Path(pid_file)

        if not pid_file.exists():
            logger.debug("PID file does not exist: %s", pid_file)
            return False

        if expected_record is not None:
            current_record = self.read_pid_record(pid_file)
            if current_record != expected_record:
                logger.debug("PID file record changed; skipping removal: %s", pid_file)
                return False

        try:
            pid_file.unlink()
            logger.debug("Removed PID file: %s", pid_file)
            return True
        except OSError as exc:
            logger.warning("Failed to remove PID file %s: %s", pid_file, exc, exc_info=True)
            return False

    def claim_pid_file(self, pid_file: Path, pid: int | None = None) -> PidRecord:
        """Atomically claim *pid_file* with a live PID record.

        F4 (hardening roadmap #159): closes the TOCTOU window between
        :meth:`is_running` and :meth:`write_pid_record`.  Two daemon
        processes can both observe the PID file as absent, pass the
        liveness check, and then both call :meth:`write_pid_record` —
        the second silently overwriting the first.  This method uses
        ``os.open(O_CREAT | O_EXCL | O_WRONLY)`` which is atomic on POSIX:
        exactly one caller succeeds; every subsequent caller raises
        :exc:`FileExistsError`. The winner writes the real JSON PID record
        immediately so a concurrent starter sees a live daemon instead of a
        placeholder it might treat as stale/corrupt.

        :meth:`write_pid_record` calls this internally before the
        tmp-file dance, so callers do not need to invoke it directly.
        It is exposed publicly so tests and advanced callers can assert
        the claim step independently.

        Args:
            pid_file: Path to claim.
            pid: Process ID to write. Defaults to the current process.

        Returns:
            The :class:`PidRecord` that was written.

        Raises:
            FileExistsError: If another process has already claimed
                *pid_file* (i.e. the file already exists on disk).
            OSError: For other I/O failures (permissions, missing parent
                directory, etc.).
        """
        pid = pid if pid is not None else os.getpid()
        create_time = psutil.Process(pid).create_time()
        record = PidRecord(pid=pid, create_time=create_time)
        payload = json.dumps({"pid": pid, "create_time": create_time})
        pid_file = Path(pid_file)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        # os.open() with O_CREAT|O_EXCL is the POSIX atomic exclusive-create
        # primitive.  Unlike open("x"), it accepts an explicit ``mode``
        # argument that is applied BEFORE umask masking (O_EXCL semantics)
        # so the placeholder inherits the same 0o644 target mode as the
        # final JSON record — keeping the umask-independence guarantee
        # that TestWritePidRecordPermissions verifies.
        try:
            fd = os.open(
                pid_file,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o644,
            )
        except FileExistsError:
            raise
        except OSError as exc:
            logger.debug("claim_pid_file(%s) failed: %s", pid_file, exc)
            raise
        # os.open() mode is still masked by the process umask — use
        # fchmod() on the open fd (which bypasses umask) to force 0o644
        # regardless of the caller's umask.  This matches the approach
        # write_pid_record uses on the NamedTemporaryFile.
        if hasattr(os, "fchmod"):
            try:
                os.fchmod(fd, 0o644)
            except OSError:
                pass  # non-fatal; chmod on tmp_path below will cover it
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
                fh.flush()
                os.fsync(fh.fileno())
        except OSError:
            # Write to the already-created fd failed — the file exists on
            # disk but is empty/partial; clean up and re-raise.
            try:
                pid_file.unlink()
            except OSError:
                pass
            raise
        return record

    def write_pid_record(self, pid_file: Path, pid: int | None = None) -> PidRecord:
        """Write a PID + process-start-time record to *pid_file*.

        F2 (hardening roadmap #159): records the process's start time
        so :meth:`is_running` can detect PID recycling.

        Args:
            pid_file: Path where the record will be written.
            pid: Process ID to write. Defaults to the current process.

        Returns:
            The :class:`PidRecord` that was written.

        Raises:
            OSError: If the file cannot be written.
            psutil.NoSuchProcess: If *pid* doesn't exist at write time.
            psutil.AccessDenied: If *pid* refers to a process owned by
                another user whose ``create_time`` isn't readable
                (typically only triggered when callers pass an explicit
                *pid* that isn't the current process).
        """
        pid = pid if pid is not None else os.getpid()
        create_time = psutil.Process(pid).create_time()
        pid_file = Path(pid_file)
        pid_file.parent.mkdir(parents=True, exist_ok=True)
        # F4 (atomic claim): use open("x") to exclusively create the file
        # before the tmp-write dance.  This closes the TOCTOU window where
        # two processes both call is_running() → False and then both call
        # write_pid_record() — without the claim, the second os.replace()
        # silently wins and the first daemon's PID is lost.  Only attempt
        # the claim when the file does not yet exist; on daemon rotation
        # (pid_file already present from a previous write) we fall through
        # to the normal os.replace() path which is idempotent for the same
        # process.
        if not pid_file.exists():
            return self.claim_pid_file(pid_file, pid=pid)
        # F3 (atomic write): temp file + os.replace so a mid-write crash
        # can never leave a partial JSON file. A corrupt record would
        # otherwise defeat the F2 recycling check — ``read_pid_record``
        # falls through to legacy int parse, returns None, and a fresh
        # ``daemon start`` would spawn a second daemon alongside the
        # original.
        payload = json.dumps({"pid": pid, "create_time": create_time})
        tmp_path: Path | None = None
        # Permission preservation (codex P2 PRRT_kwDOR_Rkws59bl3J):
        # ``tempfile.NamedTemporaryFile`` creates the file with mode
        # 0o600 (via ``mkstemp``). After ``os.replace`` the destination
        # inherits that mode, silently dropping cross-account access
        # the pre-F2 ``write_pid`` provided via ``open(path, "w")``.
        # In deployments where the daemon runs as one user and
        # operators run ``daemon status``/``stop`` as another, 0o600
        # breaks cross-account reads, causing ``read_pid_record`` to
        # return None and ``stop`` to wipe a valid PID file.
        #
        # Strategy: preserve the pre-existing file's mode on rotation;
        # fall back to ``0o644`` for first-time writes. 0o644 is the
        # standard daemon PID file mode (matches /var/run/*.pid
        # convention and the default-umask result of the pre-F2
        # ``open(path, "w")``). Deliberately NOT probing ``os.umask``
        # — that call is process-global and creates a race window
        # where concurrent threads creating files inherit the probe's
        # permissive mode (codex P2 PRRT_kwDOR_Rkws59bvEf). Operators
        # who need a stricter mode can chmod the PID file; rotation
        # will preserve it.
        # Codex P2 PRRT_kwDOR_Rkws59b9f_ (ownership preservation): when
        # an operator pre-provisions the PID file with specific uid:gid
        # (e.g. ``root:operator`` for cross-account ``daemon stop``),
        # ``os.replace`` creates a new inode owned by whoever the
        # daemon runs as, silently dropping the group access. Capture
        # uid/gid alongside mode before the replace so we can ``chown``
        # them back. ``chown`` to a *different* user typically requires
        # CAP_CHOWN / root on Linux — if we don't have it we fall back
        # silently (same degradation philosophy as the mode path: a
        # stricter PID file beats a lost one).
        existing_mode: int | None
        existing_uid: int | None
        existing_gid: int | None
        try:
            st = pid_file.stat()
            existing_mode = st.st_mode & 0o7777
            existing_uid = st.st_uid
            existing_gid = st.st_gid
        except FileNotFoundError:
            existing_mode = None
            existing_uid = None
            existing_gid = None
        target_mode = existing_mode if existing_mode is not None else 0o644
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=pid_file.parent,
                prefix=f".{pid_file.name}.",
                suffix=".tmp",
                delete=False,
            ) as tmp:
                # Coderabbit PRRT_kwDOR_Rkws59dhdX: capture ``tmp_path``
                # BEFORE write/flush/fsync so the ``finally`` cleanup
                # armed at Line 166 actually sees the on-disk temp if
                # any of those calls raises (ENOSPC, EIO,
                # KeyboardInterrupt). ``NamedTemporaryFile(delete=False)``
                # creates the file on disk immediately and does not
                # auto-unlink on exception — without this assignment
                # order a mid-write failure would leave ``.tmp`` debris
                # next to the real PID file.
                tmp_path = Path(tmp.name)
                tmp.write(payload)
                tmp.flush()
                os.fsync(tmp.fileno())
            try:
                os.chmod(tmp_path, target_mode)
            except OSError:
                # chmod failure is non-fatal — fall back to the 0o600
                # temp mode rather than lose the write. A lost PID
                # file would crash ``daemon stop`` entirely; a
                # too-restrictive PID file only breaks cross-account
                # reads, which is the same failure mode we were trying
                # to fix. Log and move on.
                logger.debug(
                    "Failed to chmod temp PID file %s to %#o; "
                    "proceeding with mkstemp default (0o600)",
                    tmp_path,
                    target_mode,
                )
            os.replace(tmp_path, pid_file)
            tmp_path = None  # successfully moved — no cleanup needed
            # Restore uid/gid on rotation. No-op when the daemon is
            # writing its own PID file as the same account; matters
            # only when an operator pre-provisioned ``root:operator``
            # or similar for cross-account access.
            #
            # ``hasattr`` guard (codex P1 PRRT_kwDOR_Rkws59cFi6): on
            # Windows ``os.chown`` doesn't exist as an attribute at
            # all — a bare ``os.chown(...)`` call raises
            # ``AttributeError`` before the ``try`` block has a chance
            # to catch it, aborting daemon startup whenever a PID
            # file already exists. Short-circuit on the missing
            # attribute so the rest of the rotation succeeds.
            if existing_uid is not None and existing_gid is not None and hasattr(os, "chown"):
                try:
                    os.chown(pid_file, existing_uid, existing_gid)
                except (PermissionError, OSError) as exc:
                    # Typically PermissionError when the daemon doesn't
                    # have CAP_CHOWN to set a different user. Don't
                    # fail the write — just log.
                    logger.debug(
                        "Failed to chown %s to %d:%d (%s); ownership inherits writer's account",
                        pid_file,
                        existing_uid,
                        existing_gid,
                        exc,
                    )
        finally:
            if tmp_path is not None and tmp_path.exists():
                # os.replace failed — best-effort cleanup of the stray
                # temp file so we don't accumulate .tmp debris.
                try:
                    tmp_path.unlink()
                except OSError:
                    logger.debug("Failed to clean up stray temp PID file %s", tmp_path)
        logger.debug(
            "Wrote PID record pid=%d create_time=%f to %s (mode=%#o)",
            pid,
            create_time,
            pid_file,
            target_mode,
        )
        return PidRecord(pid=pid, create_time=create_time)

    def read_pid_record(self, pid_file: Path) -> PidRecord | None:
        """Read a PID record from *pid_file*.

        Handles both F2 JSON format and the legacy text-only integer
        format. Returns ``None`` for missing/empty/corrupt files.

        Args:
            pid_file: Path to the PID file.

        Returns:
            A :class:`PidRecord`, or ``None`` if the file is missing,
            empty, or unparsable as either JSON or integer.
        """
        pid_file = Path(pid_file)
        if not pid_file.exists():
            return None

        try:
            content = pid_file.read_text().strip()
        except OSError as exc:
            logger.warning("Failed to read PID file %s: %s", pid_file, exc, exc_info=True)
            return None
        except UnicodeDecodeError as exc:
            # Codex P2 PRRT_kwDOR_Rkws59b9f6: a PID file containing
            # non-UTF-8 bytes (corruption, partial overwrite by a
            # different tool) used to crash ``daemon status``/``stop``
            # because ``Path.read_text`` raises ``UnicodeDecodeError``
            # which is NOT an ``OSError``. The docstring promises
            # ``None`` for corrupt files; honour it.
            logger.warning(
                "PID file %s is not valid UTF-8 (likely corrupt): %s",
                pid_file,
                exc,
                exc_info=True,
            )
            return None

        if not content:
            return None

        # Try F2 JSON format first.
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "pid" in data:
                # Codex P2 PRRT_kwDOR_Rkws59dh0Y: reject non-integer pid
                # values outright rather than coercing with ``int()`` —
                # ``int(True)`` yields 1, ``int(3.9)`` yields 3, either
                # of which could signal the wrong process in
                # ``daemon stop``. An externally-written or malformed
                # record with a boolean or float pid is corrupt; the
                # code-path contract is "treat corrupt as None".
                #
                # ``isinstance(v, bool)`` first because ``bool`` is a
                # subclass of ``int`` in Python (``isinstance(True,
                # int)`` is True).
                raw_pid = data["pid"]
                if isinstance(raw_pid, bool) or not isinstance(raw_pid, int):
                    raise TypeError(f"pid field must be int, got {type(raw_pid).__name__}")
                pid = raw_pid
                ct_raw = data.get("create_time")
                if ct_raw is None:
                    create_time: float | None = None
                else:
                    # Codex P2: reject non-finite ``create_time`` values
                    # (NaN, +Inf, -Inf). ``float("nan")`` parses cleanly
                    # from JSON strings like ``"nan"`` or from a
                    # malformed numeric literal, but propagating NaN
                    # into ``is_running`` silently defeats the F2
                    # recycling check: ``abs(actual - NaN) > tolerance``
                    # is ALWAYS False (any comparison with NaN is
                    # False), so a recycled PID would be reported as
                    # the original daemon. Inf makes the subtraction
                    # overflow and the comparison either always True
                    # (False-positive recycling mismatch) or NaN again.
                    # Treat any non-finite value as corrupt.
                    create_time = float(ct_raw)
                    if not math.isfinite(create_time):
                        raise ValueError(f"create_time must be finite, got {create_time!r}")
                return PidRecord(pid=pid, create_time=create_time)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            # Distinguish "valid JSON with malformed pid field" from
            # "invalid JSON, try legacy int" so an operator debugging a
            # corrupt PID file can tell the two failure modes apart.
            logger.debug(
                "read_pid_record: JSON parse failed for %s (%s); "
                "falling through to legacy int parse",
                pid_file,
                exc,
            )

        # Fall through to legacy integer format.
        try:
            return PidRecord(pid=int(content), create_time=None)
        except ValueError:
            logger.warning("PID file %s contains unparsable content", pid_file)
            return None

    def is_running(self, pid_file: Path) -> bool:
        """Check whether the process recorded in a PID file is alive.

        F2 (hardening roadmap #159): for records that include
        ``create_time`` (JSON format, from :meth:`write_pid_record`),
        the start-time of the live process is compared against the
        recorded value — a mismatch means the PID was recycled by the
        OS after the original daemon died, and we return False.

        For legacy text-only PID files (no ``create_time``), falls back
        to the pre-F2 behaviour: ``psutil.pid_exists(pid)``. This is a
        documented degradation — PID recycling is not detected for
        legacy files. Run ``write_pid_record`` on daemon startup to
        opt into recycling protection.

        ``psutil.pid_exists()`` uses OS-native handle checking
        (OpenProcess on Windows, /proc on Linux) and is safe on all
        platforms. ``os.kill(pid, 0)`` is not used because on Windows
        signal 0 maps to CTRL_C_EVENT.

        Args:
            pid_file: Path to the PID file.

        Returns:
            True if the PID file exists, the recorded process is
            alive, and (for F2 records) the recorded start-time
            matches the running process's start-time. False otherwise.
        """
        record = self.read_pid_record(pid_file)
        if record is None:
            return False

        if not psutil.pid_exists(record.pid):
            return False

        # Legacy format — no recycling detection.
        if record.create_time is None:
            return True

        # F2 recycling check: verify the PID points at the same process
        # that wrote the record.
        try:
            actual_create_time = psutil.Process(record.pid).create_time()
        except psutil.NoSuchProcess:
            # Process disappeared between pid_exists and create_time —
            # it's really gone, treat as not running.
            return False
        except psutil.AccessDenied:
            # Codex P2 PRRT_kwDOR_Rkws59dh0X: in hardened deployments
            # (cross-user checks with restricted ``/proc`` visibility,
            # hidepid=2, seccomp-bpf sandboxes, etc.) we can't read
            # ``create_time`` but ``pid_exists`` already confirmed the
            # process is alive. Returning False here reports a running
            # daemon as stopped — a regression from the pre-F2
            # ``psutil.pid_exists``-only fallback. Degrade gracefully:
            # without create_time we lose recycling detection (same
            # degradation as the legacy-format branch above), but
            # we correctly report liveness.
            logger.debug(
                "PID %d create_time unreadable (AccessDenied); "
                "falling back to PID-liveness only (no recycling check)",
                record.pid,
            )
            return True

        if abs(actual_create_time - record.create_time) > _CREATE_TIME_TOLERANCE_S:
            logger.warning(
                "PID %d was recycled: recorded create_time=%f but running process "
                "create_time=%f; treating as not running (F2 protection).",
                record.pid,
                record.create_time,
                actual_create_time,
            )
            return False

        return True
