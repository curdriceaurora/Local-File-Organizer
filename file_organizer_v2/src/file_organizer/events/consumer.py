"""Event consumer for the file organizer event system.

Provides a high-level API for consuming and processing events
from Redis Streams with handler registration.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from file_organizer.events.config import EventConfig
from file_organizer.events.stream import Event, RedisStreamManager
from file_organizer.events.types import EventType

logger = logging.getLogger(__name__)

# Type alias for event handler callbacks
EventHandler = Callable[[Event], None]


class EventConsumer:
    """High-level event consumer with handler registration.

    Allows registering typed handlers for specific event types.
    When consuming, incoming events are dispatched to the appropriate
    handler based on their event_type field.

    Example:
        >>> consumer = EventConsumer()
        >>> consumer.connect()
        >>> consumer.register_handler(
        ...     EventType.FILE_CREATED,
        ...     lambda event: print(f"New file: {event.data}")
        ... )
        >>> asyncio.run(consumer.start_consuming("file-events"))
    """

    def __init__(
        self,
        config: EventConfig | None = None,
        stream_manager: RedisStreamManager | None = None,
        consumer_name: str = "worker-1",
    ) -> None:
        """Initialize the event consumer.

        Args:
            config: Event configuration. Uses defaults if not provided.
            stream_manager: Optional pre-configured stream manager.
            consumer_name: Name identifying this consumer within a group.
        """
        self._config = config or EventConfig()
        self._manager = stream_manager or RedisStreamManager(self._config)
        self._consumer_name = consumer_name
        self._handlers: dict[str, list[EventHandler]] = {}
        self._running = False
        self._events_processed = 0

    @property
    def is_connected(self) -> bool:
        """Whether the underlying stream manager is connected."""
        return self._manager.is_connected

    @property
    def is_running(self) -> bool:
        """Whether the consumer is actively consuming events."""
        return self._running

    @property
    def events_processed(self) -> int:
        """Total number of events processed since creation."""
        return self._events_processed

    @property
    def registered_handlers(self) -> dict[str, int]:
        """Map of event types to their handler counts."""
        return {k: len(v) for k, v in self._handlers.items()}

    def connect(self, redis_url: str | None = None) -> bool:
        """Connect to Redis.

        Args:
            redis_url: Override Redis URL. If None, uses config.

        Returns:
            True if connected, False if Redis is unavailable.
        """
        return self._manager.connect(redis_url)

    def disconnect(self) -> None:
        """Disconnect from Redis and stop consuming."""
        self.stop()
        self._manager.disconnect()

    def register_handler(self, event_type: EventType, handler: EventHandler) -> None:
        """Register a handler for a specific event type.

        Multiple handlers can be registered for the same event type.
        They will be called in registration order.

        Args:
            event_type: The type of event this handler should process.
            handler: Callable that takes an Event and returns None.
        """
        key = event_type.value
        if key not in self._handlers:
            self._handlers[key] = []
        self._handlers[key].append(handler)
        logger.debug(
            "Registered handler for '%s' (total: %d)",
            key,
            len(self._handlers[key]),
        )

    def unregister_handler(self, event_type: EventType, handler: EventHandler) -> bool:
        """Remove a previously registered handler.

        Args:
            event_type: The event type the handler was registered for.
            handler: The handler callable to remove.

        Returns:
            True if the handler was found and removed, False otherwise.
        """
        key = event_type.value
        if key in self._handlers and handler in self._handlers[key]:
            self._handlers[key].remove(handler)
            if not self._handlers[key]:
                del self._handlers[key]
            return True
        return False

    async def start_consuming(
        self,
        stream_name: str,
        group_name: str | None = None,
    ) -> None:
        """Start consuming events from a stream.

        This is an async method that runs until stop() is called.
        Events are dispatched to registered handlers based on their
        event_type field.

        Args:
            stream_name: Base name of the stream to consume from.
            group_name: Consumer group name. Defaults to config consumer_group.
        """
        if not self._manager.is_connected:
            logger.warning("Redis not connected. Cannot start consuming.")
            return

        group = group_name or self._config.consumer_group

        # Ensure consumer group exists
        self._manager.create_consumer_group(stream_name, group)

        self._running = True
        logger.info(
            "Started consuming from '%s' (group: %s, consumer: %s)",
            stream_name,
            group,
            self._consumer_name,
        )

        while self._running:
            events = self._manager.read_group(
                stream_name=stream_name,
                group_name=group,
                consumer_name=self._consumer_name,
                block_ms=0,  # Non-blocking for async compatibility
            )

            for event in events:
                self._dispatch_event(event, stream_name, group)

            if not events:
                await asyncio.sleep(self._config.block_ms / 1000.0)

        logger.info("Stopped consuming from '%s'", stream_name)

    def stop(self) -> None:
        """Signal the consumer to stop processing events.

        The consumer will finish processing the current batch before stopping.
        """
        if self._running:
            self._running = False
            logger.info("Stop signal received")

    def _dispatch_event(self, event: Event, stream_name: str, group_name: str) -> None:
        """Dispatch an event to registered handlers.

        After all handlers succeed, the event is acknowledged.
        If any handler raises an exception, the event is NOT acknowledged
        so it can be retried.

        Args:
            event: The event to dispatch.
            stream_name: Stream name for acknowledgment.
            group_name: Group name for acknowledgment.
        """
        event_type = event.data.get("event_type", "")
        handlers = self._handlers.get(event_type, [])

        if not handlers:
            # No handlers registered; acknowledge to prevent redelivery
            self._manager.acknowledge(stream_name, group_name, event.id)
            logger.debug(
                "No handlers for event type '%s', acknowledged message '%s'",
                event_type,
                event.id,
            )
            return

        all_succeeded = True
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.error(
                    "Handler failed for event '%s' (type: %s)",
                    event.id,
                    event_type,
                    exc_info=True,
                )
                all_succeeded = False

        if all_succeeded:
            self._manager.acknowledge(stream_name, group_name, event.id)
            self._events_processed += 1
            logger.debug(
                "Processed and acknowledged event '%s' (type: %s)",
                event.id,
                event_type,
            )

    def __enter__(self) -> EventConsumer:
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
            f"EventConsumer(connected={self.is_connected}, "
            f"running={self._running}, "
            f"handlers={len(self._handlers)}, "
            f"processed={self._events_processed})"
        )
