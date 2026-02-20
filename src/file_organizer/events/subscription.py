"""Subscription management for the pub/sub event system.

Provides dataclass-based subscription tracking and a registry
for managing multiple handlers per topic with optional filtering.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    """A single subscription binding a handler to a topic.

    Attributes:
        topic: The topic pattern this subscription listens to.
            Supports wildcards (e.g., ``"file.*"``).
        handler: Callable invoked when a matching event arrives.
        filter_fn: Optional predicate applied to event data before
            the handler is called.  When provided, the handler is
            only invoked if ``filter_fn(data)`` returns ``True``.
        created_at: UTC timestamp when the subscription was created.
        active: Whether the subscription is currently active.
    """

    topic: str
    handler: Callable[..., Any]
    filter_fn: Callable[[dict[str, Any]], bool] | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    active: bool = True

    def matches_topic(self, topic: str) -> bool:
        """Check whether *topic* matches this subscription's pattern.

        Matching rules:
        - Exact string match always succeeds.
        - ``"*"`` matches any single topic segment.
        - ``"file.*"`` matches ``"file.created"``, ``"file.deleted"``,
          etc. but not ``"file.a.b"`` (single segment only).
        - ``"file.**"`` (double-star) matches any number of remaining
          segments.

        Args:
            topic: The concrete topic to test against this pattern.

        Returns:
            ``True`` if the topic matches the subscription pattern.
        """
        if self.topic == topic:
            return True

        pattern = _topic_to_regex(self.topic)
        return pattern.fullmatch(topic) is not None

    def passes_filter(self, data: dict[str, Any]) -> bool:
        """Evaluate the optional filter predicate.

        Args:
            data: Event payload dictionary.

        Returns:
            ``True`` if no filter is set, or if the filter returns ``True``.
        """
        if self.filter_fn is None:
            return True
        try:
            return bool(self.filter_fn(data))
        except Exception:
            logger.warning(
                "Filter function raised an exception for topic '%s'",
                self.topic,
                exc_info=True,
            )
            return False

    def __repr__(self) -> str:
        filtered = "filtered" if self.filter_fn is not None else "unfiltered"
        status = "active" if self.active else "inactive"
        return f"Subscription(topic={self.topic!r}, {filtered}, {status})"


class SubscriptionRegistry:
    """Registry that tracks subscriptions and dispatches topic lookups.

    Thread-safe for single-threaded async use.  Not safe for concurrent
    mutation from multiple OS threads without external synchronisation.
    """

    def __init__(self) -> None:
        self._subscriptions: list[Subscription] = []

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(
        self,
        topic: str,
        handler: Callable[..., Any],
        filter_fn: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Subscription:
        """Create and register a new subscription.

        Args:
            topic: Topic pattern (may include wildcards).
            handler: Callable to invoke on matching events.
            filter_fn: Optional filter predicate.

        Returns:
            The newly created :class:`Subscription`.
        """
        sub = Subscription(
            topic=topic,
            handler=handler,
            filter_fn=filter_fn,
        )
        self._subscriptions.append(sub)
        logger.debug("Added subscription: %s", sub)
        return sub

    def remove(self, topic: str, handler: Callable[..., Any]) -> bool:
        """Remove the first subscription matching *topic* and *handler*.

        The subscription is fully removed from the registry (not just
        deactivated).

        Args:
            topic: Exact topic string used when the subscription was added.
            handler: The handler callable to match.

        Returns:
            ``True`` if a matching subscription was found and removed.
        """
        for i, sub in enumerate(self._subscriptions):
            if sub.topic == topic and sub.handler is handler:
                self._subscriptions.pop(i)
                logger.debug("Removed subscription: %s", sub)
                return True
        return False

    def deactivate(self, topic: str, handler: Callable[..., Any]) -> bool:
        """Deactivate (but do not remove) a subscription.

        Deactivated subscriptions remain in the registry but are
        excluded from :meth:`get_for_topic` results.

        Args:
            topic: Exact topic string.
            handler: Handler callable.

        Returns:
            ``True`` if the subscription was found and deactivated.
        """
        for sub in self._subscriptions:
            if sub.topic == topic and sub.handler is handler:
                sub.active = False
                return True
        return False

    def activate(self, topic: str, handler: Callable[..., Any]) -> bool:
        """Re-activate a previously deactivated subscription.

        Args:
            topic: Exact topic string.
            handler: Handler callable.

        Returns:
            ``True`` if the subscription was found and activated.
        """
        for sub in self._subscriptions:
            if sub.topic == topic and sub.handler is handler:
                sub.active = True
                return True
        return False

    def clear(self) -> int:
        """Remove all subscriptions.

        Returns:
            Number of subscriptions that were removed.
        """
        count = len(self._subscriptions)
        self._subscriptions.clear()
        return count

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_for_topic(self, topic: str) -> list[Subscription]:
        """Return all active subscriptions whose pattern matches *topic*.

        Inactive subscriptions are excluded.

        Args:
            topic: A concrete (non-wildcard) topic name.

        Returns:
            List of matching active subscriptions.
        """
        return [sub for sub in self._subscriptions if sub.active and sub.matches_topic(topic)]

    def get_all(self) -> list[Subscription]:
        """Return a shallow copy of every subscription (active or not).

        Returns:
            List of all subscriptions in registration order.
        """
        return list(self._subscriptions)

    def get_active(self) -> list[Subscription]:
        """Return only active subscriptions.

        Returns:
            List of active subscriptions in registration order.
        """
        return [sub for sub in self._subscriptions if sub.active]

    @property
    def count(self) -> int:
        """Total number of subscriptions (active and inactive)."""
        return len(self._subscriptions)

    @property
    def active_count(self) -> int:
        """Number of currently active subscriptions."""
        return sum(1 for sub in self._subscriptions if sub.active)

    def __len__(self) -> int:
        return len(self._subscriptions)

    def __repr__(self) -> str:
        return f"SubscriptionRegistry(total={self.count}, active={self.active_count})"


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_REGEX_CACHE: dict[str, re.Pattern[str]] = {}


def _topic_to_regex(pattern: str) -> re.Pattern[str]:
    """Convert a topic pattern with wildcards to a compiled regex.

    Wildcard rules:
    - ``*`` matches exactly one segment (no dots).
    - ``**`` matches one or more segments (including dots).

    Results are cached for repeated lookups.

    Args:
        pattern: Topic pattern string.

    Returns:
        Compiled regex.
    """
    if pattern in _REGEX_CACHE:
        return _REGEX_CACHE[pattern]

    # Split on '.' and convert each segment
    parts: list[str] = []
    for segment in pattern.split("."):
        if segment == "**":
            parts.append(r".+")
        elif segment == "*":
            parts.append(r"[^.]+")
        else:
            parts.append(re.escape(segment))

    compiled = re.compile(r"\.".join(parts))
    _REGEX_CACHE[pattern] = compiled
    return compiled
