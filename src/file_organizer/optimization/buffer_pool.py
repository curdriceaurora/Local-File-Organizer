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
        """Initialize pool geometry and pre-allocate baseline buffers."""
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
        """Configured startup pool size."""
        return self._initial_buffers

    @property
    def max_buffers(self) -> int:
        """Maximum number of pooled buffers."""
        return self._max_buffers

    @property
    def total_buffers(self) -> int:
        """Current number of pooled buffers (available + in-use pooled)."""
        with self._cv:
            return self._total_buffers

    @property
    def available_buffers(self) -> int:
        """Number of pooled buffers currently idle and available."""
        with self._cv:
            return len(self._available)

    @property
    def in_use_count(self) -> int:
        """Number of currently acquired buffers (including oversize buffers)."""
        with self._cv:
            return len(self._in_use_ids)

    @property
    def peak_in_use(self) -> int:
        """Maximum concurrent in-use buffers observed since initialization."""
        with self._cv:
            return self._peak_in_use

    @property
    def utilization(self) -> float:
        """Current in-use ratio across pooled buffers."""
        with self._cv:
            if self._total_buffers <= 0:
                return 0.0
            return len(self._in_use_ids) / float(self._total_buffers)

    def acquire(self, size: int | None = None, timeout: float | None = None) -> bytearray:
        """Acquire a buffer of at least *size* bytes.

        For requests larger than ``buffer_size``, a temporary oversize buffer is
        allocated and tracked as in-use, but it is not retained in the pool when
        released.
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
        """Release a previously acquired *buffer* back to the pool."""
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
        """Shrink the pool back to its baseline ``initial_buffers`` size."""
        return self.resize(self._initial_buffers)

    def _mark_in_use(self, buffer: bytearray) -> None:
        self._in_use_ids.add(id(buffer))
        in_use = len(self._in_use_ids)
        if in_use > self._peak_in_use:
            self._peak_in_use = in_use
