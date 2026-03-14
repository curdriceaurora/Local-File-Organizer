"""Positive fixture: BufferPool() instantiated eagerly inside __init__."""

from __future__ import annotations


class BufferPool:
    pass


class StreamProcessor:
    def __init__(self) -> None:
        # BAD: BufferPool() instantiated eagerly before any context is available
        self._pool = BufferPool()
