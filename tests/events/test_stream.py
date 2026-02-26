"""
Unit tests for RedisStreamManager.

Tests Redis Streams operations including connect, disconnect, publish,
consume, acknowledge, and consumer group management. All tests mock
Redis to avoid requiring a running Redis instance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.events.config import EventConfig
from file_organizer.events.stream import (
    Event,
    RedisStreamManager,
    _parse_timestamp_from_id,
)


@pytest.mark.unit
class TestEvent:
    """Tests for the Event dataclass."""

    def test_create_event(self):
        """Test creating an Event with all fields."""
        now = datetime.now(UTC)
        event = Event(
            id="1234567890-0",
            stream="test:stream",
            data={"key": "value"},
            timestamp=now,
        )

        assert event.id == "1234567890-0"
        assert event.stream == "test:stream"
        assert event.data == {"key": "value"}
        assert event.timestamp == now

    def test_event_default_timestamp(self):
        """Test that Event gets a default timestamp."""
        event = Event(id="1-0", stream="s", data={})
        assert event.timestamp is not None
        assert event.timestamp.tzinfo == UTC

    def test_event_is_frozen(self):
        """Test that Event is immutable."""
        event = Event(id="1-0", stream="s", data={})
        with pytest.raises(AttributeError):
            event.id = "2-0"  # type: ignore[misc]


@pytest.mark.unit
class TestParseTimestampFromId:
    """Tests for the _parse_timestamp_from_id helper."""

    def test_parse_valid_id(self):
        """Test parsing a valid Redis Stream message ID."""
        # 1700000000000 ms = 2023-11-14T22:13:20Z
        result = _parse_timestamp_from_id("1700000000000-0")
        assert result.year == 2023
        assert result.month == 11
        assert result.tzinfo == UTC

    def test_parse_id_with_sequence(self):
        """Test parsing an ID with a non-zero sequence number."""
        result = _parse_timestamp_from_id("1700000000000-5")
        assert result.year == 2023

    def test_parse_invalid_id_returns_now(self):
        """Test that an invalid ID returns current time."""
        before = datetime.now(UTC)
        result = _parse_timestamp_from_id("invalid-id")
        after = datetime.now(UTC)
        assert before <= result <= after

    def test_parse_empty_string(self):
        """Test that an empty string returns current time."""
        result = _parse_timestamp_from_id("")
        assert result.tzinfo == UTC


@pytest.mark.unit
class TestRedisStreamManagerInit:
    """Tests for RedisStreamManager initialization."""

    def test_default_config(self):
        """Test initialization with default config."""
        manager = RedisStreamManager()
        assert manager.is_connected is False
        assert manager.config.redis_url == "redis://localhost:6379/0"

    def test_custom_config(self):
        """Test initialization with custom config."""
        config = EventConfig(
            redis_url="redis://custom:6380/1",
            stream_prefix="myapp",
        )
        manager = RedisStreamManager(config)
        assert manager.config.redis_url == "redis://custom:6380/1"
        assert manager.config.stream_prefix == "myapp"

    def test_repr_disconnected(self):
        """Test string representation when disconnected."""
        manager = RedisStreamManager()
        result = repr(manager)
        assert "connected=False" in result
        assert "redis://localhost:6379/0" in result


@pytest.mark.unit
class TestRedisStreamManagerConnect:
    """Tests for connect/disconnect lifecycle."""

    @patch("file_organizer.events.stream.redis")
    def test_connect_success(self, mock_redis_module: MagicMock):
        """Test successful Redis connection."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        result = manager.connect()

        assert result is True
        assert manager.is_connected is True
        mock_redis_module.Redis.from_url.assert_called_once()

    @patch("file_organizer.events.stream.redis")
    def test_connect_with_custom_url(self, mock_redis_module: MagicMock):
        """Test connection with a custom URL override."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        result = manager.connect("redis://other:6380/2")

        assert result is True
        mock_redis_module.Redis.from_url.assert_called_once_with(
            "redis://other:6380/2", decode_responses=True, socket_timeout=5
        )

    @patch("file_organizer.events.stream.redis")
    def test_connect_failure(self, mock_redis_module: MagicMock):
        """Test graceful handling of connection failure."""
        mock_redis_module.Redis.from_url.side_effect = ConnectionError("refused")

        manager = RedisStreamManager()
        result = manager.connect()

        assert result is False
        assert manager.is_connected is False

    @patch("file_organizer.events.stream.redis")
    def test_disconnect(self, mock_redis_module: MagicMock):
        """Test disconnection cleans up state."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()
        assert manager.is_connected is True

        manager.disconnect()
        assert manager.is_connected is False
        mock_client.close.assert_called_once()

    def test_disconnect_when_not_connected(self):
        """Test disconnect is safe when not connected."""
        manager = RedisStreamManager()
        manager.disconnect()  # Should not raise
        assert manager.is_connected is False

    @patch("file_organizer.events.stream.redis")
    def test_disconnect_handles_close_error(self, mock_redis_module: MagicMock):
        """Test disconnect handles errors during close."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.close.side_effect = RuntimeError("close failed")
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()
        manager.disconnect()  # Should not raise

        assert manager.is_connected is False


@pytest.mark.unit
class TestRedisStreamManagerPublish:
    """Tests for publishing events to streams."""

    def _create_connected_manager(
        self, mock_redis_module: MagicMock
    ) -> tuple[RedisStreamManager, MagicMock]:
        """Helper: create a connected manager with mocked Redis."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()
        return manager, mock_client

    @patch("file_organizer.events.stream.redis")
    def test_publish_success(self, mock_redis_module: MagicMock):
        """Test successful event publishing."""
        manager, mock_client = self._create_connected_manager(mock_redis_module)
        mock_client.xadd.return_value = "1700000000000-0"

        result = manager.publish("events", {"key": "value"})

        assert result == "1700000000000-0"
        mock_client.xadd.assert_called_once()

    @patch("file_organizer.events.stream.redis")
    def test_publish_uses_prefixed_stream_name(self, mock_redis_module: MagicMock):
        """Test that stream names are prefixed."""
        manager, mock_client = self._create_connected_manager(mock_redis_module)
        mock_client.xadd.return_value = "1-0"

        manager.publish("events", {"key": "value"})

        call_kwargs = mock_client.xadd.call_args
        assert call_kwargs.kwargs["name"] == "fileorg:events"

    @patch("file_organizer.events.stream.redis")
    def test_publish_with_max_len(self, mock_redis_module: MagicMock):
        """Test publishing with explicit max length."""
        manager, mock_client = self._create_connected_manager(mock_redis_module)
        mock_client.xadd.return_value = "1-0"

        manager.publish("events", {"key": "value"}, max_len=500)

        call_kwargs = mock_client.xadd.call_args
        assert call_kwargs.kwargs["maxlen"] == 500
        assert call_kwargs.kwargs["approximate"] is True

    @patch("file_organizer.events.stream.redis")
    def test_publish_with_default_max_len(self, mock_redis_module: MagicMock):
        """Test publishing uses config max_stream_length."""
        config = EventConfig(max_stream_length=5000)
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager(config)
        manager.connect()
        mock_client.xadd.return_value = "1-0"

        manager.publish("events", {"key": "value"})

        call_kwargs = mock_client.xadd.call_args
        assert call_kwargs.kwargs["maxlen"] == 5000

    @patch("file_organizer.events.stream.redis")
    def test_publish_no_max_len_when_none(self, mock_redis_module: MagicMock):
        """Test publishing without trimming when max_stream_length is None."""
        config = EventConfig(max_stream_length=None)
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager(config)
        manager.connect()
        mock_client.xadd.return_value = "1-0"

        manager.publish("events", {"key": "value"})

        call_kwargs = mock_client.xadd.call_args
        assert "maxlen" not in call_kwargs.kwargs

    def test_publish_when_disconnected(self):
        """Test that publish returns None when not connected."""
        manager = RedisStreamManager()
        result = manager.publish("events", {"key": "value"})
        assert result is None

    @patch("file_organizer.events.stream.redis")
    def test_publish_handles_redis_error(self, mock_redis_module: MagicMock):
        """Test publish handles Redis errors gracefully."""
        manager, mock_client = self._create_connected_manager(mock_redis_module)
        mock_client.xadd.side_effect = RuntimeError("write error")

        result = manager.publish("events", {"key": "value"})
        assert result is None


