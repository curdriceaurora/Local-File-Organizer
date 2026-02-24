"""Event middleware pipeline for the pub/sub system.

Provides a protocol-based middleware architecture that intercepts
events at publish and consume time.  Includes ready-made middleware
for logging, metrics collection, and retry logic.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# Protocol
# ------------------------------------------------------------------


@runtime_checkable
class Middleware(Protocol):
    """Protocol that all event middleware must satisfy.

    Implementors may define any subset of the four hooks.  Missing
    hooks are silently skipped by the :class:`MiddlewarePipeline`.
    """

    def before_publish(self, topic: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Called before an event is published.

        Args:
            topic: Target topic.
            data: Event payload (may be mutated).

        Returns:
            The (possibly modified) data dict to continue publishing,
            or ``None`` to **cancel** the publish.
        """
        ...  # pragma: no cover

    def after_publish(
        self,
        topic: str,
        data: dict[str, Any],
        message_id: str | None,
    ) -> None:
        """Called after an event has been published.

        Args:
            topic: Target topic.
            data: Event payload that was published.
            message_id: Redis message ID, or ``None`` if publish failed.
        """
        ...  # pragma: no cover

    def before_consume(self, topic: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Called before a consumed event is dispatched to handlers.

        Args:
            topic: Topic the event was published to.
            data: Event payload.

        Returns:
            The data dict to pass to handlers, or ``None`` to skip
            handler dispatch entirely.
        """
        ...  # pragma: no cover

    def after_consume(
        self,
        topic: str,
        data: dict[str, Any],
        error: Exception | None,
    ) -> None:
        """Called after handler dispatch completes (success or failure).

        Args:
            topic: Topic the event belonged to.
            data: Event payload.
            error: The exception if a handler failed, else ``None``.
        """
        ...  # pragma: no cover


# ------------------------------------------------------------------
# Pipeline
# ------------------------------------------------------------------


class MiddlewarePipeline:
    """Ordered chain of middleware applied to every event.

    Middleware are executed in **registration order** for ``before_*``
    hooks and in **reverse order** for ``after_*`` hooks (onion model).
    """

    def __init__(self) -> None:
        """Initialize the middleware pipeline."""
        self._middleware: list[Middleware] = []

    def add(self, mw: Middleware) -> None:
        """Append a middleware to the end of the pipeline.

        Args:
            mw: Middleware instance to add.
        """
        self._middleware.append(mw)
        logger.debug("Added middleware: %s", type(mw).__name__)

    def remove(self, mw: Middleware) -> bool:
        """Remove a middleware from the pipeline.

        Args:
            mw: The exact middleware instance to remove.

        Returns:
            ``True`` if found and removed.
        """
        try:
            self._middleware.remove(mw)
            return True
        except ValueError:
            return False

    def clear(self) -> None:
        """Remove all middleware from the pipeline."""
        self._middleware.clear()

    @property
    def count(self) -> int:
        """Number of middleware in the pipeline."""
        return len(self._middleware)

    # ------------------------------------------------------------------
    # Hook execution
    # ------------------------------------------------------------------

    def run_before_publish(self, topic: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Execute ``before_publish`` on all middleware in order.

        If any middleware returns ``None`` the chain is short-circuited
        and ``None`` is returned (publish should be cancelled).

        Args:
            topic: Target topic.
            data: Event payload.

        Returns:
            Possibly-modified data, or ``None`` to cancel.
        """
        current: dict[str, Any] | None = data
        for mw in self._middleware:
            if current is None:
                break
            if hasattr(mw, "before_publish"):
                try:
                    current = mw.before_publish(topic, current)
                except Exception:
                    logger.error(
                        "Middleware %s.before_publish raised",
                        type(mw).__name__,
                        exc_info=True,
                    )
                    # Treat middleware errors as non-fatal; continue
        return current

    def run_after_publish(
        self,
        topic: str,
        data: dict[str, Any],
        message_id: str | None,
    ) -> None:
        """Execute ``after_publish`` on all middleware in **reverse** order.

        Args:
            topic: Target topic.
            data: Event payload.
            message_id: Redis message ID or ``None``.
        """
        for mw in reversed(self._middleware):
            if hasattr(mw, "after_publish"):
                try:
                    mw.after_publish(topic, data, message_id)
                except Exception:
                    logger.error(
                        "Middleware %s.after_publish raised",
                        type(mw).__name__,
                        exc_info=True,
                    )

    def run_before_consume(self, topic: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Execute ``before_consume`` on all middleware in order.

        Args:
            topic: Topic the event belongs to.
            data: Event payload.

        Returns:
            Possibly-modified data, or ``None`` to skip dispatch.
        """
        current: dict[str, Any] | None = data
        for mw in self._middleware:
            if current is None:
                break
            if hasattr(mw, "before_consume"):
                try:
                    current = mw.before_consume(topic, current)
                except Exception:
                    logger.error(
                        "Middleware %s.before_consume raised",
                        type(mw).__name__,
                        exc_info=True,
                    )
        return current

    def run_after_consume(
        self,
        topic: str,
        data: dict[str, Any],
        error: Exception | None,
    ) -> None:
        """Execute ``after_consume`` on all middleware in **reverse** order.

        Args:
            topic: Topic the event belonged to.
            data: Event payload.
            error: Handler exception or ``None``.
        """
        for mw in reversed(self._middleware):
            if hasattr(mw, "after_consume"):
                try:
                    mw.after_consume(topic, data, error)
                except Exception:
                    logger.error(
                        "Middleware %s.after_consume raised",
                        type(mw).__name__,
                        exc_info=True,
                    )

    def __len__(self) -> int:
        """Return the number of registered middleware."""
        return len(self._middleware)

    def __repr__(self) -> str:
        """Return a string representation of this pipeline."""
        names = [type(mw).__name__ for mw in self._middleware]
        return f"MiddlewarePipeline({names})"


# ------------------------------------------------------------------
# Built-in middleware
# ------------------------------------------------------------------


class LoggingMiddleware:
    """Logs every event at publish and consume time.

    Uses the standard :mod:`logging` module at ``INFO`` level for
    publish/consume events and ``WARNING`` for errors.
    """

    def __init__(self, logger_name: str = "file_organizer.events.pubsub") -> None:
        """Initialize the logging middleware with the given logger name."""
        self._logger = logging.getLogger(logger_name)

    def before_publish(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        """Log event data before publishing to topic."""
        self._logger.info("Publishing to '%s': %s", topic, data)
        return data

    def after_publish(
        self,
        topic: str,
        data: dict[str, Any],
        message_id: str | None,
    ) -> None:
        """Log the outcome after publishing to topic."""
        if message_id is not None:
            self._logger.info("Published to '%s' (ID: %s)", topic, message_id)
        else:
            self._logger.warning("Failed to publish to '%s'", topic)

    def before_consume(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        """Log event data before dispatching to handlers."""
        self._logger.info("Consuming from '%s': %s", topic, data)
        return data

    def after_consume(
        self,
        topic: str,
        data: dict[str, Any],
        error: Exception | None,
    ) -> None:
        """Log outcome after handlers have consumed the event."""
        if error is not None:
            self._logger.warning("Handler error on '%s': %s", topic, error)
        else:
            self._logger.info("Consumed from '%s' successfully", topic)


@dataclass
class MetricsMiddleware:
    """Tracks event counts and handler latency.

    Attributes:
        publish_count: Total events published.
        publish_errors: Events that failed to publish.
        consume_count: Total events consumed.
        consume_errors: Events where a handler raised.
        total_consume_time_ms: Cumulative handler latency in milliseconds.
    """

    publish_count: int = 0
    publish_errors: int = 0
    consume_count: int = 0
    consume_errors: int = 0
    total_consume_time_ms: float = 0.0
    _consume_start: float = field(default=0.0, repr=False)

    # Per-topic counters
    topic_publish_counts: dict[str, int] = field(default_factory=dict)
    topic_consume_counts: dict[str, int] = field(default_factory=dict)

    def before_publish(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        """Track event data before publishing; return data unchanged."""
        return data

    def after_publish(
        self,
        topic: str,
        data: dict[str, Any],
        message_id: str | None,
    ) -> None:
        """Record publish count or error after publishing."""
        if message_id is not None:
            self.publish_count += 1
            self.topic_publish_counts[topic] = self.topic_publish_counts.get(topic, 0) + 1
        else:
            self.publish_errors += 1

    def before_consume(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        """Record start time before dispatching to handlers."""
        self._consume_start = time.monotonic()
        return data

    def after_consume(
        self,
        topic: str,
        data: dict[str, Any],
        error: Exception | None,
    ) -> None:
        """Record latency and update consume counters after handlers run."""
        elapsed = (time.monotonic() - self._consume_start) * 1000.0
        self.total_consume_time_ms += elapsed
        if error is not None:
            self.consume_errors += 1
        else:
            self.consume_count += 1
            self.topic_consume_counts[topic] = self.topic_consume_counts.get(topic, 0) + 1

    @property
    def avg_consume_time_ms(self) -> float:
        """Average handler latency in milliseconds."""
        total = self.consume_count + self.consume_errors
        if total == 0:
            return 0.0
        return self.total_consume_time_ms / total

    def reset(self) -> None:
        """Reset all counters to zero."""
        self.publish_count = 0
        self.publish_errors = 0
        self.consume_count = 0
        self.consume_errors = 0
        self.total_consume_time_ms = 0.0
        self.topic_publish_counts.clear()
        self.topic_consume_counts.clear()


class RetryMiddleware:
    """Retries failed handler invocations.

    When a handler raises during consume, this middleware re-invokes
    the handler up to ``max_retries`` times.  The retry logic is
    cooperative: it stores the retry callable and count, and the
    :class:`PubSubManager` calls :meth:`should_retry` after an error.

    Attributes:
        max_retries: Maximum retry attempts per event.
        retry_delay: Seconds to wait between retries (currently
            informational; actual sleeping is left to the caller).
    """

    def __init__(
        self,
        max_retries: int = 3,
        retry_delay: float = 0.1,
    ) -> None:
        """Initialize the retry middleware with retry limits."""
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._attempt_counts: dict[str, int] = {}
        self._total_retries: int = 0

    def before_publish(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        """Pass through event data before publishing."""
        return data

    def after_publish(
        self,
        topic: str,
        data: dict[str, Any],
        message_id: str | None,
    ) -> None:
        """No-op after publish; retry logic applies only to consume."""
        pass

    def before_consume(self, topic: str, data: dict[str, Any]) -> dict[str, Any]:
        """Reset the attempt counter for this event before dispatching."""
        # Reset attempt counter for this event
        event_key = f"{topic}:{id(data)}"
        self._attempt_counts[event_key] = 0
        return data

    def after_consume(
        self,
        topic: str,
        data: dict[str, Any],
        error: Exception | None,
    ) -> None:
        """Increment the attempt counter on handler error."""
        if error is not None:
            event_key = f"{topic}:{id(data)}"
            self._attempt_counts[event_key] = self._attempt_counts.get(event_key, 0) + 1

    def should_retry(self, topic: str, data: dict[str, Any]) -> bool:
        """Check whether the event should be retried.

        Args:
            topic: Event topic.
            data: Event payload (uses ``id()`` for tracking).

        Returns:
            ``True`` if more retries are available.
        """
        event_key = f"{topic}:{id(data)}"
        attempts = self._attempt_counts.get(event_key, 0)
        if attempts < self.max_retries:
            self._total_retries += 1
            return True
        return False

    @property
    def total_retries(self) -> int:
        """Total number of retry attempts executed."""
        return self._total_retries

    def reset(self) -> None:
        """Clear all retry state."""
        self._attempt_counts.clear()
        self._total_retries = 0
