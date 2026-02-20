"""Event publisher for the file organizer event system.

Provides a high-level API for publishing file and scan events
to Redis Streams.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from file_organizer.events.config import EventConfig
from file_organizer.events.stream import RedisStreamManager
from file_organizer.events.types import EventType, FileEvent, ScanEvent

logger = logging.getLogger(__name__)


class EventPublisher:
    """High-level event publisher for file organizer events.

    Wraps the RedisStreamManager to provide typed event publishing
    methods. If Redis is unavailable, events are silently dropped
    and logged at debug level.

    Example:
        >>> publisher = EventPublisher()
        >>> publisher.connect()
        >>> publisher.publish_file_event(
        ...     EventType.FILE_CREATED,
        ...     "/path/to/file.txt",
        ...     {"size": 1024}
        ... )
        >>> publisher.disconnect()
    """

    # Default stream names for different event categories
    FILE_STREAM = "file-events"
    SCAN_STREAM = "scan-events"

    def __init__(
        self,
        config: EventConfig | None = None,
        stream_manager: RedisStreamManager | None = None,
    ) -> None:
        """Initialize the event publisher.

        Args:
            config: Event configuration. Uses defaults if not provided.
            stream_manager: Optional pre-configured stream manager.
                If not provided, a new one will be created.
        """
        self._config = config or EventConfig()
        self._manager = stream_manager or RedisStreamManager(self._config)
        self._event_count = 0

    @property
    def is_connected(self) -> bool:
        """Whether the underlying stream manager is connected."""
        return self._manager.is_connected

    @property
    def event_count(self) -> int:
        """Total number of events published since creation."""
        return self._event_count

    def connect(self, redis_url: str | None = None) -> bool:
        """Connect to Redis.

        Args:
            redis_url: Override Redis URL. If None, uses config.

        Returns:
            True if connected, False if Redis is unavailable.
        """
        return self._manager.connect(redis_url)

    def disconnect(self) -> None:
        """Disconnect from Redis."""
        self._manager.disconnect()

    def publish_file_event(
        self,
        event_type: EventType,
        file_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Publish a file-related event.

        Args:
            event_type: Type of file event (FILE_CREATED, FILE_MODIFIED, etc.).
            file_path: Path to the affected file.
            metadata: Optional additional metadata about the event.

        Returns:
            The Redis message ID if published, None otherwise.
        """
        event = FileEvent(
            event_type=event_type,
            file_path=file_path,
            metadata=metadata or {},
            timestamp=datetime.now(UTC),
        )

        message_id = self._manager.publish(
            stream_name=self.FILE_STREAM,
            event_data=event.to_dict(),
        )

        if message_id is not None:
            self._event_count += 1
            logger.debug(
                "Published %s event for '%s' (ID: %s)",
                event_type.value,
                file_path,
                message_id,
            )

        return message_id

    def publish_scan_event(
        self,
        scan_id: str,
        status: str,
        stats: dict[str, Any] | None = None,
    ) -> str | None:
        """Publish a scan-related event.

        Args:
            scan_id: Unique identifier for the scan operation.
            status: Status string (e.g., 'started', 'completed', 'failed').
            stats: Optional scan statistics (files_found, errors, etc.).

        Returns:
            The Redis message ID if published, None otherwise.
        """
        event = ScanEvent(
            scan_id=scan_id,
            status=status,
            stats=stats or {},
            timestamp=datetime.now(UTC),
        )

        message_id = self._manager.publish(
            stream_name=self.SCAN_STREAM,
            event_data=event.to_dict(),
        )

        if message_id is not None:
            self._event_count += 1
            logger.debug(
                "Published scan event '%s' (status: %s, ID: %s)",
                scan_id,
                status,
                message_id,
            )

        return message_id

    def __enter__(self) -> EventPublisher:
        """Context manager entry - connects to Redis."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Context manager exit - disconnects from Redis."""
        self.disconnect()

    def __repr__(self) -> str:
        """String representation."""
        return (
            f"EventPublisher(connected={self.is_connected}, events_published={self._event_count})"
        )
