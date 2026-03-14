"""Safe fixture: BufferPool() deferred to a setup method, not __init__."""

from __future__ import annotations


class BufferPool:
    pass


class StreamProcessor:
    def __init__(self) -> None:
        # GOOD: pool is None at init time; instantiation deferred
        self._pool: BufferPool | None = None

    def initialize(self, context: object) -> None:
        # Pool created only once context is established
        self._pool = BufferPool()
