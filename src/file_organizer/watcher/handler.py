"""File system event handler with debouncing and filtering.

Extends watchdog's FileSystemEventHandler to add debounce logic,
configurable pattern filtering, and event queuing for batch processing.
"""

from __future__ import annotations

import logging
import os
import stat
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from watchdog.events import (
    DirCreatedEvent,
    DirDeletedEvent,
    DirMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)

from .config import WatcherConfig
from .queue import EventQueue, EventType, FileEvent

logger = logging.getLogger(__name__)


class FileEventHandler(FileSystemEventHandler):
    """Watchdog event handler with debouncing, filtering, and queue integration.

    Receives raw file system events from watchdog observers, applies
    configurable filtering (exclude patterns, file type whitelist),
    debounces rapid successive events on the same file, and enqueues
    the deduplicated events for batch processing.

    Attributes:
        config: Watcher configuration controlling filter and debounce behavior.
        queue: Event queue where processed events are placed.
    """

    def __init__(self, config: WatcherConfig, queue: EventQueue) -> None:
        """Initialize the event handler.

        Args:
            config: Watcher configuration for filtering and debouncing.
            queue: Event queue for downstream processing.
        """
        super().__init__()
        self.config = config
        self.queue = queue

        # Debounce state: maps file path -> last event timestamp (monotonic)
        self._last_event_times: dict[str, float] = {}
        self._debounce_lock = threading.Lock()

        # Callback hooks (optional, for direct notification without queue)
        self._on_created_callbacks: list[Callable[..., object]] = []
        self._on_modified_callbacks: list[Callable[..., object]] = []
        self._on_deleted_callbacks: list[Callable[..., object]] = []
        self._on_moved_callbacks: list[Callable[..., object]] = []

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file/directory creation events.

        Args:
            event: The watchdog creation event.
        """
        self._handle_event(event, EventType.CREATED)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events.

        Args:
            event: The watchdog modification event.
        """
        self._handle_event(event, EventType.MODIFIED)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file/directory deletion events.

        Args:
            event: The watchdog deletion event.
        """
        self._handle_event(event, EventType.DELETED)

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file/directory move events.

        Args:
            event: The watchdog move event.
        """
        dest_path: Path | None = None
        raw_dest = getattr(event, "dest_path", None)
        if raw_dest is not None:
            dest_path = Path(os.fsdecode(raw_dest))
        self._handle_event(event, EventType.MOVED, dest_path=dest_path)

    def register_callback(
        self,
        event_type: EventType,
        callback: Callable[..., object],
    ) -> None:
        """Register a callback for a specific event type.

        Callbacks are invoked after filtering and debouncing, in addition
        to the event being placed on the queue.

        Args:
            event_type: The event type to listen for.
            callback: A callable that accepts a single FileEvent argument.
        """
        callbacks_map = {
            EventType.CREATED: self._on_created_callbacks,
            EventType.MODIFIED: self._on_modified_callbacks,
            EventType.DELETED: self._on_deleted_callbacks,
            EventType.MOVED: self._on_moved_callbacks,
        }
        callbacks_map[event_type].append(callback)

    def _handle_event(
        self,
        event: FileSystemEvent,
        event_type: EventType,
        dest_path: Path | None = None,
    ) -> None:
        """Central event processing pipeline: filter, debounce, enqueue.

        Args:
            event: The raw watchdog event.
            event_type: Classified event type.
            dest_path: Destination path for move events.
        """
        src_path = Path(os.fsdecode(event.src_path))
        is_directory = isinstance(event, (DirCreatedEvent, DirDeletedEvent, DirMovedEvent))

        # For MOVED events the destination is the live, to-be-organized file;
        # the source no longer exists. Use the destination as the effective path
        # for filtering, debounce, the symlink/containment guard, and
        # FileEvent.path so the downstream watch loop processes (and we validate)
        # the file's new location rather than the missing source. Fall back to
        # the source when no destination is supplied.
        path = dest_path if dest_path is not None else src_path

        # Skip directory events for non-directory-aware processing
        # (still allow them through if they pass filters)
        if not is_directory and not self.config.should_include_file(path):
            logger.debug("Filtered out event for: %s", path)
            return

        # Symlink / containment hardening (WP-2.3, #1228): refuse events whose
        # path is a symlink (at any component under the watched root) or resolves
        # outside the watched roots, failing closed on any resolution error
        # (e.g. symlink loops).
        if not self._is_event_path_allowed(
            path, allow_missing_leaf=event_type is EventType.DELETED
        ):
            logger.warning("Skipping event for unsafe/out-of-root path: %s", path)
            return

        # Apply debouncing
        if not self._should_process(str(path)):
            logger.debug("Debounced event for: %s", path)
            return

        # Create the FileEvent
        file_event = FileEvent(
            event_type=event_type,
            path=path,
            timestamp=datetime.now(UTC),
            is_directory=is_directory,
            dest_path=dest_path,
        )

        # Enqueue
        self.queue.enqueue(file_event)
        logger.info("Queued %s event for: %s", event_type.value, path)

        # Fire callbacks
        self._fire_callbacks(event_type, file_event)

    def _watch_roots(self) -> list[tuple[Path, Path]]:
        """Return ``(original, resolved)`` pairs for each configured watch dir.

        ``original`` is the path as configured (which may itself be a symlinked
        directory the user deliberately pointed the watcher at); ``resolved`` is
        its canonical form. The per-component symlink walk in
        :meth:`_is_event_path_allowed` aligns on whichever form the event path is
        expressed under, so events under a symlinked watch root still flow while
        a symlinked *ancestor below* the root is still caught.

        Roots whose canonicalization *raises* (symlink loop, OS-level resolution
        failure) are dropped rather than aborting the whole check; a merely
        missing root is **not** dropped because ``Path.resolve()`` is non-strict.
        An empty result means no containment boundary is configured (e.g. a
        handler used standalone), in which case :meth:`_is_event_path_allowed`
        does not block — there is nothing to contain the event against.
        """
        pairs: list[tuple[Path, Path]] = []
        for directory in self.config.watch_directories:
            original = Path(directory)
            try:
                resolved = original.resolve()
            except (OSError, RuntimeError):  # pragma: no cover - defensive
                continue
            pairs.append((original, resolved))
        return pairs

    def _is_event_path_allowed(self, path: Path, *, allow_missing_leaf: bool) -> bool:
        """Return True if *path* is safe to process under the watched roots.

        Fail-closed symlink/containment guard (WP-2.3, #1228):

        - **resolve-loop handling**: the path is canonicalized with
          ``Path.resolve()``; a symlink loop or other resolution error raises
          ``OSError``/``RuntimeError`` and is treated as unsafe (skip).
        - **containment**: the resolved path must live inside one of the
          resolved watch roots; anything outside is refused.
        - **per-component symlink rejection**: every component from the matched
          root down to the leaf is ``lstat``-ed; a symlink anywhere along the
          way is refused. Checking only the leaf would let a symlinked
          *ancestor* that currently resolves back under the root (e.g.
          ``root/link/doc.txt`` with ``link -> root/real``) pass containment —
          the original symlink-bearing path would then be enqueued and a later
          downstream open could be raced by retargeting the link outside the
          root (TOCTOU). A missing *final* component ends the walk as safe only
          when ``allow_missing_leaf`` is set (a DELETED event, where the leaf is
          expected to be gone); for a live event, or for any missing
          *intermediate* component, the walk fails closed — a vanished component
          can't be proven symlink-free and the name could be recreated as an
          out-of-root symlink before downstream opens it.

        The walk is anchored on whichever root form (original or resolved) the
        event path is expressed under, so it works for events under a symlinked
        watch root *and* watchdog's canonical-prefixed paths. If the path cannot
        be aligned to either form the check **fails closed** rather than allowing
        the path unchecked (a non-canonical prefix must not bypass the walk).

        When the handler has **no** watch directories configured the method
        returns True (no boundary to enforce) so a standalone handler keeps
        working. But if directories *are* configured and none of them resolve,
        it **fails closed** — the guard must not be disablable by making a
        configured root unresolvable.
        """
        roots = self._watch_roots()
        if not roots:
            # Distinguish a genuinely unconfigured handler (no watch roots → no
            # boundary to enforce, allow) from one whose roots *all* failed to
            # resolve (e.g. a configured root replaced by a symlink loop). The
            # latter must fail closed, else the guard could be disabled simply by
            # making a configured root unresolvable.
            return not self.config.watch_directories

        try:
            resolved = path.resolve()
        except (OSError, RuntimeError):
            return False  # fail closed on symlink loops / resolution failures

        match = next(
            (
                (original_root, resolved_root)
                for (original_root, resolved_root) in roots
                if resolved == resolved_root or resolved.is_relative_to(resolved_root)
            ),
            None,
        )
        if match is None:
            return False  # resolves outside every watch root
        original_root, resolved_root = match

        # Align the per-component walk on whichever root form prefixes the event
        # path. The resolved root never has symlinks in it; the original root may
        # *be* a (trusted) symlinked directory, so we never lstat the root
        # itself — only the components below it.
        for base in (original_root, resolved_root):
            try:
                relative = path.relative_to(base)
            except ValueError:
                continue
            current = base
            parts = relative.parts
            for index, part in enumerate(parts):
                current = current / part
                try:
                    if stat.S_ISLNK(os.lstat(current).st_mode):
                        return False
                except FileNotFoundError:
                    # A missing *final* component is benign only for a DELETED
                    # event (the leaf is expected to be gone and nothing live is
                    # read downstream). For a live CREATED/MODIFIED/MOVED event a
                    # vanished leaf — or any vanished intermediate component —
                    # can't be proven symlink-free: the pathname could be
                    # recreated as an out-of-root symlink before the watch loop
                    # opens it. Fail closed in those cases.
                    return allow_missing_leaf and index == len(parts) - 1
                except OSError:
                    return False  # fail closed on any other stat error
            return True

        # The event path is under neither root form lexically — cannot prove it
        # is symlink-free, so refuse rather than allow unchecked.
        return False

    def _should_process(self, path_key: str) -> bool:
        """Check if an event for this path should be processed based on debounce timing.

        Uses monotonic time for reliable interval measurement regardless
        of system clock adjustments.

        Args:
            path_key: String representation of the file path.

        Returns:
            True if the event should be processed, False if within debounce window.
        """
        now = time.monotonic()

        with self._debounce_lock:
            last_time = self._last_event_times.get(path_key)

            if last_time is not None:
                elapsed = now - last_time
                if elapsed < self.config.debounce_seconds:
                    return False

            self._last_event_times[path_key] = now
            return True

    def _fire_callbacks(self, event_type: EventType, file_event: FileEvent) -> None:
        """Invoke registered callbacks for the given event type.

        Args:
            event_type: The type of event that occurred.
            file_event: The processed file event to pass to callbacks.
        """
        callbacks_map = {
            EventType.CREATED: self._on_created_callbacks,
            EventType.MODIFIED: self._on_modified_callbacks,
            EventType.DELETED: self._on_deleted_callbacks,
            EventType.MOVED: self._on_moved_callbacks,
        }

        for callback in callbacks_map.get(event_type, []):
            try:
                callback(file_event)
            except Exception:
                logger.exception("Error in %s callback for %s", event_type.value, file_event.path)

    def clear_debounce_state(self) -> None:
        """Clear all debounce tracking state."""
        with self._debounce_lock:
            self._last_event_times.clear()

    @property
    def pending_paths(self) -> int:
        """Return the number of paths being tracked for debouncing."""
        with self._debounce_lock:
            return len(self._last_event_times)
