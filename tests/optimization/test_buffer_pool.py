"""Tests for optimization.buffer_pool."""

from __future__ import annotations

import tracemalloc
from concurrent.futures import ThreadPoolExecutor

import pytest

import file_organizer.optimization.buffer_pool as buffer_pool_module
from file_organizer.optimization.buffer_pool import BufferPool

pytestmark = [pytest.mark.unit, pytest.mark.ci]


class TestBufferPoolInitialization:
    """Initialization and input validation."""

    def test_default_initialization(self) -> None:
        pool = BufferPool()
        assert pool.buffer_size == 1024 * 1024
        assert pool.initial_buffers == 10
        assert pool.total_buffers == 10
        assert pool.available_buffers == 10
        assert pool.in_use_count == 0

    def test_invalid_args_raise(self) -> None:
        with pytest.raises(ValueError, match="buffer_size must be > 0"):
            BufferPool(buffer_size=0)
        with pytest.raises(ValueError, match="initial_buffers must be > 0"):
            BufferPool(initial_buffers=0)
        with pytest.raises(ValueError, match=r"max_buffers .* must be >= initial_buffers"):
            BufferPool(initial_buffers=4, max_buffers=3)


class TestBufferPoolAcquireRelease:
    """Acquire/release lifecycle and resizing behavior."""

    def test_acquire_release_roundtrip_returns_to_baseline(self) -> None:
        pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=4)
        one = pool.acquire()
        two = pool.acquire()

        assert pool.in_use_count == 2
        assert pool.available_buffers == 0

        pool.release(one)
        pool.release(two)

        assert pool.in_use_count == 0
        assert pool.available_buffers == 2
        assert pool.total_buffers == 2

    def test_oversized_buffer_is_tracked_then_dropped_on_release(self) -> None:
        pool = BufferPool(buffer_size=128, initial_buffers=2, max_buffers=4)
        oversized = pool.acquire(size=1024)
        assert len(oversized) == 1024
        assert pool.in_use_count == 1
        assert pool.total_buffers == 2

        pool.release(oversized)
        assert pool.in_use_count == 0
        assert pool.total_buffers == 2
        assert pool.available_buffers == 2

    def test_resize_shrinks_only_available_buffers(self) -> None:
        pool = BufferPool(buffer_size=64, initial_buffers=2, max_buffers=8)
        assert pool.resize(6) == 6
        assert pool.total_buffers == 6

        held = pool.acquire()
        assert pool.resize(2) == 2
        assert pool.total_buffers == 2
        pool.release(held)
        assert pool.total_buffers == 2
        assert pool.available_buffers == 2

    def test_release_of_unknown_buffer_raises(self) -> None:
        pool = BufferPool(buffer_size=64, initial_buffers=1, max_buffers=2)
        with pytest.raises(ValueError, match="not owned by this pool"):
            pool.release(bytearray(64))

    def test_release_of_resized_pooled_buffer_drops_capacity_without_raising(self) -> None:
        pool = BufferPool(buffer_size=64, initial_buffers=2, max_buffers=4)
        pooled = pool.acquire()
        pooled.extend(b"x")

        pool.release(pooled)

        assert pool.in_use_count == 0
        assert pool.total_buffers == 1
        assert pool.available_buffers == 1

    def test_resize_grow_is_atomic_on_allocation_failure(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        pool = BufferPool(buffer_size=64, initial_buffers=2, max_buffers=4)
        baseline_total = pool.total_buffers
        baseline_available = pool.available_buffers

        calls = 0
        original_bytearray = bytearray

        def flaky_bytearray(size: int) -> bytearray:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise MemoryError("synthetic allocation failure")
            return original_bytearray(size)

        monkeypatch.setitem(
            buffer_pool_module.BufferPool.resize.__globals__, "bytearray", flaky_bytearray
        )

        with pytest.raises(MemoryError, match="synthetic allocation failure"):
            pool.resize(4)

        assert calls == 2
        assert pool.total_buffers == baseline_total
        assert pool.available_buffers == baseline_available


class TestBufferPoolThreadSafety:
    """Concurrent usage should not leak buffers or corrupt counters."""

    def test_concurrent_acquire_release_is_leak_free(self) -> None:
        pool = BufferPool(buffer_size=512, initial_buffers=4, max_buffers=12)

        def worker(iterations: int) -> None:
            for _ in range(iterations):
                buf = pool.acquire()
                buf[0:4] = b"test"
                pool.release(buf)

        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(worker, 200) for _ in range(8)]
            for fut in futures:
                fut.result()

        assert pool.in_use_count == 0
        assert pool.available_buffers == pool.total_buffers
        assert pool.total_buffers >= pool.initial_buffers
        assert pool.peak_in_use >= 1

    def test_concurrent_acquire_release_thread_safe(self) -> None:
        """Multiple threads acquiring and releasing simultaneously must not corrupt pool state."""
        pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=8)
        errors: list[Exception] = []

        def worker() -> None:
            try:
                for _ in range(50):
                    buf = pool.acquire()
                    # Verify we got a valid buffer of at least buffer_size bytes.
                    assert len(buf) >= 256
                    pool.release(buf)
            except Exception as exc:
                errors.append(exc)

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(worker) for _ in range(6)]
            for fut in futures:
                fut.result()

        assert not errors, f"Thread workers raised: {errors}"
        assert pool.in_use_count == 0
        assert pool.available_buffers == pool.total_buffers


