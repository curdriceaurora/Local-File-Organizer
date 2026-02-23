"""Publish/Subscribe manager built on top of Redis Streams.

Provides topic-based routing with wildcard support, per-subscription
filtering, and an optional middleware pipeline.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from file_organizer.events.config import EventConfig
from file_organizer.events.middleware import MiddlewarePipeline
from file_organizer.events.stream import RedisStreamManager
from file_organizer.events.subscription import Subscription, SubscriptionRegistry

logger = logging.getLogger(__name__)


def _topic_to_stream(topic: str) -> str:
    """Convert a topic name to a Redis stream name.

    Dots are replaced with colons so that ``"file.created"`` maps to
    the stream ``"pubsub:file:created"``.

    Args:
        topic: Dot-delimited topic name.

    Returns:
        Stream name string.
    """
    return f"pubsub:{topic.replace('.', ':')}"


class PubSubManager:
    """High-level publish/subscribe layer over Redis Streams.

    Topics are dot-delimited strings (e.g. ``"file.created"``).
    Subscriptions may use wildcards:

    - ``"file.*"`` matches any single sub-segment.
    - ``"file.**"`` matches one or more sub-segments.

    Each subscription can carry an optional *filter function* that
    receives the event data dict and returns a bool.

    Example::

        pubsub = PubSubManager()
        pubsub.connect()

        def on_file_created(data: dict) -> None:
            print("New file:", data["path"])

        pubsub.subscribe("file.created", on_file_created)
        pubsub.publish("file.created", {"path": "/tmp/hello.txt"})
        pubsub.disconnect()
    """

    def __init__(
        self,
        config: EventConfig | None = None,
        stream_manager: RedisStreamManager | None = None,
        pipeline: MiddlewarePipeline | None = None,
    ) -> None:
        """Initialize the PubSubManager with optional config and backends."""
        self._config = config or EventConfig()
        self._manager = stream_manager or RedisStreamManager(self._config)
        self._registry = SubscriptionRegistry()
        self._pipeline = pipeline or MiddlewarePipeline()
        self._publish_count = 0

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    @property
    def is_connected(self) -> bool:
        """Whether the underlying stream manager is connected."""
        return self._manager.is_connected

    @property
    def registry(self) -> SubscriptionRegistry:
        """The subscription registry (read-only access)."""
        return self._registry

    @property
    def pipeline(self) -> MiddlewarePipeline:
        """The middleware pipeline."""
        return self._pipeline

    @property
    def publish_count(self) -> int:
        """Total number of successful publishes."""
        return self._publish_count

    def connect(self, redis_url: str | None = None) -> bool:
        """Connect to Redis.

        Args:
            redis_url: Override Redis URL.

        Returns:
            ``True`` if connected.
        """
        return self._manager.connect(redis_url)

    def disconnect(self) -> None:
        """Disconnect from Redis and clear subscriptions."""
        self._manager.disconnect()

    # ------------------------------------------------------------------
    # Subscribe / Unsubscribe
    # ------------------------------------------------------------------

    def subscribe(
        self,
        topic: str,
        handler: Callable[..., Any],
        filter_fn: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Subscription:
        """Register a handler for a topic pattern.

        Args:
            topic: Topic pattern (supports ``*`` and ``**`` wildcards).
            handler: Callable invoked with the event data dict.
            filter_fn: Optional predicate.  Handler is only called
                when ``filter_fn(data)`` returns ``True``.

        Returns:
            The :class:`Subscription` object (can be used to check status).
        """
        sub = self._registry.add(topic, handler, filter_fn)
        logger.info("Subscribed to '%s'", topic)
        return sub

    def unsubscribe(self, topic: str, handler: Callable[..., Any]) -> bool:
        """Remove a previously registered handler.

        Args:
            topic: Exact topic string used during subscribe.
            handler: The handler callable.

        Returns:
            ``True`` if found and removed.
        """
        removed = self._registry.remove(topic, handler)
        if removed:
            logger.info("Unsubscribed from '%s'", topic)
        return removed

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    def publish(self, topic: str, data: dict[str, Any]) -> str | None:
        """Publish an event to a topic.

        The event is written to a Redis Stream whose name is derived
        from the topic.  All registered subscribers whose patterns
        match are then invoked **synchronously** with the data.

        Middleware ``before_publish`` / ``after_publish`` hooks are
        executed around the Redis write.

        Args:
            topic: Dot-delimited topic name.
            data: Arbitrary event payload.

        Returns:
            Redis message ID if the stream write succeeded, ``None``
            otherwise.
        """
        # --- before_publish middleware ---
        processed = self._pipeline.run_before_publish(topic, data)
        if processed is None:
            logger.debug("Publish cancelled by middleware for '%s'", topic)
            self._pipeline.run_after_publish(topic, data, None)
            return None

        # --- Redis write ---
        stream = _topic_to_stream(topic)
        serialized = _serialize(processed, topic)
        message_id = self._manager.publish(stream, serialized)

        if message_id is not None:
            self._publish_count += 1

        # --- after_publish middleware ---
        self._pipeline.run_after_publish(topic, processed, message_id)

        # --- local dispatch to matching subscribers ---
        self._dispatch(topic, processed)

        return message_id

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, topic: str, data: dict[str, Any]) -> None:
        """Dispatch an event to all matching, active subscribers.

        Applies the middleware ``before_consume`` / ``after_consume``
        hooks and each subscription's filter function.

        Args:
            topic: Concrete topic name.
            data: Event payload.
        """
        subs = self._registry.get_for_topic(topic)
        if not subs:
            return

        # --- before_consume middleware ---
        processed = self._pipeline.run_before_consume(topic, data)
        if processed is None:
            logger.debug("Consume cancelled by middleware for '%s'", topic)
            return

        for sub in subs:
            if not sub.passes_filter(processed):
                logger.debug("Event filtered out for handler on '%s'", sub.topic)
                continue

            error: Exception | None = None
            try:
                sub.handler(processed)
            except Exception as exc:
                error = exc
                logger.error(
                    "Handler error on topic '%s': %s",
                    topic,
                    exc,
                    exc_info=True,
                )

            # --- after_consume middleware ---
            self._pipeline.run_after_consume(topic, processed, error)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def get_subscriptions(self, topic: str) -> list[Subscription]:
        """Return all active subscriptions matching a topic.

        Args:
            topic: Concrete topic name.

        Returns:
            List of matching :class:`Subscription` objects.
        """
        return self._registry.get_for_topic(topic)

    def __enter__(self) -> PubSubManager:
        """Connect and return self for use as a context manager."""
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Disconnect when exiting the context manager."""
        self.disconnect()

    def __repr__(self) -> str:
        """Return a string representation of this manager."""
        return (
            f"PubSubManager(connected={self.is_connected}, "
            f"subscriptions={self._registry.count}, "
            f"published={self._publish_count})"
        )


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _serialize(data: dict[str, Any], topic: str) -> dict[str, str]:
    """Serialize an event payload to Redis-compatible string dict.

    Args:
        data: Arbitrary event data.
        topic: Topic name (included in the serialized form).

    Returns:
        Dictionary with string keys and values.
    """
    return {
        "topic": topic,
        "payload": json.dumps(data),
        "timestamp": datetime.now(UTC).isoformat(),
    }
