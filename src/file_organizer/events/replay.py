"""Event replay functionality for the Redis Streams event system.

Provides the ability to replay historical events from Redis Streams
for debugging, recovery, and testing purposes.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from file_organizer.events.consumer import EventConsumer
from file_organizer.events.stream import Event, RedisStreamManager

logger = logging.getLogger(__name__)


@dataclass
class ReplayConfig:
    """Configuration for event replay operations.

    Attributes:
        batch_size: Number of events to read per batch during replay.
        delay_between_events: Seconds to wait between replaying events.
            Useful for simulating real-time playback.
        dry_run: If True, events are returned but not dispatched to consumers.
    """

    batch_size: int = 100
    delay_between_events: float = 0.0
    dry_run: bool = False


class EventReplayManager:
    """Manages replaying historical events from Redis Streams.

    Allows querying past events by time range or specific message IDs,
    and optionally re-dispatching them to an EventConsumer for reprocessing.

    Example:
        >>> manager = EventReplayManager(stream_manager)
        >>> events = manager.replay_range(
        ...     "file-events",
        ...     start_time=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ...     end_time=datetime(2024, 1, 2, tzinfo=timezone.utc),
        ... )
    """

    def __init__(
        self,
        stream_manager: RedisStreamManager,
        replay_config: ReplayConfig | None = None,
    ) -> None:
        """Initialize the replay manager.

        Args:
            stream_manager: An active RedisStreamManager for stream access.
            replay_config: Replay behavior configuration. Uses defaults
                if not provided.
        """
        self._manager = stream_manager
        self._config = replay_config or ReplayConfig()

    @property
    def config(self) -> ReplayConfig:
        """The current replay configuration."""
        return self._config

    def replay_range(
        self,
        stream: str,
        start_time: datetime,
        end_time: datetime,
    ) -> list[Event]:
        """Replay events within a time range.

        Reads all events from the stream between start_time and end_time
        using Redis XRANGE. Times are converted to Redis millisecond
        timestamps.

        Args:
            stream: Base name of the stream (will be prefixed).
            start_time: Start of the time range (inclusive).
            end_time: End of the time range (inclusive).

        Returns:
            List of Event objects within the time range, ordered
            chronologically. Empty list if Redis is unavailable.
        """
        if not self._manager.is_connected:
            logger.debug("Redis not connected. Cannot replay events.")
            return []

        full_name = self._manager.config.get_stream_name(stream)
        start_ms = _datetime_to_redis_ms(start_time)
        end_ms = _datetime_to_redis_ms(end_time)

        try:
            events: list[Event] = []
            last_id = start_ms
            while True:
                results = self._manager._redis.xrange(
                    full_name,
                    min=last_id,
                    max=end_ms,
                    count=self._config.batch_size,
                )

                if not results:
                    break

                for message_id, data in results:
                    events.append(
                        Event(
                            id=message_id,
                            stream=full_name,
                            data=data,
                            timestamp=_parse_timestamp_from_id(message_id),
                        )
                    )

                # If we got fewer than batch_size, we've read everything
                if len(results) < self._config.batch_size:
                    break

                # Increment the last ID to avoid re-reading it
                last_id = _increment_id(results[-1][0])

            logger.info(
                "Replayed %d events from '%s' between %s and %s",
                len(events),
                full_name,
                start_time.isoformat(),
                end_time.isoformat(),
            )
            return events
        except Exception:
            logger.error(
                "Failed to replay events from '%s'",
                full_name,
                exc_info=True,
            )
            return []

    def replay_by_id(
        self,
        stream: str,
        message_ids: list[str],
    ) -> list[Event]:
        """Replay specific events by their message IDs.

        Retrieves individual events from the stream using Redis XRANGE
        with exact ID matching.

        Args:
            stream: Base name of the stream (will be prefixed).
            message_ids: List of Redis message IDs to retrieve.

        Returns:
            List of Event objects for found messages. Messages that
            no longer exist in the stream are silently skipped.
        """
        if not self._manager.is_connected:
            logger.debug("Redis not connected. Cannot replay by ID.")
            return []

        full_name = self._manager.config.get_stream_name(stream)
        events: list[Event] = []

        try:
            for msg_id in message_ids:
                results = self._manager._redis.xrange(
                    full_name,
                    min=msg_id,
                    max=msg_id,
                    count=1,
                )
                if results:
                    message_id, data = results[0]
                    events.append(
                        Event(
                            id=message_id,
                            stream=full_name,
                            data=data,
                            timestamp=_parse_timestamp_from_id(message_id),
                        )
                    )

            logger.info(
                "Replayed %d of %d requested events from '%s'",
                len(events),
                len(message_ids),
                full_name,
            )
            return events
        except Exception:
            logger.error(
                "Failed to replay events by ID from '%s'",
                full_name,
                exc_info=True,
            )
            return []

    def replay_to_consumer(
        self,
        stream: str,
        start_time: datetime,
        consumer: EventConsumer,
    ) -> int:
        """Replay events from a time range and dispatch them to a consumer.

        Retrieves historical events and feeds them to the consumer's
        registered handlers. Respects the replay config's delay_between_events
        and dry_run settings.

        Args:
            stream: Base name of the stream (will be prefixed).
            start_time: Start of the time range (inclusive). Events are
                replayed from this point up to the current time.
            consumer: An EventConsumer with registered handlers to receive
                the replayed events.

        Returns:
            Number of events dispatched to the consumer. Returns 0 if
            dry_run is enabled or Redis is unavailable.
        """
        end_time = datetime.now(UTC)
        events = self.replay_range(stream, start_time, end_time)

        if self._config.dry_run:
            logger.info("Dry run: would replay %d events to consumer", len(events))
            return 0

        dispatched = 0
        for event in events:
            event_type = event.data.get("event_type", "")
            handlers = consumer._handlers.get(event_type, [])

            for handler in handlers:
                try:
                    handler(event)
                except Exception:
                    logger.error(
                        "Handler failed during replay for event '%s'",
                        event.id,
                        exc_info=True,
                    )

            dispatched += 1

            if self._config.delay_between_events > 0:
                time.sleep(self._config.delay_between_events)

        logger.info(
            "Dispatched %d events to consumer from '%s'",
            dispatched,
            stream,
        )
        return dispatched

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"EventReplayManager(connected={self._manager.is_connected}, "
            f"batch_size={self._config.batch_size}, "
            f"dry_run={self._config.dry_run})"
        )


def _datetime_to_redis_ms(dt: datetime) -> str:
    """Convert a datetime to a Redis Stream millisecond timestamp string.

    Args:
        dt: The datetime to convert. Must be timezone-aware.

    Returns:
        String of milliseconds since epoch suitable for XRANGE.
    """
    return str(int(dt.timestamp() * 1000))


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


def _increment_id(message_id: str) -> str:
    """Increment a Redis Stream message ID to the next possible value.

    Used for pagination to avoid re-reading the last message.

    Args:
        message_id: The Redis message ID to increment (e.g., '123-0').

    Returns:
        The next message ID (e.g., '123-1').
    """
    try:
        parts = message_id.split("-")
        ms = parts[0]
        seq = int(parts[1]) + 1
        return f"{ms}-{seq}"
    except (ValueError, IndexError):
        return message_id
