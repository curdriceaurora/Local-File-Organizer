"""Thread-safe reusable byte buffer pool for pipeline workloads.

The pool pre-allocates fixed-size buffers to reduce allocation churn during
high-volume batch processing. Buffers can be acquired concurrently from worker
threads and released back into the pool when processing completes.
"""

from __future__ import annotations

import threading


class BufferPool:
    """Manage reusable fixed-size ``bytearray`` buffers.

    Args:
        buffer_size: Size in bytes for each pooled buffer.
        initial_buffers: Number of buffers to pre-allocate at startup.
        max_buffers: Hard upper bound for pooled buffers. If ``None``,
            defaults to ``max(initial_buffers, initial_buffers * 4)``.
    """

    def __init__(
        self,
        *,
        buffer_size: int = 1024 * 1024,
        initial_buffers: int = 10,
        max_buffers: int | None = None,
    ) -> None:
        """
        Create a BufferPool configured to manage fixed-size reusable bytearray buffers and pre-allocate the baseline pool.
        
        Parameters:
            buffer_size (int): Size in bytes for each pooled buffer; must be greater than 0.
            initial_buffers (int): Number of buffers to pre-allocate at construction; must be greater than 0.
            max_buffers (int | None): Hard upper bound for total buffers managed by the pool. If None, defaults to max(initial_buffers, initial_buffers * 4). The resolved value must be greater than or equal to initial_buffers.
        
        Raises:
            ValueError: If `buffer_size` <= 0, `initial_buffers` <= 0, or the resolved `max_buffers` is less than `initial_buffers`.
        """
        if buffer_size <= 0:
            raise ValueError(f"buffer_size must be > 0, got {buffer_size}")
        if initial_buffers <= 0:
            raise ValueError(f"initial_buffers must be > 0, got {initial_buffers}")
        resolved_max = (
            max_buffers if max_buffers is not None else max(initial_buffers, initial_buffers * 4)
        )
        if resolved_max < initial_buffers:
            raise ValueError(
                f"max_buffers ({resolved_max}) must be >= initial_buffers ({initial_buffers})"
            )

        self._buffer_size = buffer_size
        self._initial_buffers = initial_buffers
        self._max_buffers = resolved_max
        self._available: list[bytearray] = [bytearray(buffer_size) for _ in range(initial_buffers)]
        self._total_buffers = initial_buffers
        self._in_use_ids: set[int] = set()
        self._peak_in_use = 0
        self._cv = threading.Condition()

    @property
    def buffer_size(self) -> int:
        """Size in bytes for each pooled buffer."""
        return self._buffer_size

    @property
    def initial_buffers(self) -> int:
        """
        Configured number of buffers pre-allocated at pool startup.
        
        Returns:
            int: Number of buffers created during initialization.
        """
        return self._initial_buffers

    @property
    def max_buffers(self) -> int:
        """
        Maximum number of buffers the pool may hold.
        
        Returns:
            max_buffers (int): The configured upper bound for pooled buffers.
        """
        return self._max_buffers

    @property
    def total_buffers(self) -> int:
        """
        Return the pool's current total number of fixed-size buffers.
        
        Returns:
            total (int): The total number of buffers managed by the pool (available + in-use).
        """
        with self._cv:
            return self._total_buffers

    @property
    def available_buffers(self) -> int:
        """
        Number of pooled bytearray buffers currently idle and available for acquisition.
        
        Returns:
            int: Count of idle buffers ready to be acquired.
        """
        with self._cv:
            return len(self._available)

    @property
    def in_use_count(self) -> int:
        """
        Return the count of buffers currently acquired from the pool, including oversize buffers.
        
        Returns:
            int: Number of buffers currently in use.
        """
        with self._cv:
            return len(self._in_use_ids)

    @property
    def peak_in_use(self) -> int:
        """
        Maximum number of buffers concurrently acquired since initialization.
        
        Returns:
            peak (int): Highest observed count of buffers that were in use at the same time.
        """
        with self._cv:
            return self._peak_in_use

    @property
    def utilization(self) -> float:
        """
        Current fraction of the pool's buffers that are currently acquired.
        
        Returns:
            ratio (float): The number of in-use buffers divided by the total buffers; 0.0 if the pool has no buffers.
        """
        with self._cv:
            if self._total_buffers <= 0:
                return 0.0
            return len(self._in_use_ids) / float(self._total_buffers)

    def acquire(self, size: int | None = None, timeout: float | None = None) -> bytearray:
        """
        Acquire a buffer with at least the requested number of bytes from the pool.
        
        If `size` is None the pool's configured buffer_size is used. If the requested
        size is greater than the pooled buffer_size an oversize temporary buffer is
        allocated and tracked as in-use but will not be returned to the pool when
        released. When the pool is at maximum capacity and no buffers are available,
        this call will wait up to `timeout` seconds for a buffer to be released.
        
        Parameters:
            size (int | None): Minimum number of bytes required; defaults to the pool's
                buffer_size when None.
            timeout (float | None): Maximum seconds to wait for an available pooled
                buffer when the pool is exhausted. `None` means wait indefinitely.
        
        Returns:
            bytearray: A buffer at least `size` bytes long. Oversize buffers are not
            retained in the pool when released.
        
        Raises:
            ValueError: If `size` <= 0 or `timeout` is negative.
            TimeoutError: If waiting for a buffer times out.
        """
        requested = self._buffer_size if size is None else size
        if requested <= 0:
            raise ValueError(f"size must be > 0, got {requested}")

        with self._cv:
            if requested > self._buffer_size:
                buffer = bytearray(requested)
                self._mark_in_use(buffer)
                return buffer

            if self._available:
                buffer = self._available.pop()
                self._mark_in_use(buffer)
                return buffer

            if self._total_buffers < self._max_buffers:
                buffer = bytearray(self._buffer_size)
                self._total_buffers += 1
                self._mark_in_use(buffer)
                return buffer

            if timeout is not None and timeout < 0:
                raise ValueError(f"timeout must be >= 0, got {timeout}")

            waited = self._cv.wait_for(lambda: bool(self._available), timeout=timeout)
            if not waited:
                raise TimeoutError("Timed out waiting for an available buffer")
            buffer = self._available.pop()
            self._mark_in_use(buffer)
            return buffer

    def release(self, buffer: bytearray) -> None:
        """
        Return a previously acquired buffer to the pool.
        
        If the buffer was obtained from this pool and has the pool's configured size, it is returned to the available pool and a waiting acquirer is notified; buffers larger than the pool size are discarded. Raises a ValueError if the buffer is not currently marked as in use by this pool.
        
        Parameters:
            buffer (bytearray): The buffer to release; must have previously been acquired from this pool.
        
        Raises:
            ValueError: If the provided buffer is not owned by this pool.
        """
        with self._cv:
            buffer_id = id(buffer)
            if buffer_id not in self._in_use_ids:
                raise ValueError("Attempted to release a buffer not owned by this pool")

            self._in_use_ids.remove(buffer_id)

            if len(buffer) == self._buffer_size and len(self._available) < self._total_buffers:
                self._available.append(buffer)
                self._cv.notify()

    def resize(self, target_total_buffers: int) -> int:
        """Resize pooled capacity toward *target_total_buffers*.

        The pool never shrinks below ``initial_buffers`` and never grows above
        ``max_buffers``. Shrink operations only remove currently available
        buffers, never in-use buffers.

        Returns:
            The resulting ``total_buffers`` count.
        """
        if target_total_buffers <= 0:
            raise ValueError(f"target_total_buffers must be > 0, got {target_total_buffers}")

        with self._cv:
            clamped_target = min(
                self._max_buffers,
                max(self._initial_buffers, target_total_buffers),
            )

            if clamped_target > self._total_buffers:
                for _ in range(clamped_target - self._total_buffers):
                    self._available.append(bytearray(self._buffer_size))
                self._total_buffers = clamped_target
                self._cv.notify_all()
                return self._total_buffers

            desired_removal = self._total_buffers - clamped_target
            removable = min(desired_removal, len(self._available))
            if removable > 0:
                del self._available[-removable:]
                self._total_buffers -= removable

            return self._total_buffers

    def shrink_to_baseline(self) -> int:
        """
        Shrink the pool to its configured initial number of buffers.
        
        Returns:
            total_buffers (int): New total number of buffers after shrinking.
        """
        return self.resize(self._initial_buffers)

    def _mark_in_use(self, buffer: bytearray) -> None:
        """
        Mark the given buffer as currently in use by the pool and update the peak concurrent usage.
        
        Parameters:
            buffer (bytearray): The buffer instance to record as in-use; its identity is tracked for later validation on release.
        """
        self._in_use_ids.add(id(buffer))
        in_use = len(self._in_use_ids)
        if in_use > self._peak_in_use:
            self._peak_in_use = in_use