class TestBufferPoolNamedContracts:
    """Named contract tests that match the issue acceptance criteria."""

    def test_acquire_returns_buffer_of_requested_size(self) -> None:
        """acquire(size) returns a bytearray of at least *size* bytes."""
        pool = BufferPool(buffer_size=512, initial_buffers=2, max_buffers=4)

        # Request smaller than buffer_size → returns a standard pool buffer.
        buf_small = pool.acquire(size=100)
        assert isinstance(buf_small, bytearray)
        assert len(buf_small) >= 100
        pool.release(buf_small)

        # Request exactly buffer_size → returns a standard pool buffer.
        buf_exact = pool.acquire(size=512)
        assert len(buf_exact) == 512
        pool.release(buf_exact)

        # Request larger than buffer_size → allocates an oversized buffer.
        buf_large = pool.acquire(size=4096)
        assert isinstance(buf_large, bytearray)
        assert len(buf_large) == 4096
        pool.release(buf_large)

    def test_release_returns_buffer_to_pool(self) -> None:
        """release() returns a standard buffer back to the pool's available list."""
        pool = BufferPool(buffer_size=256, initial_buffers=2, max_buffers=4)

        available_before = pool.available_buffers
        buf = pool.acquire()
        assert pool.available_buffers == available_before - 1
        assert pool.in_use_count == 1

        pool.release(buf)
        assert pool.available_buffers == available_before
        assert pool.in_use_count == 0

    def test_acquire_when_pool_empty_allocates_new_buffer(self) -> None:
        """When all pre-allocated buffers are in use and pool hasn't hit max_buffers,
        acquire() allocates a new buffer rather than blocking."""
        pool = BufferPool(buffer_size=64, initial_buffers=1, max_buffers=4)

        # Exhaust the single pre-allocated buffer.
        first = pool.acquire()
        assert pool.available_buffers == 0
        assert pool.total_buffers == 1

        # Pool not at max — should allocate a new buffer without blocking.
        second = pool.acquire()
        assert isinstance(second, bytearray)
        assert pool.total_buffers == 2

        pool.release(first)
        pool.release(second)
        assert pool.in_use_count == 0


class TestBufferPoolTracemalloc:
    """Memory-footprint tests using tracemalloc."""

    def test_tracemalloc_1000_file_synthetic_batch(self) -> None:
        """Peak allocation delta across 1 000 synthetic file-process cycles must stay < 50 MB.

        This test exercises the pool's buffer-reuse path: the same physical
        bytearray objects are recycled across all iterations, so the net
        allocation increment should be far below the theoretical 1 000 × 1 MB
        that a naive, non-pooled implementation would consume.
        """
        pool = BufferPool(buffer_size=1024 * 1024, initial_buffers=4, max_buffers=16)

        # Warm up the pool so pre-allocation is attributed outside the measured window.
        warmup = pool.acquire()
        pool.release(warmup)

        tracemalloc.start()
        snapshot_before = tracemalloc.take_snapshot()

        for _ in range(1000):
            buf = pool.acquire()
            # Simulate minimal I/O: touch first and last byte.
            buf[0] = 0xAB
            buf[-1] = 0xCD
            pool.release(buf)

        snapshot_after = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Compute net allocation delta (new - old, bytes only).
        stats = snapshot_after.compare_to(snapshot_before, "lineno")
        net_delta_bytes = sum(stat.size_diff for stat in stats if stat.size_diff > 0)

        fifty_mb = 50 * 1024 * 1024
        assert net_delta_bytes < fifty_mb, (
            f"Pool reuse allocated {net_delta_bytes / (1024 * 1024):.1f} MB across "
            f"1 000 iterations (limit: 50 MB). Buffer reuse is not working correctly."
        )
