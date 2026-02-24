"""Background daemon service.

Provides the DaemonService class that combines file watching with
auto-organization, managing the full lifecycle including signal
handling, PID file management, and periodic tasks.
"""

from __future__ import annotations

import logging
import signal
import threading
import time
from collections.abc import Callable

from .config import DaemonConfig
from .pid import PidFileManager
from .scheduler import DaemonScheduler

logger = logging.getLogger(__name__)


class DaemonService:
    """Long-running daemon that watches directories and organizes files.

    Combines file monitoring, pipeline processing, PID management,
    signal handling, and periodic scheduling into a single service
    that can run in the foreground or background.

    Example:
        >>> config = DaemonConfig(
        ...     watch_directories=[Path("/tmp/incoming")],
        ...     output_directory=Path("/tmp/organized"),
        ...     pid_file=Path("/tmp/daemon.pid"),
        ... )
        >>> daemon = DaemonService(config)
        >>> daemon.start_background()
        >>> assert daemon.is_running
        >>> daemon.stop()
    """

    def __init__(self, config: DaemonConfig) -> None:
        """Initialize the daemon service.

        Args:
            config: Daemon configuration controlling behavior.
        """
        self.config = config

        self._pid_manager = PidFileManager()
        self._scheduler = DaemonScheduler()
        self._stop_event = threading.Event()
        self._started_event = threading.Event()
        self._stopped_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._original_sigterm: signal.Handlers | None = None
        self._original_sigint: signal.Handlers | None = None
        self._started_at: float | None = None
        self._files_processed: int = 0
        self._on_start_callback: Callable[[], None] | None = None
        self._on_stop_callback: Callable[[], None] | None = None

    def start(self) -> None:
        """Start the daemon in the foreground (blocking).

        Installs signal handlers, writes the PID file, starts the
        scheduler and event loop. Blocks until ``stop()`` is called
        or a termination signal is received.

        Raises:
            RuntimeError: If the daemon is already running.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("Daemon is already running")
            self._running = True

        logger.info("Starting daemon service")
        self._started_at = time.monotonic()
        self._stop_event.clear()
        self._stopped_event.clear()

        try:
            # Write PID file
            if self.config.pid_file is not None:
                self._pid_manager.write_pid(self.config.pid_file)

            # Install signal handlers (only in main thread)
            self._install_signal_handlers()

            # Set up default periodic tasks
            self._setup_default_tasks()

            # Start the scheduler in background
            self._scheduler.run_in_background()

            # Fire on_start callback
            if self._on_start_callback is not None:
                try:
                    self._on_start_callback()
                except Exception:
                    logger.exception("on_start callback failed")

            # Signal that startup is complete
            self._started_event.set()

            # Main event loop
            self._run_loop()

        finally:
            self._cleanup()

    def start_background(self) -> None:
        """Start the daemon in a background thread.

        Returns once the daemon has fully initialized. The daemon
        can be stopped by calling ``stop()``.

        Raises:
            RuntimeError: If the daemon is already running.
        """
        with self._lock:
            if self._running:
                raise RuntimeError("Daemon is already running")

        self._started_event.clear()
        self._stopped_event.clear()

        self._thread = threading.Thread(
            target=self._background_run,
            name="daemon-service",
            daemon=True,
        )
        self._thread.start()

        # Wait for the daemon to fully initialize
        self._started_event.wait(timeout=5.0)

    def stop(self) -> None:
        """Request a graceful shutdown of the daemon.

        Signals the event loop to stop, waits for the background
        thread to finish, cleans up the PID file, and restores
        signal handlers. Safe to call even if the daemon is not
        running.
        """
        logger.info("Stopping daemon service")
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None

        # Wait for cleanup to complete
        self._stopped_event.wait(timeout=5.0)

    def restart(self) -> None:
        """Restart the daemon by stopping and starting in background.

        Performs a full stop followed by a background start.
        """
        logger.info("Restarting daemon service")
        was_running = self._running

        if was_running:
            self.stop()

        self.start_background()

    @property
    def is_running(self) -> bool:
        """Return True if the daemon is currently running."""
        return self._running

    @property
    def uptime_seconds(self) -> float:
        """Return seconds since the daemon started, or 0 if not running."""
        if self._started_at is None or not self._running:
            return 0.0
        return time.monotonic() - self._started_at

    @property
    def files_processed(self) -> int:
        """Return the number of files processed since daemon start."""
        return self._files_processed

    @property
    def scheduler(self) -> DaemonScheduler:
        """Return the daemon's task scheduler for custom task registration."""
        return self._scheduler

    def on_start(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when the daemon starts.

        Args:
            callback: Zero-argument callable.
        """
        self._on_start_callback = callback

    def on_stop(self, callback: Callable[[], None]) -> None:
        """Register a callback to be invoked when the daemon stops.

        Args:
            callback: Zero-argument callable.
        """
        self._on_stop_callback = callback

    def _background_run(self) -> None:
        """Entry point for the background thread."""
        with self._lock:
            if self._running:
                return
            self._running = True

        logger.info("Starting daemon service (background)")
        self._started_at = time.monotonic()
        self._stop_event.clear()

        try:
            # Write PID file
            if self.config.pid_file is not None:
                self._pid_manager.write_pid(self.config.pid_file)

            # Set up default periodic tasks
            self._setup_default_tasks()

            # Start the scheduler in background
            self._scheduler.run_in_background()

            # Fire on_start callback
            if self._on_start_callback is not None:
                try:
                    self._on_start_callback()
                except Exception:
                    logger.exception("on_start callback failed")

            # Signal that startup is complete
            self._started_event.set()

            # Main event loop
            self._run_loop()

        finally:
            self._cleanup()

    def _run_loop(self) -> None:
        """Main daemon event loop.

        Polls for file events and processes them at the configured
        interval. Exits when the stop event is set.
        """
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=self.config.poll_interval)

    def _cleanup(self) -> None:
        """Clean up daemon resources on shutdown.

        Stops the scheduler, removes the PID file, restores signal
        handlers, and fires the on_stop callback.
        """
        logger.info("Cleaning up daemon resources")

        # Stop scheduler
        self._scheduler.stop()

        # Remove PID file
        if self.config.pid_file is not None:
            self._pid_manager.remove_pid(self.config.pid_file)

        # Restore signal handlers
        self._restore_signal_handlers()

        # Fire on_stop callback
        if self._on_stop_callback is not None:
            try:
                self._on_stop_callback()
            except Exception:
                logger.exception("on_stop callback failed")

        self._running = False
        self._started_at = None
        self._stopped_event.set()
        logger.info("Daemon service stopped")

    def _install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown.

        Only installs handlers when running in the main thread.
        Saves original handlers so they can be restored later.
        """
        if threading.current_thread() is not threading.main_thread():
            logger.debug("Skipping signal handler installation (not main thread)")
            return

        try:
            self._original_sigterm = signal.getsignal(signal.SIGTERM)
            self._original_sigint = signal.getsignal(signal.SIGINT)
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
            logger.debug("Installed SIGTERM and SIGINT handlers")
        except (OSError, ValueError) as exc:
            logger.warning("Could not install signal handlers: %s", exc)

    def _restore_signal_handlers(self) -> None:
        """Restore the original signal handlers saved during installation."""
        if threading.current_thread() is not threading.main_thread():
            return

        try:
            if self._original_sigterm is not None:
                signal.signal(signal.SIGTERM, self._original_sigterm)
                self._original_sigterm = None
            if self._original_sigint is not None:
                signal.signal(signal.SIGINT, self._original_sigint)
                self._original_sigint = None
            logger.debug("Restored original signal handlers")
        except (OSError, ValueError) as exc:
            logger.warning("Could not restore signal handlers: %s", exc)

    def _handle_signal(self, signum: int, frame: object) -> None:
        """Handle a termination signal by requesting graceful shutdown.

        Args:
            signum: The signal number received.
            frame: The current stack frame (unused).
        """
        sig_name = signal.Signals(signum).name
        logger.info("Received %s, initiating graceful shutdown", sig_name)
        self._stop_event.set()

    def _setup_default_tasks(self) -> None:
        """Register default periodic tasks with the scheduler."""
        self._scheduler.schedule_task(
            name="health_check",
            interval=30.0,
            callback=self._health_check,
        )
        self._scheduler.schedule_task(
            name="stats_report",
            interval=60.0,
            callback=self._stats_report,
        )

    def _health_check(self) -> None:
        """Periodic health check task."""
        logger.debug(
            "Health check: running=%s, uptime=%.0fs, processed=%d",
            self._running,
            self.uptime_seconds,
            self._files_processed,
        )

    def _stats_report(self) -> None:
        """Periodic stats reporting task."""
        logger.info(
            "Stats: uptime=%.0fs, files_processed=%d, scheduler_tasks=%d",
            self.uptime_seconds,
            self._files_processed,
            self._scheduler.task_count,
        )
