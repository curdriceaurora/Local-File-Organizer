"""Tests for optimization.buffer_pool."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

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
        with pytest.raises(ValueError, match="max_buffers .* must be >= initial_buffers"):
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


class TestBufferPoolThreadSafety:
    """Concurrent usage should not leak buffers or corrupt counters."""

    def test_concurrent_acquire_release_is_leak_free(self) -> None:
        """
        Verifies that BufferPool does not leak buffers when many threads concurrently acquire and release.
        
        Creates a pool and runs multiple worker threads that repeatedly acquire a buffer, write to it, and release it; after all workers finish the test asserts:
        - `in_use_count` is 0
        - `available_buffers` equals `total_buffers`
        - `total_buffers` is at least `initial_buffers`
        - `peak_in_use` is at least 1
        """
        pool = BufferPool(buffer_size=512, initial_buffers=4, max_buffers=12)

        def worker(iterations: int) -> None:
            """
            Repeatably acquires a buffer from the surrounding `pool`, writes four bytes, then releases it.
            
            Parameters:
                iterations (int): Number of acquire/write/release cycles to perform.
            
            Notes:
                - Writes the bytes b"test" into the first four positions of each acquired buffer.
                - Uses the `pool` variable from the enclosing scope; does not return a value.
            """
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
