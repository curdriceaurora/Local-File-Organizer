"""Tests for optimization.buffer_pool."""

from __future__ import annotations

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
