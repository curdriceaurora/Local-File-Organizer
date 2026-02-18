"""Configuration for the Redis Streams event system.

Provides configuration dataclass with sensible defaults for Redis
connection and stream behavior.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EventConfig:
    """Configuration for the event system.

    Attributes:
        redis_url: Redis connection URL.
        stream_prefix: Prefix for all stream names to enable namespacing.
        consumer_group: Default consumer group name.
        max_retries: Maximum number of retry attempts for failed operations.
        retry_delay: Delay in seconds between retries.
        block_ms: Milliseconds to block when reading streams (0 = non-blocking).
        max_stream_length: Maximum number of entries to keep in a stream
            (approximate trimming). None means unlimited.
        batch_size: Number of messages to read per batch.
    """

    redis_url: str = "redis://localhost:6379/0"
    stream_prefix: str = "fileorg"
    consumer_group: str = "file-organizer"
    max_retries: int = 3
    retry_delay: float = 1.0
    block_ms: int = 5000
    max_stream_length: int | None = 10000
    batch_size: int = 10

    def get_stream_name(self, name: str) -> str:
        """Build a fully qualified stream name with prefix.

        Args:
            name: Base stream name.

        Returns:
            Prefixed stream name (e.g., 'fileorg:events').
        """
        return f"{self.stream_prefix}:{name}"