@pytest.mark.unit
class TestRedisStreamManagerConsumerGroup:
    """Tests for consumer group operations."""

    @patch("file_organizer.events.stream.redis")
    def test_create_consumer_group_success(self, mock_redis_module: MagicMock):
        """Test creating a consumer group."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        result = manager.create_consumer_group("events")

        assert result is True
        mock_client.xgroup_create.assert_called_once_with(
            name="fileorg:events",
            groupname="file-organizer",
            id="0",
            mkstream=True,
        )

    @patch("file_organizer.events.stream.redis")
    def test_create_consumer_group_custom_name(self, mock_redis_module: MagicMock):
        """Test creating a group with a custom name."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        result = manager.create_consumer_group("events", "my-group", "$")

        assert result is True
        mock_client.xgroup_create.assert_called_once_with(
            name="fileorg:events",
            groupname="my-group",
            id="$",
            mkstream=True,
        )

    @patch("file_organizer.events.stream.redis")
    def test_create_consumer_group_already_exists(self, mock_redis_module: MagicMock):
        """Test that existing groups are handled silently."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xgroup_create.side_effect = Exception(
            "BUSYGROUP Consumer Group name already exists"
        )
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        result = manager.create_consumer_group("events")
        assert result is True

    @patch("file_organizer.events.stream.redis")
    def test_create_consumer_group_error(self, mock_redis_module: MagicMock):
        """Test that other errors return False."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xgroup_create.side_effect = Exception("some other error")
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        result = manager.create_consumer_group("events")
        assert result is False

    def test_create_consumer_group_when_disconnected(self):
        """Test creating group when not connected returns False."""
        manager = RedisStreamManager()
        result = manager.create_consumer_group("events")
        assert result is False


