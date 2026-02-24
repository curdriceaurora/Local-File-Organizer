"""Rate throttling for parallel file processing.

This module implements a token-bucket rate limiter that controls the
throughput of file processing operations. It is thread-safe and supports
both blocking and non-blocking acquisition modes.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass


@dataclass
class ThrottleStats:
    """Statistics for a :class:`RateThrottler` instance.

    Attributes:
        allowed: Total number of requests that were allowed.
        denied: Total number of requests that were denied (non-blocking).
        current_rate: Estimated current request rate (requests per second).
        max_rate: Configured maximum rate (requests per second).
        window_seconds: Configured time window in seconds.
    """

    allowed: int
    denied: int
    current_rate: float
    max_rate: float
    window_seconds: float


class RateThrottler:
    """Token-bucket rate limiter for controlling processing throughput.

    Tokens are added to the bucket at a steady rate of ``max_rate`` tokens
    per ``window_seconds``. Each :meth:`acquire` or :meth:`wait` call
    consumes one token. When the bucket is empty, :meth:`acquire` returns
    ``False`` (non-blocking) and :meth:`wait` sleeps until a token becomes
    available.

    The bucket capacity equals ``max_rate``, allowing short bursts up to
    the configured rate.

    Args:
        max_rate: Maximum number of operations per *window_seconds*.
        window_seconds: Time window for rate calculation (default 1.0s).
    """

    def __init__(self, max_rate: float, window_seconds: float = 1.0) -> None:
        """Configure the throttler with the given rate and time window."""
        if max_rate <= 0:
            raise ValueError(f"max_rate must be > 0, got {max_rate}")
        if window_seconds <= 0:
            raise ValueError(f"window_seconds must be > 0, got {window_seconds}")

        self._max_rate = max_rate
        self._window_seconds = window_seconds

        # Token bucket state
        self._tokens = max_rate
        self._last_refill = time.monotonic()

        # Rate of token generation: tokens per second
        self._refill_rate = max_rate / window_seconds

        # Statistics
        self._allowed = 0
        self._denied = 0
        self._first_allowed_time: float | None = None

        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Refill tokens based on elapsed time. Must be called with lock held."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        new_tokens = elapsed * self._refill_rate
        self._tokens = min(self._max_rate, self._tokens + new_tokens)
        self._last_refill = now

    def acquire(self) -> bool:
        """Try to acquire a token without blocking.

        Returns:
            ``True`` if a token was acquired, ``False`` if the rate
            limit has been reached.
        """
        with self._lock:
            self._refill()
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._allowed += 1
                if self._first_allowed_time is None:
                    self._first_allowed_time = time.monotonic()
                return True
            self._denied += 1
            return False

    def wait(self) -> None:
        """Block until a token is available, then consume it.

        This method sleeps in small increments until the bucket has
        enough tokens. It is safe to call from multiple threads.
        """
        while True:
            with self._lock:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    self._allowed += 1
                    if self._first_allowed_time is None:
                        self._first_allowed_time = time.monotonic()
                    return
                # Calculate time to wait for next token
                deficit = 1.0 - self._tokens
                wait_time = deficit / self._refill_rate

            # Sleep outside the lock so other threads can proceed
            time.sleep(max(wait_time, 0.001))

    def stats(self) -> ThrottleStats:
        """Return current throttle statistics.

        Returns:
            A :class:`ThrottleStats` snapshot.
        """
        with self._lock:
            if self._first_allowed_time is not None and self._allowed > 0:
                elapsed = time.monotonic() - self._first_allowed_time
                if elapsed > 0:
                    current_rate = self._allowed / elapsed
                else:
                    current_rate = 0.0
            else:
                current_rate = 0.0

            return ThrottleStats(
                allowed=self._allowed,
                denied=self._denied,
                current_rate=current_rate,
                max_rate=self._max_rate,
                window_seconds=self._window_seconds,
            )

    def reset(self) -> None:
        """Reset the throttler to its initial state."""
        with self._lock:
            self._tokens = self._max_rate
            self._last_refill = time.monotonic()
            self._allowed = 0
            self._denied = 0
            self._first_allowed_time = None
