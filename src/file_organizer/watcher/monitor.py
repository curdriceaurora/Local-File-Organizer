"""File system monitor for real-time directory watching.

Provides the FileMonitor class that manages watchdog observers,
coordinates event handling, and supports dynamic directory management.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver
from watchdog.observers.polling import PollingObserver

from .config import WatcherConfig
from .handler import FileEventHandler
from .queue import EventQueue, EventType, FileEvent

logger = logging.getLogger(__name__)


class FileMonitor:
    """Real-time file system monitor using watchdog.

    Manages one or more watched directories, applies filtering and
    debouncing through FileEventHandler, and queues events for
    batch processing.

    Example:
        >>> config = WatcherConfig(
        ...     watch_directories=[Path("/tmp/watched")],
        ...     debounce_seconds=1.0,
        ... )
        >>> monitor = FileMonitor(config)
        >>> monitor.start()
        >>> # ... files are created/modified ...
        >>> events = monitor.get_events(max_size=5)
        >>> monitor.stop()
    """

    def __init__(
        self,
        config: WatcherConfig | None = None,
        queue: EventQueue | None = None,
    ) -> None:
        """Initialize the file monitor.

        Args:
            config: Watcher configuration. Uses defaults if None.
            queue: Event queue for collected events. Creates one if None.
        """
        self.config = config or WatcherConfig()
        self.queue = queue or EventQueue()
        self.handler = FileEventHandler(self.config, self.queue)

        self._observer: BaseObserver | None = None
        self._watches: dict[str, object] = {}
        self._lock = threading.Lock()
        self._running = False
        self._observer_type: str = "none"  # Track which observer is in use

    def start(self) -> None:
        """Start monitoring all configured directories.

        Creates and starts the watchdog observer, scheduling watches
        for each directory in the configuration. Implements graceful fallback
        from native observers (FSEvents, Inotify, etc.) to PollingObserver
        when the platform-specific observer fails to initialize.

        Raises:
            RuntimeError: If the monitor is already running.
            FileNotFoundError: If a watch directory does not exist.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("FileMonitor is already running")

            # Try native observer first, fallback to polling if it fails
            try:
                self._observer = Observer()
                self._observer_type = "native"
                logger.info(
                    "Using native file system observer "
                    "(FSEvents/Inotify/Windows)"
                )
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "Native observer failed to initialize: %s. "
                    "Falling back to polling observer.",
                    e,
                )
                self._observer = PollingObserver(timeout=1.0)
                self._observer_type = "polling"
                logger.info("Using polling observer for file system monitoring")

            self._observer.daemon = True

            # Schedule all configured directories
            for directory in self.config.watch_directories:
                self._schedule_directory(directory, self.config.recursive)

            self._observer.start()
            self._running = True
            logger.info(
                "FileMonitor started (%s observer), watching %d directories",
                self._observer_type,
                len(self._watches),
            )

    def stop(self) -> None:
        """Stop monitoring and clean up resources.

        Stops the watchdog observer and clears all watch state.
        Safe to call even if the monitor is not running.
        """
        with self._lock:
            if not self._running or self._observer is None:
                return

            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
            self._watches.clear()
            self._running = False
            logger.info("FileMonitor stopped")

    def add_directory(self, path: Path, recursive: bool = True) -> None:
        """Add a directory to be monitored.

        Can be called while the monitor is running to dynamically
        add new directories.

        Args:
            path: Directory path to monitor.
            recursive: Whether to monitor subdirectories.

        Raises:
            FileNotFoundError: If the directory does not exist.
            ValueError: If the directory is already being watched.
        """
        path = Path(path).resolve()
        path_key = str(path)

        with self._lock:
            if path_key in self._watches:
                raise ValueError(f"Directory already watched: {path}")

            if self._running and self._observer is not None:
                self._schedule_directory(path, recursive)
            else:
                # If not running, just add to config for when start() is called
                if path not in self.config.watch_directories:
                    self.config.watch_directories.append(path)

            logger.info("Added watch directory: %s (recursive=%s)", path, recursive)

    def remove_directory(self, path: Path) -> None:
        """Remove a directory from monitoring.

        Args:
            path: Directory path to stop monitoring.

        Raises:
            ValueError: If the directory is not being watched.
        """
        path = Path(path).resolve()
        path_key = str(path)

        with self._lock:
            if path_key not in self._watches:
                raise ValueError(f"Directory not being watched: {path}")

            if self._running and self._observer is not None:
                watch = self._watches[path_key]
                self._observer.unschedule(watch)

            del self._watches[path_key]

            # Also remove from config
            try:
                self.config.watch_directories.remove(path)
            except ValueError:
                pass

            logger.info("Removed watch directory: %s", path)

    def get_events(self, max_size: int | None = None) -> list[FileEvent]:
        """Retrieve queued events in a batch.

        Args:
            max_size: Maximum number of events to return.
                Defaults to config.batch_size.

        Returns:
            List of FileEvent instances.
        """
        batch_size = max_size if max_size is not None else self.config.batch_size
        return self.queue.dequeue_batch(batch_size)

    def get_events_blocking(
        self,
        max_size: int | None = None,
        timeout: float | None = None,
    ) -> list[FileEvent]:
        """Retrieve queued events, blocking until at least one is available.

        Args:
            max_size: Maximum number of events to return.
                Defaults to config.batch_size.
            timeout: Maximum seconds to wait. None means wait forever.

        Returns:
            List of FileEvent instances. May be empty if timeout expired.
        """
        batch_size = max_size if max_size is not None else self.config.batch_size
        return self.queue.dequeue_batch_blocking(batch_size, timeout=timeout)

    def on_created(self, callback: callable) -> None:
        """Register a callback for file creation events.

        Args:
            callback: Callable accepting a FileEvent argument.
        """
        self.handler.register_callback(EventType.CREATED, callback)

    def on_modified(self, callback: callable) -> None:
        """Register a callback for file modification events.

        Args:
            callback: Callable accepting a FileEvent argument.
        """
        self.handler.register_callback(EventType.MODIFIED, callback)

    def on_deleted(self, callback: callable) -> None:
        """Register a callback for file deletion events.

        Args:
            callback: Callable accepting a FileEvent argument.
        """
        self.handler.register_callback(EventType.DELETED, callback)

    def on_moved(self, callback: callable) -> None:
        """Register a callback for file move events.

        Args:
            callback: Callable accepting a FileEvent argument.
        """
        self.handler.register_callback(EventType.MOVED, callback)

    @property
    def is_running(self) -> bool:
        """Return True if the monitor is currently active."""
        return self._running

    @property
    def watched_directories(self) -> list[Path]:
        """Return list of currently watched directory paths."""
        with self._lock:
            return [Path(p) for p in self._watches]

    @property
    def event_count(self) -> int:
        """Return the number of events currently in the queue."""
        return self.queue.size

    @property
    def observer_type(self) -> str:
        """Return the type of observer currently in use.

        Possible values:
            - 'none': Observer not yet initialized
            - 'native': Platform-native observer (FSEvents, Inotify, etc.)
            - 'polling': Polling-based observer (fallback)
        """
        return self._observer_type

    def _schedule_directory(self, path: Path, recursive: bool) -> None:
        """Schedule a directory watch with the observer.

        Must be called while holding self._lock.

        Args:
            path: Directory path to watch.
            recursive: Whether to watch subdirectories.

        Raises:
            FileNotFoundError: If the directory does not exist.
        """
        path = Path(path).resolve()
        path_key = str(path)

        if not path.is_dir():
            raise FileNotFoundError(f"Watch directory does not exist: {path}")

        if self._observer is not None:
            watch = self._observer.schedule(self.handler, str(path), recursive=recursive)
            self._watches[path_key] = watch