@pytest.mark.unit
class TestRedisStreamManagerReadGroup:
    """Tests for reading from consumer groups."""

    @patch("file_organizer.events.stream.redis")
    def test_read_group_returns_events(self, mock_redis_module: MagicMock):
        """Test reading messages from a consumer group."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xreadgroup.return_value = [
            (
                "fileorg:events",
                [
                    ("1700000000000-0", {"event_type": "file.created", "file_path": "/a.txt"}),
                    ("1700000000001-0", {"event_type": "file.modified", "file_path": "/b.txt"}),
                ],
            )
        ]
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        events = manager.read_group("events", consumer_name="w1")

        assert len(events) == 2
        assert events[0].id == "1700000000000-0"
        assert events[0].data["file_path"] == "/a.txt"
        assert events[1].id == "1700000000001-0"

    @patch("file_organizer.events.stream.redis")
    def test_read_group_empty_results(self, mock_redis_module: MagicMock):
        """Test reading when no messages available."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xreadgroup.return_value = []
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        events = manager.read_group("events")
        assert events == []

    @patch("file_organizer.events.stream.redis")
    def test_read_group_none_results(self, mock_redis_module: MagicMock):
        """Test reading when Redis returns None."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xreadgroup.return_value = None
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        events = manager.read_group("events")
        assert events == []

    def test_read_group_when_disconnected(self):
        """Test reading when not connected returns empty list."""
        manager = RedisStreamManager()
        events = manager.read_group("events")
        assert events == []

    @patch("file_organizer.events.stream.redis")
    def test_read_group_handles_error(self, mock_redis_module: MagicMock):
        """Test reading handles Redis errors gracefully."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xreadgroup.side_effect = RuntimeError("read error")
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        events = manager.read_group("events")
        assert events == []

    @patch("file_organizer.events.stream.redis")
    def test_read_group_with_custom_params(self, mock_redis_module: MagicMock):
        """Test reading with custom count and block parameters."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xreadgroup.return_value = []
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        manager.read_group("events", count=5, block_ms=1000)

        mock_client.xreadgroup.assert_called_once_with(
            groupname="file-organizer",
            consumername="worker-1",
            streams={"fileorg:events": ">"},
            count=5,
            block=1000,
        )


@pytest.mark.unit
class TestRedisStreamManagerAcknowledge:
    """Tests for acknowledging messages."""

    @patch("file_organizer.events.stream.redis")
    def test_acknowledge_success(self, mock_redis_module: MagicMock):
        """Test successful acknowledgment."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xack.return_value = 1
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        result = manager.acknowledge("events", message_id="1-0")
        assert result is True

    @patch("file_organizer.events.stream.redis")
    def test_acknowledge_not_found(self, mock_redis_module: MagicMock):
        """Test acknowledging a non-existent message."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xack.return_value = 0
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        result = manager.acknowledge("events", message_id="nonexistent")
        assert result is False

    def test_acknowledge_when_disconnected(self):
        """Test acknowledge when not connected returns False."""
        manager = RedisStreamManager()
        result = manager.acknowledge("events", message_id="1-0")
        assert result is False

    @patch("file_organizer.events.stream.redis")
    def test_acknowledge_handles_error(self, mock_redis_module: MagicMock):
        """Test acknowledge handles errors gracefully."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xack.side_effect = RuntimeError("ack error")
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        result = manager.acknowledge("events", message_id="1-0")
        assert result is False


@pytest.mark.unit
class TestRedisStreamManagerStreamInfo:
    """Tests for stream information queries."""

    @patch("file_organizer.events.stream.redis")
    def test_get_stream_length(self, mock_redis_module: MagicMock):
        """Test getting stream length."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xlen.return_value = 42
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        assert manager.get_stream_length("events") == 42

    def test_get_stream_length_when_disconnected(self):
        """Test stream length returns 0 when not connected."""
        manager = RedisStreamManager()
        assert manager.get_stream_length("events") == 0

    @patch("file_organizer.events.stream.redis")
    def test_get_pending_count(self, mock_redis_module: MagicMock):
        """Test getting pending message count."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xpending.return_value = {"pending": 5}
        mock_redis_module.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        assert manager.get_pending_count("events") == 5

    def test_get_pending_count_when_disconnected(self):
        """Test pending count returns 0 when not connected."""
        manager = RedisStreamManager()
        assert manager.get_pending_count("events") == 0


@pytest.mark.unit
class TestRedisStreamManagerContextManager:
    """Tests for context manager protocol."""

    @patch("file_organizer.events.stream.redis")
    def test_context_manager(self, mock_redis_module: MagicMock):
        """Test using the manager as a context manager."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        with RedisStreamManager() as manager:
            assert manager.is_connected is True

        assert manager.is_connected is False

    @patch("file_organizer.events.stream.redis")
    def test_context_manager_disconnects_on_error(self, mock_redis_module: MagicMock):
        """Test context manager cleans up on exception."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_module.Redis.from_url.return_value = mock_client

        with pytest.raises(ValueError, match="test error"):
            with RedisStreamManager() as manager:
                assert manager.is_connected is True
                raise ValueError("test error")

        assert manager.is_connected is False
