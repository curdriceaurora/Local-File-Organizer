"""Positive fixture: len(buffer) used to infer ownership inside pool contexts."""


class BufferPool:
    def acquire(self, size: int) -> bytearray:
        return bytearray(size)

    def release(self, buf: bytearray) -> None:
        # BAD: using len(buf) to infer whether we own it
        if len(buf) > 0:
            buf.clear()

    def _get_buffer(self, buf: bytearray) -> int:
        return len(buf)
