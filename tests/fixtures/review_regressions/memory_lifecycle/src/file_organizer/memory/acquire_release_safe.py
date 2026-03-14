"""Safe fixture: buffer is consumed between acquire and release."""

from __future__ import annotations


class BufferPool:
    def acquire(self, size: int) -> bytearray:
        return bytearray(size)

    def release(self, buf: bytearray) -> None:
        pass


def process_chunk(pool: BufferPool, data: bytes) -> None:
    # GOOD: buffer is written to before being released
    buf = pool.acquire(len(data))
    buf[:] = data
    pool.release(buf)
