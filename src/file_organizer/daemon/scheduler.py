"""Periodic task scheduler for the daemon.

Provides the DaemonScheduler class that runs named tasks at fixed
intervals in a single background thread, supporting dynamic task
registration and graceful shutdown.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class _ScheduledTask:
    """Internal representation of a scheduled periodic task."""

    name: str
    interval: float
    callback: Callable[[], None]
    last_run: float = 0.0


class DaemonScheduler:
    """Schedules and runs periodic tasks in a background thread.

    Tasks are registered with a name, interval, and callback.
    The scheduler runs a single event loop that fires each task
    when its interval has elapsed.

    Example:
        >>> scheduler = DaemonScheduler()
        >>> scheduler.schedule_task("health", 60.0, check_health)
        >>> scheduler.schedule_task("stats", 300.0, report_stats)
        >>> scheduler.run()  # Blocks until stop() is called
    """

    def __init__(self) -> None:
        """Initialize the scheduler with an empty task registry."""
        self._tasks: dict[str, _ScheduledTask] = {}
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._running = False
        self._thread: threading.Thread | None = None

    def schedule_task(
        self,
        name: str,
        interval: float,
        callback: Callable[[], None],
    ) -> None:
        """Register a periodic task.

        If a task with the same name already exists, it is replaced.

        Args:
            name: Unique identifier for the task.
            interval: Seconds between invocations. Must be positive.
            callback: Zero-argument callable to invoke on each tick.

        Raises:
            ValueError: If interval is not positive.
        """
        if interval <= 0:
            raise ValueError(f"interval must be positive, got {interval}")

        with self._lock:
            self._tasks[name] = _ScheduledTask(
                name=name,
                interval=interval,
                callback=callback,
            )
            logger.debug("Scheduled task '%s' every %.1fs", name, interval)

    def cancel_task(self, name: str) -> bool:
        """Cancel a previously scheduled task.

        Args:
            name: The name of the task to cancel.

        Returns:
            True if the task was found and cancelled, False if no
            task with that name exists.
        """
        with self._lock:
            if name in self._tasks:
                del self._tasks[name]
                logger.debug("Cancelled task '%s'", name)
                return True
            return False

    def run(self) -> None:
        """Run the scheduler event loop (blocking).

        Processes all registered tasks, firing each one when its
        interval has elapsed. Blocks until ``stop()`` is called
        from another thread.
        """
        self._running = True
        self._stop_event.clear()
        logger.info("Scheduler started with %d tasks", len(self._tasks))

        try:
            while not self._stop_event.is_set():
                self._tick()
                # Sleep in small increments so stop() is responsive
                self._stop_event.wait(timeout=0.1)
        finally:
            self._running = False
            logger.info("Scheduler stopped")

    def run_in_background(self) -> None:
        """Start the scheduler in a background daemon thread.

        Returns immediately. The scheduler can be stopped by calling
        ``stop()``.

        Raises:
            RuntimeError: If the scheduler is already running.
        """
        if self._running:
            raise RuntimeError("Scheduler is already running")

        self._thread = threading.Thread(
            target=self.run,
            name="daemon-scheduler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the scheduler event loop.

        Safe to call even if the scheduler is not running. If the
        scheduler was started in background mode, waits for the
        thread to finish.
        """
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

        logger.debug("Scheduler stop requested")

    @property
    def is_running(self) -> bool:
        """Return True if the scheduler event loop is active."""
        return self._running

    @property
    def task_names(self) -> list[str]:
        """Return the names of all currently scheduled tasks."""
        with self._lock:
            return list(self._tasks.keys())

    @property
    def task_count(self) -> int:
        """Return the number of registered tasks."""
        with self._lock:
            return len(self._tasks)

    def _tick(self) -> None:
        """Execute one scheduler tick.

        Checks every registered task and fires it if enough time
        has elapsed since its last invocation.
        """
        now = time.monotonic()

        with self._lock:
            tasks = list(self._tasks.values())

        for task in tasks:
            if now - task.last_run >= task.interval:
                try:
                    task.callback()
                    task.last_run = now
                except Exception:
                    logger.exception("Task '%s' raised an exception", task.name)
                    # Update last_run even on failure to prevent tight loops
                    task.last_run = now
