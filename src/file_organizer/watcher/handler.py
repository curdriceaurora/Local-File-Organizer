"""
File system event handler with debouncing and filtering.

Extends watchdog's FileSystemEventHandler to add debounce logic,
configurable pattern filtering, and event queuing for batch processing.
"""

from __future__ import annotations

import logging
import threading
import time
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
    """
    Watchdog event handler with debouncing, filtering, and queue integration.

    Receives raw file system events from watchdog observers, applies
    configurable filtering (exclude patterns, file type whitelist),
    debounces rapid successive events on the same file, and enqueues
    the deduplicated events for batch processing.

    Attributes:
        config: Watcher configuration controlling filter and debounce behavior.
        queue: Event queue where processed events are placed.
    """

    def __init__(self, config: WatcherConfig, queue: EventQueue) -> None:
        """
        Initialize the event handler.

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
        self._on_created_callbacks: list[callable] = []
        self._on_modified_callbacks: list[callable] = []
        self._on_deleted_callbacks: list[callable] = []
        self._on_moved_callbacks: list[callable] = []

    def on_created(self, event: FileSystemEvent) -> None:
        """
        Handle file/directory creation events.

        Args:
            event: The watchdog creation event.
        """
        self._handle_event(event, EventType.CREATED)

    def on_modified(self, event: FileSystemEvent) -> None:
        """
        Handle file modification events.

        Args:
            event: The watchdog modification event.
        """
        self._handle_event(event, EventType.MODIFIED)

    def on_deleted(self, event: FileSystemEvent) -> None:
        """
        Handle file/directory deletion events.

        Args:
            event: The watchdog deletion event.
        """
        self._handle_event(event, EventType.DELETED)

    def on_moved(self, event: FileSystemEvent) -> None:
        """
        Handle file/directory move events.

        Args:
            event: The watchdog move event.
        """
        dest_path: Path | None = None
        if hasattr(event, "dest_path") and event.dest_path is not None:
            dest_path = Path(event.dest_path)
        self._handle_event(event, EventType.MOVED, dest_path=dest_path)

    def register_callback(
        self,
        event_type: EventType,
        callback: callable,
    ) -> None:
        """
        Register a callback for a specific event type.

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
        """
        Central event processing pipeline: filter, debounce, enqueue.

        Args:
            event: The raw watchdog event.
            event_type: Classified event type.
            dest_path: Destination path for move events.
        """
        path = Path(event.src_path)
        is_directory = isinstance(event, (DirCreatedEvent, DirDeletedEvent, DirMovedEvent))

        # Skip directory events for non-directory-aware processing
        # (still allow them through if they pass filters)
        if not is_directory and not self.config.should_include_file(path):
            logger.debug("Filtered out event for: %s", path)
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

    def _should_process(self, path_key: str) -> bool:
        """
        Check if an event for this path should be processed based on debounce timing.

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
        """
        Invoke registered callbacks for the given event type.

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
