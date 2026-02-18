"""
Unit tests for Subscription and SubscriptionRegistry.

Tests subscription creation, topic matching (exact and wildcard),
filter evaluation, and registry CRUD operations.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from file_organizer.events.subscription import (
    Subscription,
    SubscriptionRegistry,
    _topic_to_regex,
)

# ------------------------------------------------------------------
# Subscription dataclass
# ------------------------------------------------------------------


class TestSubscription:
    """Tests for the Subscription dataclass."""

    def test_creation_defaults(self) -> None:
        """Subscription has sensible defaults."""
        handler = MagicMock()
        sub = Subscription(topic="file.created", handler=handler)
        assert sub.topic == "file.created"
        assert sub.handler is handler
        assert sub.filter_fn is None
        assert sub.active is True
        assert sub.created_at is not None

    def test_exact_topic_match(self) -> None:
        """Exact topic string matches itself."""
        sub = Subscription(topic="file.created", handler=MagicMock())
        assert sub.matches_topic("file.created") is True
        assert sub.matches_topic("file.deleted") is False

    def test_single_wildcard_match(self) -> None:
        """Single wildcard '*' matches one segment."""
        sub = Subscription(topic="file.*", handler=MagicMock())
        assert sub.matches_topic("file.created") is True
        assert sub.matches_topic("file.deleted") is True
        assert sub.matches_topic("scan.started") is False
        # Single wildcard should NOT match multiple segments
        assert sub.matches_topic("file.a.b") is False

    def test_double_wildcard_match(self) -> None:
        """Double wildcard '**' matches one or more segments."""
        sub = Subscription(topic="file.**", handler=MagicMock())
        assert sub.matches_topic("file.created") is True
        assert sub.matches_topic("file.a.b") is True
        assert sub.matches_topic("file.a.b.c") is True
        assert sub.matches_topic("scan.started") is False

    def test_no_match_different_prefix(self) -> None:
        """Topics with different prefixes do not match."""
        sub = Subscription(topic="file.*", handler=MagicMock())
        assert sub.matches_topic("scan.started") is False

    def test_passes_filter_no_filter(self) -> None:
        """Without a filter, passes_filter always returns True."""
        sub = Subscription(topic="t", handler=MagicMock())
        assert sub.passes_filter({"key": "val"}) is True

    def test_passes_filter_true(self) -> None:
        """Filter returning True passes."""

        def fn(data):
            return data.get("size", 0) > 100

        sub = Subscription(topic="t", handler=MagicMock(), filter_fn=fn)
        assert sub.passes_filter({"size": 200}) is True

    def test_passes_filter_false(self) -> None:
        """Filter returning False rejects."""

        def fn(data):
            return data.get("size", 0) > 100

        sub = Subscription(topic="t", handler=MagicMock(), filter_fn=fn)
        assert sub.passes_filter({"size": 50}) is False

    def test_passes_filter_exception_returns_false(self) -> None:
        """Filter that raises returns False (safe fallback)."""

        def bad_filter(data: dict) -> bool:
            raise ValueError("boom")

        sub = Subscription(topic="t", handler=MagicMock(), filter_fn=bad_filter)
        assert sub.passes_filter({"key": "val"}) is False

    def test_repr(self) -> None:
        """Repr includes topic, filtered/unfiltered, active/inactive."""
        sub = Subscription(topic="file.created", handler=MagicMock())
        r = repr(sub)
        assert "file.created" in r
        assert "unfiltered" in r
        assert "active" in r

    def test_repr_with_filter_inactive(self) -> None:
        """Repr reflects filter and inactive state."""
        sub = Subscription(
            topic="t",
            handler=MagicMock(),
            filter_fn=lambda d: True,
            active=False,
        )
        r = repr(sub)
        assert "filtered" in r
        assert "inactive" in r


# ------------------------------------------------------------------
# SubscriptionRegistry
# ------------------------------------------------------------------


class TestSubscriptionRegistry:
    """Tests for the SubscriptionRegistry."""

    def test_add_subscription(self) -> None:
        """Adding a subscription increases the count."""
        reg = SubscriptionRegistry()
        handler = MagicMock()
        sub = reg.add("file.created", handler)
        assert isinstance(sub, Subscription)
        assert reg.count == 1
        assert len(reg) == 1

    def test_add_multiple_handlers_same_topic(self) -> None:
        """Multiple handlers can be registered for the same topic."""
        reg = SubscriptionRegistry()
        h1, h2 = MagicMock(), MagicMock()
        reg.add("file.created", h1)
        reg.add("file.created", h2)
        assert reg.count == 2

    def test_remove_subscription(self) -> None:
        """Removing a subscription decreases the count."""
        reg = SubscriptionRegistry()
        handler = MagicMock()
        reg.add("file.created", handler)
        assert reg.remove("file.created", handler) is True
        assert reg.count == 0

    def test_remove_nonexistent_returns_false(self) -> None:
        """Removing a handler that was never added returns False."""
        reg = SubscriptionRegistry()
        assert reg.remove("nope", MagicMock()) is False

    def test_deactivate_and_activate(self) -> None:
        """Deactivated subscriptions are excluded from get_for_topic."""
        reg = SubscriptionRegistry()
        handler = MagicMock()
        reg.add("file.created", handler)

        assert reg.deactivate("file.created", handler) is True
        assert reg.get_for_topic("file.created") == []
        assert reg.active_count == 0

        assert reg.activate("file.created", handler) is True
        assert len(reg.get_for_topic("file.created")) == 1
        assert reg.active_count == 1

    def test_get_for_topic_with_wildcard(self) -> None:
        """Wildcard subscriptions match concrete topics."""
        reg = SubscriptionRegistry()
        h_wild = MagicMock()
        h_exact = MagicMock()
        reg.add("file.*", h_wild)
        reg.add("file.created", h_exact)

        matches = reg.get_for_topic("file.created")
        assert len(matches) == 2

    def test_get_for_topic_excludes_non_matching(self) -> None:
        """Non-matching subscriptions are excluded."""
        reg = SubscriptionRegistry()
        reg.add("scan.*", MagicMock())
        assert reg.get_for_topic("file.created") == []

    def test_get_all(self) -> None:
        """get_all returns all subscriptions including inactive ones."""
        reg = SubscriptionRegistry()
        h1, h2 = MagicMock(), MagicMock()
        reg.add("a", h1)
        reg.add("b", h2)
        reg.deactivate("a", h1)

        assert len(reg.get_all()) == 2
        assert len(reg.get_active()) == 1

    def test_clear(self) -> None:
        """clear removes all subscriptions."""
        reg = SubscriptionRegistry()
        reg.add("a", MagicMock())
        reg.add("b", MagicMock())
        removed = reg.clear()
        assert removed == 2
        assert reg.count == 0

    def test_repr(self) -> None:
        """Repr shows total and active counts."""
        reg = SubscriptionRegistry()
        reg.add("a", MagicMock())
        r = repr(reg)
        assert "total=1" in r
        assert "active=1" in r

    def test_add_with_filter(self) -> None:
        """Adding a subscription with a filter stores it correctly."""
        reg = SubscriptionRegistry()

        def fn(d):
            return True

        sub = reg.add("t", MagicMock(), filter_fn=fn)
        assert sub.filter_fn is fn


# ------------------------------------------------------------------
# Wildcard regex helper
# ------------------------------------------------------------------


class TestTopicToRegex:
    """Tests for the _topic_to_regex helper."""

    def test_exact_pattern(self) -> None:
        """Exact patterns compile to literal regex."""
        pat = _topic_to_regex("file.created")
        assert pat.fullmatch("file.created") is not None
        assert pat.fullmatch("file.deleted") is None

    def test_single_star(self) -> None:
        """Single star matches one segment."""
        pat = _topic_to_regex("file.*")
        assert pat.fullmatch("file.created") is not None
        assert pat.fullmatch("file.x.y") is None

    def test_double_star(self) -> None:
        """Double star matches multiple segments."""
        pat = _topic_to_regex("file.**")
        assert pat.fullmatch("file.created") is not None
        assert pat.fullmatch("file.a.b.c") is not None
