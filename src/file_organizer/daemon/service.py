"""Background daemon service.

Provides the DaemonService class that combines file watching with
auto-organization, managing the full lifecycle including signal
handling, PID file management, and periodic tasks.
"""

from __future__ import annotations

import logging
import os
import select
import signal
import threading
import time
from collections.abc import Callable

from .config import DaemonConfig
from .pid import PidFileManager
from .scheduler import DaemonScheduler

logger = logging.getLogger(__name__)

# F4: minimum interval between signal-write-failure WARNINGs. At the
# default poll_interval=0.05s a saturated pipe would log ~20 times per
# second without rate limiting — a single shutdown-pipe race could bury
# the rest of the log. 1.0s keeps the signal actionable without flooding.
_SIGNAL_LOG_MIN_INTERVAL_S = 1.0

# Timeout for joining the background thread after a startup failure, so
# start_background() doesn't raise while _cleanup() is still tearing the
# daemon down (#1323, finding 4). Module-level so tests can shrink it via
# monkeypatch instead of waiting out the real timeout.
_STARTUP_JOIN_TIMEOUT_S = 10.0


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
        self._sig_wakeup_r: int | None = None
        self._sig_wakeup_w: int | None = None
        # F4 (hardening roadmap #159): counter bumped by the signal
        # handler on ``os.write`` failure (pipe full / closed). The
        # signal handler can't call logger (not async-signal-safe);
        # the run loop reads this counter on each iteration and logs
        # a warning if it changed. Simple ``int`` read/write is
        # atomic on CPython under the GIL.
        self._signal_write_failures = 0
        self._last_logged_write_failures = 0
        # F4 rate-limiting: the run loop polls every ``poll_interval``
        # (default 0.05s). When the pipe is saturated or closed the
        # counter increments on every fired signal, which could be
        # dozens per second. Suppress WARNING emits to at most one per
        # ``_SIGNAL_LOG_MIN_INTERVAL_S`` so the log remains useful.
        self._last_signal_log_time = 0.0
        self._started_at: float | None = None
        # Narrowly typed to Exception (not BaseException): only the
        # ``except Exception`` clause in ``_background_run`` assigns here,
        # so the annotation reflects what is actually captured. A
        # BaseException subtype (SystemExit, KeyboardInterrupt) raised
        # during startup is NOT recorded here and will NOT be re-raised by
        # start_background() — see that method's docstring.
        self._startup_error: Exception | None = None
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
            # Write PID file — F2 record format (pid + create_time) so
            # ``is_running`` can detect PID recycling after crash.
            if self.config.pid_file is not None:
                self._pid_manager.write_pid_record(self.config.pid_file)

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
            Exception: Whatever the background thread raised while
                writing the PID file, setting up tasks, or starting the
                scheduler — startup failures are re-raised here rather
                than left silently swallowed in the background thread
                (#1323, finding 4). Does NOT cover the ``on_start``
                callback: that is invoked inside its own pre-existing
                ``try/except Exception`` that logs and swallows on
                failure (a broken on_start callback should not abort the
                daemon), so callback failures are never re-raised here.
                Also does not cover BaseException subtypes (e.g.
                ``SystemExit``, ``KeyboardInterrupt``) raised during
                startup — only ``Exception`` subclasses are captured.
        """
        with self._lock:
            if self._running or (self._thread is not None and self._thread.is_alive()):
                raise RuntimeError("Daemon is already running")
            if self._thread is not None and not self._thread.is_alive():
                self._thread = None

            self._stop_event.clear()
            self._started_event.clear()
            self._stopped_event.clear()
            self._startup_error = None

            # Set _running = True while holding lock to prevent race condition
            # where two threads both pass the check above before _running is set
            self._running = True
            self._thread = threading.Thread(
                target=self._background_run,
                name="daemon-service",
                daemon=True,
            )
            try:
                self._thread.start()
            except Exception:
                # Reset state on thread creation failure
                self._running = False
                self._thread = None
                raise

        # Wait for the daemon to fully initialize
        self._started_event.wait(timeout=5.0)

        if self._startup_error is not None:
            error = self._startup_error
            self._startup_error = None
            # The background thread sets _started_event from inside the
            # inner `finally` *before* unwinding through the outer
            # `finally` (`_cleanup()`), so cleanup may still be in flight
            # here. Join it so `is_running` is reliably False and the PID
            # file is gone by the time this raises — callers must not
            # observe a half-torn-down daemon after the exception.
            if self._thread is not None:
                self._thread.join(timeout=_STARTUP_JOIN_TIMEOUT_S)
                if self._thread.is_alive():
                    # Cleanup is still running past the timeout (e.g. a
                    # slow on_stop callback or scheduler shutdown). Do NOT
                    # discard the thread handle — leave it set so the
                    # is_alive() guard at the top of this method and
                    # stop()'s own join() can still detect/wait for it.
                    logger.warning(
                        "Background thread still alive %.1fs after startup "
                        "failure; cleanup is still in progress. The PID "
                        "file or running flag may not have cleared yet.",
                        _STARTUP_JOIN_TIMEOUT_S,
                    )
                else:
                    self._thread = None
            raise error

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
        with self._lock:
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
        started_at = self._started_at
        return time.monotonic() - started_at

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
        """Entry point for the background thread.

        Assumes self._running is already set to True by start_background()
        while holding self._lock.
        """
        logger.info("Starting daemon service (background)")
        self._started_at = time.monotonic()
        self._startup_error = None

        try:
            try:
                # Write PID file — F2 record format (pid + create_time) so
                # ``is_running`` can detect PID recycling after crash.
                if self.config.pid_file is not None:
                    self._pid_manager.write_pid_record(self.config.pid_file)

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
            except Exception as exc:
                # F4 hardening (#1323, finding 4): startup failed before the
                # daemon was actually usable. Record it so start_background()
                # re-raises instead of returning as if startup succeeded —
                # the thread dying silently here would otherwise leave no
                # PID file and no running daemon, with the caller none the
                # wiser.
                self._startup_error = exc
                return
            finally:
                # Signal that startup is complete (success OR failure) —
                # start_background() is waiting on this event and must not
                # block for the full timeout on a fast failure.
                self._started_event.set()

            # Main event loop
            self._run_loop()

        finally:
            self._cleanup()

    def _run_loop(self) -> None:
        """Main daemon event loop.

        Uses select() on the self-pipe when signal handlers are installed
        (foreground mode). Falls back to Event.wait() in background mode
        where no signals are installed.

        F4 (hardening roadmap #159): reports any signal-write failures
        that the signal handler recorded (it can't log from within a
        signal handler — not async-safe), and fully drains the pipe
        on each readable event rather than the fixed 1024-byte read,
        so a saturated pipe can't leave stale wakeup bytes buffered.
        """
        while not self._stop_event.is_set():
            self._log_signal_write_failures_if_new()
            sig_wakeup_r = self._sig_wakeup_r
            if sig_wakeup_r is not None:
                ready, _, _ = select.select(
                    [sig_wakeup_r],
                    [],
                    [],
                    self.config.poll_interval,
                )
                if ready:
                    self._drain_signal_pipe(sig_wakeup_r)
                    logger.info("Received signal, initiating graceful shutdown")
                    self._stop_event.set()
            else:
                self._stop_event.wait(timeout=self.config.poll_interval)

    def _drain_signal_pipe(self, fd: int) -> None:
        """Read from *fd* in a loop until EAGAIN (or a limit) is hit.

        F4: the signal pipe is opened non-blocking (see
        ``_install_signal_handlers``); this drains all pending wakeup
        bytes in one pass. A small iteration cap prevents a runaway
        loop in the unlikely case the pipe is being written faster
        than we read.
        """
        for _ in range(64):
            try:
                chunk = os.read(fd, 4096)
            except BlockingIOError:
                # Pipe is now empty — normal exit.
                return
            except OSError as exc:
                logger.debug("Signal pipe read failed: %s", exc, exc_info=True)
                return
            if not chunk:
                return

    def _log_signal_write_failures_if_new(self) -> None:
        """F4: emit a rate-limited warning on new signal-write failures.

        Compares ``_signal_write_failures`` (incremented by the signal
        handler on ``os.write`` failure) against
        ``_last_logged_write_failures`` and emits a WARNING only when
        the counter increased AND at least
        ``_SIGNAL_LOG_MIN_INTERVAL_S`` seconds have passed since the
        last emit. The interval guard is important: with
        ``poll_interval=0.05s`` a saturated pipe would otherwise log
        ~20 times per second, burying everything else.

        The counter-delta state is updated on every call (not just on
        emits) so a burst of failures followed by a stable plateau only
        logs once total — the post-interval re-check would still find
        no new increase.
        """
        current = self._signal_write_failures
        if current <= self._last_logged_write_failures:
            return
        now = time.monotonic()
        if now - self._last_signal_log_time < _SIGNAL_LOG_MIN_INTERVAL_S:
            return
        delta = current - self._last_logged_write_failures
        logger.warning(
            "Signal handler write failures since last loop: %d (total: %d). "
            "The signal pipe is saturated or closed; shutdown signals may be "
            "delayed until the run loop reaches the next iteration.",
            delta,
            current,
        )
        self._last_logged_write_failures = current
        self._last_signal_log_time = now

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

        with self._lock:
            self._running = False
            self._started_at = None
        self._stopped_event.set()
        logger.info("Daemon service stopped")

    def _install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown.

        Only installs handlers when running in the main thread.
        Saves original handlers so they can be restored later.
        On Windows, skips pipe creation (select.select only supports sockets).
        """
        if threading.current_thread() is not threading.main_thread():
            logger.debug("Skipping signal handler installation (not main thread)")
            return

        try:
            # Only create signal wakeup pipe on Unix-like systems
            # (Windows select() doesn't support pipes, falls back to Event.wait)
            if os.name != "nt":
                self._sig_wakeup_r, self._sig_wakeup_w = os.pipe()
                sig_wakeup_r = self._sig_wakeup_r
                sig_wakeup_w = self._sig_wakeup_w
                assert sig_wakeup_r is not None and sig_wakeup_w is not None
                os.set_blocking(sig_wakeup_r, False)
                os.set_blocking(sig_wakeup_w, False)
            self._original_sigterm = signal.getsignal(signal.SIGTERM)  # type: ignore[assignment]
            self._original_sigint = signal.getsignal(signal.SIGINT)  # type: ignore[assignment]
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
            logger.debug("Installed SIGTERM and SIGINT handlers")
        except (OSError, ValueError) as exc:
            logger.warning("Could not install signal handlers: %s", exc, exc_info=True)
            # Close pipe fds if they were created before the failure
            if self._sig_wakeup_r is not None:
                os.close(self._sig_wakeup_r)
                self._sig_wakeup_r = None
            if self._sig_wakeup_w is not None:
                os.close(self._sig_wakeup_w)
                self._sig_wakeup_w = None

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
            logger.warning("Could not restore signal handlers: %s", exc, exc_info=True)
        finally:
            # Always close pipe fds and clear attributes, even if signal restoration fails
            if self._sig_wakeup_r is not None:
                try:
                    os.close(self._sig_wakeup_r)
                except OSError:
                    pass
                self._sig_wakeup_r = None
            if self._sig_wakeup_w is not None:
                try:
                    os.close(self._sig_wakeup_w)
                except OSError:
                    pass
                self._sig_wakeup_w = None

    def _handle_signal(self, signum: int, frame: object) -> None:
        """Handle a termination signal by requesting graceful shutdown.

        Only performs async-signal-safe operations (os.write + counter
        increment). The run loop drains the pipe and logs any write
        failures this handler recorded.

        F4 (hardening roadmap #159): pre-F4 the OSError on ``os.write``
        was silently discarded. If the pipe was saturated (many signals
        queued) or closed (teardown race), the daemon had no way to
        notice that a shutdown signal might have been lost. Post-F4
        failures bump ``_signal_write_failures`` so the run loop can
        log them on its next iteration.

        Args:
            signum: The signal number received.
            frame: The current stack frame (unused).
        """
        try:
            if self._sig_wakeup_w is not None:
                os.write(self._sig_wakeup_w, b"\x00")
        except OSError:
            # Can't call logger here — not async-signal-safe. Increment
            # a counter the run loop reads on each iteration and logs.
            # Simple ``int`` read/write is atomic under the CPython GIL.
            self._signal_write_failures += 1

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
