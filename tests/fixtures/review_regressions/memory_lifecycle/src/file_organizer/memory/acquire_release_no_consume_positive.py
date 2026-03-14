"""Positive fixture: acquire followed immediately by release with no buffer use."""

from __future__ import annotations


class BufferPool:
    def acquire(self, size: int) -> bytearray:
        return bytearray(size)

    def release(self, buf: bytearray) -> None:
        pass


def legacy_prefetch(pool: BufferPool) -> None:
    # BAD: buffer acquired and released without any use — no-op legacy path
    buf = pool.acquire(4096)
    pool.release(buf)
