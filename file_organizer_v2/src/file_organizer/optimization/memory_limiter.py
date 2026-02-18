"""Memory limiting with configurable enforcement actions.

Provides a memory limiter that monitors process memory usage and
takes configurable actions when limits are exceeded.
"""

from __future__ import annotations

import contextlib
import enum
import logging
import sys
from collections.abc import Generator

logger = logging.getLogger(__name__)


class LimitAction(enum.Enum):
    """Action to take when memory limit is exceeded.

    Attributes:
        WARN: Log a warning but allow execution to continue.
        BLOCK: Prevent new allocations by returning False from check().
        EVICT_CACHE: Trigger cache eviction to free memory.
        RAISE: Raise a MemoryLimitError exception.
    """

    WARN = "warn"
    BLOCK = "block"
    EVICT_CACHE = "evict_cache"
    RAISE = "raise"


class MemoryLimitError(Exception):
    """Raised when memory limit is exceeded and action is RAISE."""


class MemoryLimiter:
    """Enforce memory limits on the current process.

    Monitors process RSS against a configured maximum and takes
    action when the limit is exceeded.

    Args:
        max_memory_mb: Maximum allowed memory in megabytes.
        action: Action to take when memory exceeds the limit.

    Example:
        >>> limiter = MemoryLimiter(max_memory_mb=512, action=LimitAction.WARN)
        >>> if limiter.check():
        ...     # Memory is within limits, proceed
        ...     process_files()
        >>> with limiter.guarded():
        ...     # Automatically enforced within context
        ...     process_more_files()
    """

    def __init__(
        self,
        max_memory_mb: int,
        action: LimitAction = LimitAction.WARN,
    ) -> None:
        if max_memory_mb <= 0:
            raise ValueError(f"max_memory_mb must be > 0, got {max_memory_mb}")
        self._max_memory_bytes = max_memory_mb * 1024 * 1024
        self._max_memory_mb = max_memory_mb
        self._action = action
        self._evict_callback: object | None = None
        self._violation_count: int = 0

    @property
    def max_memory_mb(self) -> int:
        """Maximum allowed memory in megabytes."""
        return self._max_memory_mb

    @property
    def action(self) -> LimitAction:
        """Current enforcement action."""
        return self._action

    @property
    def violation_count(self) -> int:
        """Number of times the memory limit has been violated."""
        return self._violation_count

    def set_evict_callback(self, callback: object) -> None:
        """Set callback for EVICT_CACHE action.

        The callback should be a callable that frees memory,
        such as ModelCache.clear or similar.

        Args:
            callback: Callable to invoke for cache eviction.
        """
        self._evict_callback = callback

    def check(self) -> bool:
        """Check if current memory usage is within the limit.

        Returns:
            True if memory usage is within the limit, False if exceeded.
        """
        current = self._get_rss()
        return current < self._max_memory_bytes

    def get_current_memory_mb(self) -> float:
        """Get current RSS in megabytes.

        Returns:
            Current RSS in MB.
        """
        return self._get_rss() / (1024 * 1024)

    def enforce(self) -> None:
        """Check memory and take the configured action if over limit.

        Actions:
            WARN: Log a warning message.
            BLOCK: Log a warning (caller should check() first).
            EVICT_CACHE: Call the eviction callback if set.
            RAISE: Raise MemoryLimitError.

        Raises:
            MemoryLimitError: If action is RAISE and limit is exceeded.
        """
        current = self._get_rss()
        if current < self._max_memory_bytes:
            return

        self._violation_count += 1
        current_mb = current / (1024 * 1024)

        if self._action == LimitAction.WARN:
            logger.warning(
                "Memory limit exceeded: %.1f MB / %d MB",
                current_mb,
                self._max_memory_mb,
            )

        elif self._action == LimitAction.BLOCK:
            logger.warning(
                "Memory limit exceeded (BLOCK): %.1f MB / %d MB",
                current_mb,
                self._max_memory_mb,
            )

        elif self._action == LimitAction.EVICT_CACHE:
            logger.warning(
                "Memory limit exceeded, evicting cache: %.1f MB / %d MB",
                current_mb,
                self._max_memory_mb,
            )
            if self._evict_callback is not None and callable(self._evict_callback):
                self._evict_callback()

        elif self._action == LimitAction.RAISE:
            raise MemoryLimitError(
                f"Memory limit exceeded: {current_mb:.1f} MB / {self._max_memory_mb} MB"
            )

    @contextlib.contextmanager
    def guarded(self) -> Generator[None, None, None]:
        """Context manager that enforces memory limit on entry and exit.

        Calls enforce() at entry and exit of the context block.

        Yields:
            None.

        Raises:
            MemoryLimitError: If action is RAISE and limit is exceeded.
        """
        self.enforce()
        try:
            yield
        finally:
            self.enforce()

    @staticmethod
    def _get_rss() -> int:
        """Get current process RSS in bytes.

        Returns:
            RSS in bytes, or 0 if unavailable.
        """
        # Try /proc/self/status (Linux)
        try:
            with open("/proc/self/status") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        return int(line.split()[1]) * 1024
        except FileNotFoundError:
            pass

        # Try resource module (macOS/Unix)
        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            if sys.platform == "darwin":
                return usage.ru_maxrss
            return usage.ru_maxrss * 1024
        except (ImportError, AttributeError):
            pass

        return 0
