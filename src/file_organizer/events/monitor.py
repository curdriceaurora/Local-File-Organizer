"""Event monitoring for the Redis Streams event system.

Provides real-time monitoring of stream health, consumer lag,
and event throughput metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from file_organizer.events.stream import RedisStreamManager

logger = logging.getLogger(__name__)


@dataclass
class StreamStats:
    """Statistics for a Redis Stream.

    Attributes:
        length: Total number of entries in the stream.
        groups: Number of consumer groups attached to the stream.
        oldest_event: Timestamp of the oldest event in the stream.
        newest_event: Timestamp of the newest event in the stream.
    """

    length: int = 0
    groups: int = 0
    oldest_event: datetime | None = None
    newest_event: datetime | None = None


@dataclass
class ConsumerLag:
    """Consumer group lag information.

    Attributes:
        pending: Number of messages delivered but not yet acknowledged.
        idle_time: Milliseconds since the last interaction with the group.
        consumers: Number of consumers in the group.
    """

    pending: int = 0
    idle_time: int = 0
    consumers: int = 0


class EventMonitor:
    """Monitors Redis Streams health and performance metrics.

    Provides stream statistics, consumer lag tracking, and event
    rate calculations for operational visibility.

    Example:
        >>> monitor = EventMonitor(stream_manager)
        >>> stats = monitor.get_stream_stats("file-events")
        >>> print(f"Stream has {stats.length} events")
    """

    def __init__(self, stream_manager: RedisStreamManager) -> None:
        """Initialize the event monitor.

        Args:
            stream_manager: An active RedisStreamManager for stream access.
        """
        self._manager = stream_manager

    def get_stream_stats(self, stream: str) -> StreamStats:
        """Get comprehensive statistics for a stream.

        Queries Redis for stream length, consumer groups, and the
        timestamps of the oldest and newest events.

        Args:
            stream: Base name of the stream (will be prefixed).

        Returns:
            StreamStats with current stream information. Returns
            empty stats if Redis is unavailable.
        """
        if not self._manager.is_connected:
            logger.debug("Redis not connected. Returning empty stats.")
            return StreamStats()

        full_name = self._manager.config.get_stream_name(stream)

        try:
            assert self._manager._redis is not None
            info = self._manager._redis.xinfo_stream(full_name)

            length = info.get("length", 0)
            groups = info.get("groups", 0)

            oldest_event = _parse_entry_timestamp(info.get("first-entry"))
            newest_event = _parse_entry_timestamp(info.get("last-entry"))

            return StreamStats(
                length=length,
                groups=groups,
                oldest_event=oldest_event,
                newest_event=newest_event,
            )
        except Exception:
            logger.error(
                "Failed to get stream stats for '%s'",
                full_name,
                exc_info=True,
            )
            return StreamStats()

    def get_consumer_lag(self, stream: str, group: str) -> ConsumerLag:
        """Get consumer group lag information.

        Queries the pending entries list (PEL) and group info to
        determine how far behind consumers are.

        Args:
            stream: Base name of the stream (will be prefixed).
            group: Consumer group name to check.

        Returns:
            ConsumerLag with pending count and consumer details.
            Returns empty lag if Redis is unavailable.
        """
        if not self._manager.is_connected:
            logger.debug("Redis not connected. Returning empty lag.")
            return ConsumerLag()

        full_name = self._manager.config.get_stream_name(stream)

        try:
            # Get pending entries summary
            assert self._manager._redis is not None
            pending_info = self._manager._redis.xpending(full_name, group)
            pending = pending_info.get("pending", 0) if pending_info else 0

            # Get group details including consumers
            groups_info = self._manager._redis.xinfo_groups(full_name)
            group_info = None
            for g in groups_info:
                if g.get("name") == group:
                    group_info = g
                    break

            consumers = 0
            idle_time = 0
            if group_info:
                consumers = group_info.get("consumers", 0)
                idle_time = group_info.get("idle", 0)

            return ConsumerLag(
                pending=pending,
                idle_time=idle_time,
                consumers=consumers,
            )
        except Exception:
            logger.error(
                "Failed to get consumer lag for '%s' group '%s'",
                full_name,
                group,
                exc_info=True,
            )
            return ConsumerLag()

    def get_event_rate(self, stream: str, window_seconds: int = 60) -> float:
        """Calculate the event rate for a stream over a time window.

        Counts events published in the last window_seconds and returns
        the rate as events per second.

        Args:
            stream: Base name of the stream (will be prefixed).
            window_seconds: Time window in seconds to calculate rate over.
                Defaults to 60 seconds.

        Returns:
            Events per second as a float. Returns 0.0 if Redis is
            unavailable or no events exist.
        """
        if not self._manager.is_connected:
            logger.debug("Redis not connected. Returning zero rate.")
            return 0.0

        if window_seconds <= 0:
            return 0.0

        full_name = self._manager.config.get_stream_name(stream)

        try:
            now = datetime.now(UTC)
            start_ms = str(int((now.timestamp() - window_seconds) * 1000))
            end_ms = str(int(now.timestamp() * 1000))

            # Count events in the window using XRANGE
            assert self._manager._redis is not None
            results = self._manager._redis.xrange(
                full_name,
                min=start_ms,
                max=end_ms,
            )

            count = len(results) if results else 0
            rate = count / window_seconds

            logger.debug(
                "Event rate for '%s': %.2f events/sec (%d events in %ds)",
                full_name,
                rate,
                count,
                window_seconds,
            )
            return rate
        except Exception:
            logger.error(
                "Failed to calculate event rate for '%s'",
                full_name,
                exc_info=True,
            )
            return 0.0

    def __repr__(self) -> str:
        """String representation."""
        return f"EventMonitor(connected={self._manager.is_connected})"


def _parse_entry_timestamp(
    entry: tuple[str, dict[str, str]] | list[Any] | None,
) -> datetime | None:
    """Parse a timestamp from a Redis Stream entry (first-entry or last-entry).

    The entry format from XINFO STREAM is a tuple of (message_id, data).

    Args:
        entry: A stream entry tuple or None.

    Returns:
        UTC datetime parsed from the message ID, or None if entry is None
        or parsing fails.
    """
    if entry is None:
        return None

    try:
        message_id = entry[0] if isinstance(entry, (list, tuple)) else str(entry)
        ms_part = message_id.split("-")[0]
        return datetime.fromtimestamp(int(ms_part) / 1000.0, tz=UTC)
    except (ValueError, IndexError, TypeError):
        return None
