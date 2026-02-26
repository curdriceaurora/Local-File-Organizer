"""
Unit tests for the RateThrottler.

Tests token-bucket rate limiting including acquire, wait, stats tracking,
and concurrent access from multiple threads.
"""

from __future__ import annotations
import pytest

import threading
import time
import unittest

from file_organizer.parallel.throttle import RateThrottler, ThrottleStats


@pytest.mark.unit
class TestThrottleStats(unittest.TestCase):
    """Test cases for ThrottleStats dataclass."""

    def test_create_stats(self) -> None:
        """Test creating ThrottleStats with all fields."""
        stats = ThrottleStats(
            allowed=10,
            denied=3,
            current_rate=8.5,
            max_rate=10.0,
            window_seconds=1.0,
        )
        self.assertEqual(stats.allowed, 10)
        self.assertEqual(stats.denied, 3)
        self.assertAlmostEqual(stats.current_rate, 8.5)
        self.assertEqual(stats.max_rate, 10.0)
        self.assertEqual(stats.window_seconds, 1.0)


@pytest.mark.unit
class TestRateThrottler(unittest.TestCase):
    """Test cases for RateThrottler."""

    def test_invalid_max_rate_raises(self) -> None:
        """Test that zero or negative max_rate raises ValueError."""
        with self.assertRaises(ValueError):
            RateThrottler(max_rate=0)
        with self.assertRaises(ValueError):
            RateThrottler(max_rate=-5.0)

    def test_invalid_window_raises(self) -> None:
        """Test that zero or negative window_seconds raises ValueError."""
        with self.assertRaises(ValueError):
            RateThrottler(max_rate=10.0, window_seconds=0)
        with self.assertRaises(ValueError):
            RateThrottler(max_rate=10.0, window_seconds=-1.0)

    def test_acquire_within_limit(self) -> None:
        """Test that acquire succeeds when under the rate limit."""
        throttler = RateThrottler(max_rate=10.0)
        # Should be able to acquire up to max_rate tokens immediately
        for _ in range(10):
            self.assertTrue(throttler.acquire())

    def test_acquire_exceeds_limit(self) -> None:
        """Test that acquire fails when rate limit is exhausted."""
        throttler = RateThrottler(max_rate=5.0)
        # Use all tokens
        for _ in range(5):
            throttler.acquire()
        # Next acquire should fail (no tokens refilled yet)
        self.assertFalse(throttler.acquire())

    def test_acquire_refills_over_time(self) -> None:
        """Test that tokens refill after waiting."""
        throttler = RateThrottler(max_rate=10.0, window_seconds=1.0)
        # Exhaust all tokens
        for _ in range(10):
            throttler.acquire()
        # Wait for refill (enough time for at least 1 token)
        time.sleep(0.15)
        self.assertTrue(throttler.acquire())

    def test_wait_blocks_until_available(self) -> None:
        """Test that wait blocks until a token becomes available."""
        throttler = RateThrottler(max_rate=5.0, window_seconds=1.0)
        # Exhaust tokens
        for _ in range(5):
            throttler.acquire()

        start = time.monotonic()
        throttler.wait()
        elapsed = time.monotonic() - start

        # Should have waited for at least some time for a token refill
        self.assertGreater(elapsed, 0.05)

    def test_stats_initial(self) -> None:
        """Test initial stats are zeroed."""
        throttler = RateThrottler(max_rate=10.0)
        stats = throttler.stats()
        self.assertEqual(stats.allowed, 0)
        self.assertEqual(stats.denied, 0)
        self.assertAlmostEqual(stats.current_rate, 0.0)
        self.assertEqual(stats.max_rate, 10.0)
        self.assertEqual(stats.window_seconds, 1.0)

    def test_stats_tracks_allowed(self) -> None:
        """Test that stats counts allowed acquisitions."""
        throttler = RateThrottler(max_rate=10.0)
        for _ in range(5):
            throttler.acquire()
        stats = throttler.stats()
        self.assertEqual(stats.allowed, 5)

    def test_stats_tracks_denied(self) -> None:
        """Test that stats counts denied acquisitions."""
        throttler = RateThrottler(max_rate=3.0)
        for _ in range(3):
            throttler.acquire()
        # These should be denied
        throttler.acquire()
        throttler.acquire()
        stats = throttler.stats()
        self.assertEqual(stats.allowed, 3)
        self.assertEqual(stats.denied, 2)

    def test_reset_clears_state(self) -> None:
        """Test that reset restores initial state."""
        throttler = RateThrottler(max_rate=5.0)
        for _ in range(5):
            throttler.acquire()
        throttler.acquire()  # denied

        throttler.reset()
        stats = throttler.stats()
        self.assertEqual(stats.allowed, 0)
        self.assertEqual(stats.denied, 0)

        # Should be able to acquire again
        self.assertTrue(throttler.acquire())

    def test_custom_window_seconds(self) -> None:
        """Test throttler with a custom time window."""
        # 10 operations per 2 seconds = 5 ops/sec refill rate
        throttler = RateThrottler(max_rate=10.0, window_seconds=2.0)
        for _ in range(10):
            self.assertTrue(throttler.acquire())
        # Exhausted
        self.assertFalse(throttler.acquire())
        stats = throttler.stats()
        self.assertEqual(stats.window_seconds, 2.0)

    def test_thread_safety_concurrent_acquire(self) -> None:
        """Test concurrent acquire from multiple threads."""
        throttler = RateThrottler(max_rate=100.0, window_seconds=1.0)
        results: list[bool] = []
        lock = threading.Lock()

        def worker() -> None:
            for _ in range(20):
                result = throttler.acquire()
                with lock:
                    results.append(result)

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(len(results), 100)
        # At most 100 should be allowed (max_rate = 100)
        allowed = sum(1 for r in results if r)
        self.assertLessEqual(allowed, 100)
        stats = throttler.stats()
        self.assertEqual(stats.allowed + stats.denied, 100)

    def test_thread_safety_concurrent_wait(self) -> None:
        """Test concurrent wait from multiple threads."""
        throttler = RateThrottler(max_rate=50.0, window_seconds=1.0)
        completed = []
        lock = threading.Lock()

        def worker(worker_id: int) -> None:
            throttler.wait()
            with lock:
                completed.append(worker_id)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(len(completed), 10)
        stats = throttler.stats()
        self.assertEqual(stats.allowed, 10)


if __name__ == "__main__":
    unittest.main()
