"""
Unit tests for PubSubManager.

Tests topic-based routing, wildcard matching, event filtering,
publish/subscribe lifecycle, middleware integration, and edge cases.
All Redis operations are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.events.middleware import (
    LoggingMiddleware,
    MetricsMiddleware,
    MiddlewarePipeline,
)
from file_organizer.events.pubsub import PubSubManager, _serialize, _topic_to_stream
from file_organizer.events.stream import RedisStreamManager
from file_organizer.events.subscription import Subscription, SubscriptionRegistry

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def mock_manager() -> MagicMock:
    """Create a mock RedisStreamManager."""
    manager = MagicMock(spec=RedisStreamManager)
    manager.is_connected = True
    manager.connect.return_value = True
    manager.publish.return_value = "1234567890-0"
    return manager


@pytest.fixture
def pubsub(mock_manager: MagicMock) -> PubSubManager:
    """Create a PubSubManager with mocked stream manager."""
    return PubSubManager(stream_manager=mock_manager)


# ------------------------------------------------------------------
# Connection lifecycle
# ------------------------------------------------------------------


class TestPubSubConnection:
    """Tests for connect/disconnect lifecycle."""

    def test_connect_delegates_to_manager(self, mock_manager: MagicMock) -> None:
        """connect() delegates to the underlying stream manager."""
        ps = PubSubManager(stream_manager=mock_manager)
        assert ps.connect() is True
        mock_manager.connect.assert_called_once()

    def test_disconnect_delegates_to_manager(self, mock_manager: MagicMock) -> None:
        """disconnect() delegates to the stream manager."""
        ps = PubSubManager(stream_manager=mock_manager)
        ps.disconnect()
        mock_manager.disconnect.assert_called_once()

    def test_is_connected_property(self, mock_manager: MagicMock) -> None:
        """is_connected reflects stream manager state."""
        ps = PubSubManager(stream_manager=mock_manager)
        assert ps.is_connected is True
        mock_manager.is_connected = False
        assert ps.is_connected is False

    def test_context_manager(self, mock_manager: MagicMock) -> None:
        """PubSubManager works as a context manager."""
        with PubSubManager(stream_manager=mock_manager) as ps:
            assert ps.is_connected is True
        mock_manager.disconnect.assert_called_once()


# ------------------------------------------------------------------
# Subscribe / Unsubscribe
# ------------------------------------------------------------------


class TestPubSubSubscribe:
    """Tests for subscribe and unsubscribe."""

    def test_subscribe_returns_subscription(self, pubsub: PubSubManager) -> None:
        """subscribe() returns a Subscription object."""
        handler = MagicMock()
        sub = pubsub.subscribe("file.created", handler)
        assert isinstance(sub, Subscription)
        assert sub.topic == "file.created"
        assert sub.active is True

    def test_subscribe_with_filter(self, pubsub: PubSubManager) -> None:
        """subscribe() stores the filter function."""

        def fn(d):
            return d.get("size", 0) > 100

        sub = pubsub.subscribe("file.created", MagicMock(), filter_fn=fn)
        assert sub.filter_fn is fn

    def test_unsubscribe_existing(self, pubsub: PubSubManager) -> None:
        """unsubscribe() removes the handler."""
        handler = MagicMock()
        pubsub.subscribe("file.created", handler)
        assert pubsub.unsubscribe("file.created", handler) is True
        assert pubsub.registry.count == 0

    def test_unsubscribe_nonexistent(self, pubsub: PubSubManager) -> None:
        """unsubscribe() returns False for unknown handlers."""
        assert pubsub.unsubscribe("nope", MagicMock()) is False

    def test_multiple_handlers_same_topic(self, pubsub: PubSubManager) -> None:
        """Multiple handlers can subscribe to the same topic."""
        h1, h2, h3 = MagicMock(), MagicMock(), MagicMock()
        pubsub.subscribe("file.created", h1)
        pubsub.subscribe("file.created", h2)
        pubsub.subscribe("file.created", h3)
        assert pubsub.registry.count == 3


# ------------------------------------------------------------------
# Publish
# ------------------------------------------------------------------


class TestPubSubPublish:
    """Tests for publish and dispatch."""

    def test_publish_returns_message_id(
        self, pubsub: PubSubManager, mock_manager: MagicMock
    ) -> None:
        """publish() returns the Redis message ID."""
        msg_id = pubsub.publish("file.created", {"path": "/tmp/f.txt"})
        assert msg_id == "1234567890-0"
        assert pubsub.publish_count == 1

    def test_publish_calls_stream_manager(
        self, pubsub: PubSubManager, mock_manager: MagicMock
    ) -> None:
        """publish() writes to the correct Redis stream."""
        pubsub.publish("file.created", {"path": "/tmp/f.txt"})
        mock_manager.publish.assert_called_once()
        call_args = mock_manager.publish.call_args
        # publish is called with positional args: (stream_name, event_data)
        assert call_args[0][0] == "pubsub:file:created"

    def test_publish_dispatches_to_handler(self, pubsub: PubSubManager) -> None:
        """publish() invokes matching handlers synchronously."""
        handler = MagicMock()
        pubsub.subscribe("file.created", handler)
        pubsub.publish("file.created", {"path": "/tmp/f.txt"})
        handler.assert_called_once()

    def test_publish_dispatches_to_wildcard_handler(self, pubsub: PubSubManager) -> None:
        """Wildcard subscribers receive matching events."""
        handler = MagicMock()
        pubsub.subscribe("file.*", handler)
        pubsub.publish("file.created", {"path": "/tmp/f.txt"})
        handler.assert_called_once()

    def test_publish_does_not_dispatch_to_non_matching(self, pubsub: PubSubManager) -> None:
        """Non-matching handlers are not invoked."""
        handler = MagicMock()
        pubsub.subscribe("scan.*", handler)
        pubsub.publish("file.created", {"path": "/tmp/f.txt"})
        handler.assert_not_called()

    def test_publish_with_filter_passes(self, pubsub: PubSubManager) -> None:
        """Handler is called when filter returns True."""
        handler = MagicMock()
        pubsub.subscribe(
            "file.created",
            handler,
            filter_fn=lambda d: d.get("size", 0) > 100,
        )
        pubsub.publish("file.created", {"size": 200})
        handler.assert_called_once()

    def test_publish_with_filter_blocks(self, pubsub: PubSubManager) -> None:
        """Handler is NOT called when filter returns False."""
        handler = MagicMock()
        pubsub.subscribe(
            "file.created",
            handler,
            filter_fn=lambda d: d.get("size", 0) > 100,
        )
        pubsub.publish("file.created", {"size": 50})
        handler.assert_not_called()

    def test_publish_multiple_handlers_all_called(self, pubsub: PubSubManager) -> None:
        """All matching handlers are called for a single publish."""
        h1, h2 = MagicMock(), MagicMock()
        pubsub.subscribe("file.created", h1)
        pubsub.subscribe("file.*", h2)
        pubsub.publish("file.created", {"path": "/tmp/f.txt"})
        h1.assert_called_once()
        h2.assert_called_once()

    def test_publish_handler_error_does_not_stop_others(self, pubsub: PubSubManager) -> None:
        """A handler error does not prevent other handlers from running."""
        h1 = MagicMock(side_effect=RuntimeError("boom"))
        h2 = MagicMock()
        pubsub.subscribe("file.created", h1)
        pubsub.subscribe("file.created", h2)
        pubsub.publish("file.created", {"path": "/tmp/f.txt"})
        h1.assert_called_once()
        h2.assert_called_once()

    def test_publish_redis_failure_returns_none(
        self, pubsub: PubSubManager, mock_manager: MagicMock
    ) -> None:
        """When Redis publish fails, returns None."""
        mock_manager.publish.return_value = None
        msg_id = pubsub.publish("file.created", {"path": "/tmp/f.txt"})
        assert msg_id is None
        assert pubsub.publish_count == 0

    def test_publish_double_wildcard(self, pubsub: PubSubManager) -> None:
        """Double wildcard '**' matches multi-segment topics."""
        handler = MagicMock()
        pubsub.subscribe("file.**", handler)
        pubsub.publish("file.a.b.c", {"key": "val"})
        handler.assert_called_once()

    def test_publish_no_subscribers(self, pubsub: PubSubManager, mock_manager: MagicMock) -> None:
        """Publishing with no subscribers still writes to Redis."""
        msg_id = pubsub.publish("orphan.topic", {"key": "val"})
        assert msg_id == "1234567890-0"
        mock_manager.publish.assert_called_once()

    def test_publish_after_unsubscribe(self, pubsub: PubSubManager) -> None:
        """After unsubscribe, handler is no longer invoked."""
        handler = MagicMock()
        pubsub.subscribe("file.created", handler)
        pubsub.unsubscribe("file.created", handler)
        pubsub.publish("file.created", {"path": "/tmp/f.txt"})
        handler.assert_not_called()


# ------------------------------------------------------------------
# Middleware integration
# ------------------------------------------------------------------


class TestPubSubMiddleware:
    """Tests for middleware integration in PubSubManager."""

    def test_middleware_before_publish_cancel(self, mock_manager: MagicMock) -> None:
        """Middleware can cancel publish by returning None."""

        class CancelMiddleware:
            def before_publish(self, topic: str, data: dict) -> None:
                return None

        pipeline = MiddlewarePipeline()
        pipeline.add(CancelMiddleware())
        ps = PubSubManager(stream_manager=mock_manager, pipeline=pipeline)
        result = ps.publish("file.created", {"path": "/tmp/f.txt"})
        assert result is None
        mock_manager.publish.assert_not_called()

    def test_middleware_after_publish_called(self, mock_manager: MagicMock) -> None:
        """after_publish middleware is called after Redis write."""
        tracker = MagicMock()

        class TrackMiddleware:
            def before_publish(self, topic: str, data: dict) -> dict:
                return data

            def after_publish(self, topic: str, data: dict, msg_id: str | None) -> None:
                tracker(msg_id)

        pipeline = MiddlewarePipeline()
        pipeline.add(TrackMiddleware())
        ps = PubSubManager(stream_manager=mock_manager, pipeline=pipeline)
        ps.publish("t", {"k": "v"})
        tracker.assert_called_once_with("1234567890-0")

    def test_metrics_middleware_integration(self, mock_manager: MagicMock) -> None:
        """MetricsMiddleware counts publishes through the pipeline."""
        metrics = MetricsMiddleware()
        pipeline = MiddlewarePipeline()
        pipeline.add(metrics)
        ps = PubSubManager(stream_manager=mock_manager, pipeline=pipeline)
        ps.publish("t1", {"a": 1})
        ps.publish("t2", {"b": 2})
        assert metrics.publish_count == 2

    def test_logging_middleware_integration(self, mock_manager: MagicMock) -> None:
        """LoggingMiddleware does not interfere with publish."""
        pipeline = MiddlewarePipeline()
        pipeline.add(LoggingMiddleware())
        ps = PubSubManager(stream_manager=mock_manager, pipeline=pipeline)
        msg_id = ps.publish("t", {"k": "v"})
        assert msg_id is not None

    def test_pipeline_property(self, pubsub: PubSubManager) -> None:
        """pipeline property exposes the MiddlewarePipeline."""
        assert isinstance(pubsub.pipeline, MiddlewarePipeline)


# ------------------------------------------------------------------
# Utility / edge-case
# ------------------------------------------------------------------


class TestPubSubUtility:
    """Tests for utility methods and edge cases."""

    def test_get_subscriptions(self, pubsub: PubSubManager) -> None:
        """get_subscriptions returns matching active subs."""
        h1, h2 = MagicMock(), MagicMock()
        pubsub.subscribe("file.created", h1)
        pubsub.subscribe("file.*", h2)
        subs = pubsub.get_subscriptions("file.created")
        assert len(subs) == 2

    def test_repr(self, pubsub: PubSubManager) -> None:
        """repr includes connection, subscription count, publish count."""
        r = repr(pubsub)
        assert "connected=" in r
        assert "subscriptions=" in r
        assert "published=" in r

    def test_registry_property(self, pubsub: PubSubManager) -> None:
        """registry property returns the SubscriptionRegistry."""
        assert isinstance(pubsub.registry, SubscriptionRegistry)

    def test_default_config(self) -> None:
        """PubSubManager creates default config when none provided."""
        ps = PubSubManager()
        assert ps.is_connected is False


# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------


class TestHelpers:
    """Tests for module-level helper functions."""

    def test_topic_to_stream(self) -> None:
        """Topic dots are converted to colons with pubsub prefix."""
        assert _topic_to_stream("file.created") == "pubsub:file:created"
        assert _topic_to_stream("scan.started") == "pubsub:scan:started"
        assert _topic_to_stream("a.b.c") == "pubsub:a:b:c"

    def test_serialize(self) -> None:
        """_serialize produces a dict with topic, payload, and timestamp."""
        result = _serialize({"key": "val"}, "file.created")
        assert result["topic"] == "file.created"
        assert "payload" in result
        assert "timestamp" in result
        # payload is JSON-encoded
        import json

        decoded = json.loads(result["payload"])
        assert decoded == {"key": "val"}
