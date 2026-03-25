
class BufferPool:
    def __init__(self) -> None:
        self._buffer_size = 64

    def release(self, buffer: bytearray) -> bool:
        return len(buffer) == self._buffer_size
