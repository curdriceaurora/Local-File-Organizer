"""Redis Streams manager for the event system.

Provides low-level Redis Streams operations with graceful fallback
when Redis is unavailable.
"""

from __future__ import annotations

import logging
import types
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore[assignment]

from file_organizer.events.config import EventConfig

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    """A single event read from a Redis Stream.

    Attributes:
        id: Redis message ID (e.g., '1234567890-0').
        stream: Name of the stream the event was read from.
        data: Event payload as a dictionary.
        timestamp: UTC timestamp parsed from event data or message ID.
    """

    id: str
    stream: str
    data: dict[str, str]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class RedisConnectionError(Exception):
    """Raised when Redis connection cannot be established."""


class RedisStreamManager:
    """Manages Redis Streams for publishing and consuming events.

    Provides connect/disconnect lifecycle, publishing messages to streams,
    creating consumer groups, and reading messages. All operations gracefully
    handle Redis unavailability.

    Example:
        >>> manager = RedisStreamManager(EventConfig())
        >>> manager.connect()
        >>> msg_id = manager.publish("events", {"key": "value"})
        >>> manager.disconnect()
    """

    def __init__(self, config: EventConfig | None = None) -> None:
        """Initialize the stream manager.

        Args:
            config: Event configuration. Uses defaults if not provided.
        """
        self._config = config or EventConfig()
        self._redis: Any | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        """Whether the manager has an active Redis connection."""
        return self._connected

    @property
    def config(self) -> EventConfig:
        """The current event configuration."""
        return self._config

    def connect(self, redis_url: str | None = None) -> bool:
        """Establish a connection to Redis.

        Args:
            redis_url: Override the configured Redis URL. If None, uses
                the URL from the EventConfig.

        Returns:
            True if connection succeeded, False if Redis is unavailable.
        """
        if redis is None:
            logger.warning("redis-py is not installed. Event system will operate in no-op mode.")
            return False

        url = redis_url or self._config.redis_url
        try:
            self._redis = redis.Redis.from_url(url, decode_responses=True, socket_timeout=5)
            # Verify connection is alive
            self._redis.ping()
            self._connected = True
            logger.info("Connected to Redis at %s", url)
            return True
        except Exception:
            logger.warning(
                "Redis unavailable at %s. Event system will operate in no-op mode.",
                url,
            )
            self._redis = None
            self._connected = False
            return False

    def disconnect(self) -> None:
        """Close the Redis connection and release resources."""
        if self._redis is not None:
            try:
                self._redis.close()
            except Exception:
                logger.debug("Error closing Redis connection", exc_info=True)
            finally:
                self._redis = None
                self._connected = False
                logger.info("Disconnected from Redis")

    def publish(
        self,
        stream_name: str,
        event_data: dict[str, str],
        max_len: int | None = None,
    ) -> str | None:
        """Publish an event to a Redis Stream.

        Args:
            stream_name: Base name of the stream (will be prefixed).
            event_data: Dictionary of string key-value pairs to publish.
            max_len: Optional maximum stream length for trimming. Overrides
                the configured max_stream_length if provided.

        Returns:
            The Redis message ID if published, None if Redis is unavailable.
        """
        if not self._connected or self._redis is None:
            logger.debug(
                "Redis not connected. Dropping event for stream '%s'.",
                stream_name,
            )
            return None

        full_name = self._config.get_stream_name(stream_name)
        trim_len = max_len if max_len is not None else self._config.max_stream_length

        try:
            kwargs: dict[str, Any] = {"name": full_name, "fields": event_data}
            if trim_len is not None:
                kwargs["maxlen"] = trim_len
                kwargs["approximate"] = True

            message_id: str = self._redis.xadd(**kwargs)
            logger.debug("Published event to '%s' with ID '%s'", full_name, message_id)
            return message_id
        except Exception:
            logger.error("Failed to publish event to '%s'", full_name, exc_info=True)
            return None

    def create_consumer_group(
        self,
        stream_name: str,
        group_name: str | None = None,
        start_id: str = "0",
    ) -> bool:
        """Create a consumer group for a stream.

        If the stream does not exist, it will be created automatically.
        If the group already exists, the operation is silently ignored.

        Args:
            stream_name: Base name of the stream (will be prefixed).
            group_name: Consumer group name. Defaults to config consumer_group.
            start_id: Starting message ID for the group ('0' = all messages,
                '$' = only new messages).

        Returns:
            True if group was created or already exists, False on error.
        """
        if not self._connected or self._redis is None:
            logger.debug("Redis not connected. Cannot create consumer group.")
            return False

        full_name = self._config.get_stream_name(stream_name)
        group = group_name or self._config.consumer_group

        try:
            self._redis.xgroup_create(name=full_name, groupname=group, id=start_id, mkstream=True)
            logger.info("Created consumer group '%s' on stream '%s'", group, full_name)
            return True
        except Exception as exc:
            # BUSYGROUP means the group already exists
            if "BUSYGROUP" in str(exc):
                logger.debug(
                    "Consumer group '%s' already exists on '%s'",
                    group,
                    full_name,
                )
                return True
            logger.error(
                "Failed to create consumer group '%s' on '%s'",
                group,
                full_name,
                exc_info=True,
            )
            return False

    def read_group(
        self,
        stream_name: str,
        group_name: str | None = None,
        consumer_name: str = "worker-1",
        count: int | None = None,
        block_ms: int | None = None,
    ) -> list[Event]:
        """Read pending messages from a consumer group.

        Args:
            stream_name: Base name of the stream (will be prefixed).
            group_name: Consumer group name. Defaults to config consumer_group.
            consumer_name: Name of this consumer within the group.
            count: Maximum number of messages to read. Defaults to
                config batch_size.
            block_ms: Milliseconds to block waiting for messages. Defaults
                to config block_ms. Use 0 for non-blocking.

        Returns:
            List of Event objects. Empty list if no messages or Redis
            is unavailable.
        """
        if not self._connected or self._redis is None:
            return []

        full_name = self._config.get_stream_name(stream_name)
        group = group_name or self._config.consumer_group
        batch = count or self._config.batch_size
        block = block_ms if block_ms is not None else self._config.block_ms

        try:
            # Read new messages assigned to this consumer
            results = self._redis.xreadgroup(
                groupname=group,
                consumername=consumer_name,
                streams={full_name: ">"},
                count=batch,
                block=block,
            )

            events: list[Event] = []
            if results:
                for _stream_key, messages in results:
                    for message_id, data in messages:
                        events.append(
                            Event(
                                id=message_id,
                                stream=full_name,
                                data=data,
                                timestamp=_parse_timestamp_from_id(message_id),
                            )
                        )
            return events
        except Exception:
            logger.error(
                "Failed to read from group '%s' on '%s'",
                group,
                full_name,
                exc_info=True,
            )
            return []

    def acknowledge(
        self,
        stream_name: str,
        group_name: str | None = None,
        message_id: str = "",
    ) -> bool:
        """Acknowledge a message as processed.

        Removes the message from the consumer's pending entries list (PEL).

        Args:
            stream_name: Base name of the stream (will be prefixed).
            group_name: Consumer group name. Defaults to config consumer_group.
            message_id: The Redis message ID to acknowledge.

        Returns:
            True if acknowledged successfully, False otherwise.
        """
        if not self._connected or self._redis is None:
            return False

        full_name = self._config.get_stream_name(stream_name)
        group = group_name or self._config.consumer_group

        try:
            ack_count: int = self._redis.xack(full_name, group, message_id)
            return ack_count > 0
        except Exception:
            logger.error(
                "Failed to acknowledge message '%s' on '%s'",
                message_id,
                full_name,
                exc_info=True,
            )
            return False

    async def subscribe(
        self,
        stream_name: str,
        group_name: str | None = None,
        consumer_name: str = "worker-1",
    ) -> AsyncIterator[Event]:
        """Subscribe to a stream and yield events as they arrive.

        This is an async generator that continuously reads from the stream
        consumer group. It will block for config.block_ms between reads.

        Args:
            stream_name: Base name of the stream (will be prefixed).
            group_name: Consumer group name. Defaults to config consumer_group.
            consumer_name: Name of this consumer within the group.

        Yields:
            Event objects as they are received from the stream.
        """
        import asyncio

        if not self._connected or self._redis is None:
            logger.warning("Redis not connected. Subscribe yielding nothing.")
            return

        # Ensure the consumer group exists
        self.create_consumer_group(stream_name, group_name)

        while self._connected:
            events = self.read_group(
                stream_name=stream_name,
                group_name=group_name,
                consumer_name=consumer_name,
                block_ms=0,  # Non-blocking for async compatibility
            )
            for event in events:
                yield event

            if not events:
                # Avoid busy-loop when no messages available
                await asyncio.sleep(self._config.block_ms / 1000.0)

    def get_stream_length(self, stream_name: str) -> int:
        """Get the number of entries in a stream.

        Args:
            stream_name: Base name of the stream (will be prefixed).

        Returns:
            Number of entries, or 0 if unavailable.
        """
        if not self._connected or self._redis is None:
            return 0

        full_name = self._config.get_stream_name(stream_name)
        try:
            return int(self._redis.xlen(full_name))
        except Exception:
            return 0

    def get_pending_count(
        self,
        stream_name: str,
        group_name: str | None = None,
    ) -> int:
        """Get the number of pending (unacknowledged) messages for a group.

        Args:
            stream_name: Base name of the stream (will be prefixed).
            group_name: Consumer group name. Defaults to config consumer_group.

        Returns:
            Number of pending messages, or 0 if unavailable.
        """
        if not self._connected or self._redis is None:
            return 0

        full_name = self._config.get_stream_name(stream_name)
        group = group_name or self._config.consumer_group

        try:
            info = self._redis.xpending(full_name, group)
            return int(info["pending"]) if info else 0
        except Exception:
            return 0

    def __enter__(self) -> RedisStreamManager:
        """Context manager entry - connects to Redis."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Context manager exit - disconnects from Redis."""
        self.disconnect()

    def __repr__(self) -> str:
        """String representation."""
        return f"RedisStreamManager(connected={self._connected}, url={self._config.redis_url!r})"


def _parse_timestamp_from_id(message_id: str) -> datetime:
    """Parse a timestamp from a Redis Stream message ID.

    Redis Stream IDs have the format '<unix_ms>-<sequence>'.

    Args:
        message_id: The Redis message ID string.

    Returns:
        UTC datetime parsed from the message ID, or current time
        if parsing fails.
    """
    try:
        ms_part = message_id.split("-")[0]
        return datetime.fromtimestamp(int(ms_part) / 1000.0, tz=UTC)
    except (ValueError, IndexError):
        return datetime.now(UTC)
