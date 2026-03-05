"""Coverage tests for RedisStreamManager — targets uncovered branches."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from file_organizer.events.config import EventConfig
from file_organizer.events.stream import (
    Event,
    RedisStreamManager,
    _parse_timestamp_from_id,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def config():
    return EventConfig()


@pytest.fixture()
def manager(config):
    return RedisStreamManager(config=config)


# ---------------------------------------------------------------------------
# Event dataclass
# ---------------------------------------------------------------------------


class TestEvent:
    def test_create_event(self):
        e = Event(id="123-0", stream="test", data={"key": "val"})
        assert e.id == "123-0"
        assert e.data["key"] == "val"


# ---------------------------------------------------------------------------
# RedisStreamManager — no redis installed
# ---------------------------------------------------------------------------


class TestNoRedis:
    def test_connect_no_redis(self, manager):
        with patch("file_organizer.events.stream.redis", None):
            result = manager.connect()
        assert result is False

    def test_publish_not_connected(self, manager):
        result = manager.publish("test", {"k": "v"})
        assert result is None

    def test_read_group_not_connected(self, manager):
        result = manager.read_group("test")
        assert result == []

    def test_acknowledge_not_connected(self, manager):
        result = manager.acknowledge("test", message_id="123-0")
        assert result is False

    def test_get_stream_length_not_connected(self, manager):
        assert manager.get_stream_length("test") == 0

    def test_get_pending_count_not_connected(self, manager):
        assert manager.get_pending_count("test") == 0

    def test_create_consumer_group_not_connected(self, manager):
        result = manager.create_consumer_group("test")
        assert result is False


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestProperties:
    def test_is_connected_default(self, manager):
        assert manager.is_connected is False

    def test_config_property(self, manager, config):
        assert manager.config is config

    def test_repr(self, manager):
        r = repr(manager)
        assert "RedisStreamManager" in r
        assert "connected=False" in r


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_enter_exit(self, config):
        with patch("file_organizer.events.stream.redis", None):
            with RedisStreamManager(config=config) as mgr:
                assert mgr.is_connected is False


# ---------------------------------------------------------------------------
# disconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    def test_disconnect_when_no_connection(self, manager):
        manager.disconnect()  # Should not raise

    def test_disconnect_with_mock_redis(self, manager):
        mock_redis = MagicMock()
        manager._redis = mock_redis
        manager._connected = True
        manager.disconnect()
        assert manager._redis is None
        assert manager._connected is False
        mock_redis.close.assert_called_once()

    def test_disconnect_close_error(self, manager):
        mock_redis = MagicMock()
        mock_redis.close.side_effect = Exception("close error")
        manager._redis = mock_redis
        manager._connected = True
        manager.disconnect()
        assert manager._redis is None
        assert manager._connected is False


# ---------------------------------------------------------------------------
# connect with mock redis
# ---------------------------------------------------------------------------


class TestConnect:
    def test_connect_success(self, manager):
        mock_redis_mod = MagicMock()
        mock_conn = MagicMock()
        mock_redis_mod.Redis.from_url.return_value = mock_conn
        with patch("file_organizer.events.stream.redis", mock_redis_mod):
            result = manager.connect()
        assert result is True
        assert manager.is_connected is True

    def test_connect_failure(self, manager):
        mock_redis_mod = MagicMock()
        mock_redis_mod.Redis.from_url.side_effect = Exception("refused")
        with patch("file_organizer.events.stream.redis", mock_redis_mod):
            result = manager.connect()
        assert result is False
        assert manager.is_connected is False

    def test_connect_custom_url(self, manager):
        mock_redis_mod = MagicMock()
        mock_conn = MagicMock()
        mock_redis_mod.Redis.from_url.return_value = mock_conn
        with patch("file_organizer.events.stream.redis", mock_redis_mod):
            result = manager.connect(redis_url="redis://custom:6380")
        assert result is True


# ---------------------------------------------------------------------------
# publish with mock connection
# ---------------------------------------------------------------------------


class TestPublish:
    def test_publish_success(self, manager):
        mock_redis = MagicMock()
        mock_redis.xadd.return_value = "123-0"
        manager._redis = mock_redis
        manager._connected = True
        result = manager.publish("events", {"key": "val"})
        assert result == "123-0"

    def test_publish_with_max_len(self, manager):
        mock_redis = MagicMock()
        mock_redis.xadd.return_value = "123-0"
        manager._redis = mock_redis
        manager._connected = True
        result = manager.publish("events", {"key": "val"}, max_len=100)
        assert result == "123-0"

    def test_publish_exception(self, manager):
        mock_redis = MagicMock()
        mock_redis.xadd.side_effect = Exception("fail")
        manager._redis = mock_redis
        manager._connected = True
        result = manager.publish("events", {"key": "val"})
        assert result is None


# ---------------------------------------------------------------------------
# create_consumer_group with mock
# ---------------------------------------------------------------------------


class TestCreateConsumerGroup:
    def test_create_success(self, manager):
        mock_redis = MagicMock()
        manager._redis = mock_redis
        manager._connected = True
        result = manager.create_consumer_group("stream")
        assert result is True

    def test_already_exists(self, manager):
        mock_redis = MagicMock()
        mock_redis.xgroup_create.side_effect = Exception("BUSYGROUP already exists")
        manager._redis = mock_redis
        manager._connected = True
        result = manager.create_consumer_group("stream")
        assert result is True

    def test_other_error(self, manager):
        mock_redis = MagicMock()
        mock_redis.xgroup_create.side_effect = Exception("other error")
        manager._redis = mock_redis
        manager._connected = True
        result = manager.create_consumer_group("stream")
        assert result is False


# ---------------------------------------------------------------------------
# read_group with mock
# ---------------------------------------------------------------------------


class TestReadGroup:
    def test_read_returns_events(self, manager):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = [("stream", [("1000000000000-0", {"k": "v"})])]
        manager._redis = mock_redis
        manager._connected = True
        events = manager.read_group("test")
        assert len(events) == 1
        assert events[0].data == {"k": "v"}

    def test_read_empty(self, manager):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = None
        manager._redis = mock_redis
        manager._connected = True
        events = manager.read_group("test")
        assert events == []

    def test_read_exception(self, manager):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.side_effect = Exception("fail")
        manager._redis = mock_redis
        manager._connected = True
        events = manager.read_group("test")
        assert events == []


# ---------------------------------------------------------------------------
# acknowledge with mock
# ---------------------------------------------------------------------------


class TestAcknowledge:
    def test_ack_success(self, manager):
        mock_redis = MagicMock()
        mock_redis.xack.return_value = 1
        manager._redis = mock_redis
        manager._connected = True
        assert manager.acknowledge("test", message_id="123-0") is True

    def test_ack_not_found(self, manager):
        mock_redis = MagicMock()
        mock_redis.xack.return_value = 0
        manager._redis = mock_redis
        manager._connected = True
        assert manager.acknowledge("test", message_id="999-0") is False

    def test_ack_error(self, manager):
        mock_redis = MagicMock()
        mock_redis.xack.side_effect = Exception("fail")
        manager._redis = mock_redis
        manager._connected = True
        assert manager.acknowledge("test", message_id="123-0") is False


# ---------------------------------------------------------------------------
# get_stream_length / get_pending_count
# ---------------------------------------------------------------------------


class TestStreamInfo:
    def test_stream_length(self, manager):
        mock_redis = MagicMock()
        mock_redis.xlen.return_value = 42
        manager._redis = mock_redis
        manager._connected = True
        assert manager.get_stream_length("test") == 42

    def test_stream_length_error(self, manager):
        mock_redis = MagicMock()
        mock_redis.xlen.side_effect = Exception("fail")
        manager._redis = mock_redis
        manager._connected = True
        assert manager.get_stream_length("test") == 0

    def test_pending_count(self, manager):
        mock_redis = MagicMock()
        mock_redis.xpending.return_value = {"pending": 5}
        manager._redis = mock_redis
        manager._connected = True
        assert manager.get_pending_count("test") == 5

    def test_pending_count_none(self, manager):
        mock_redis = MagicMock()
        mock_redis.xpending.return_value = None
        manager._redis = mock_redis
        manager._connected = True
        assert manager.get_pending_count("test") == 0

    def test_pending_count_error(self, manager):
        mock_redis = MagicMock()
        mock_redis.xpending.side_effect = Exception("fail")
        manager._redis = mock_redis
        manager._connected = True
        assert manager.get_pending_count("test") == 0


# ---------------------------------------------------------------------------
# _parse_timestamp_from_id
# ---------------------------------------------------------------------------


class TestParseTimestamp:
    def test_valid_id(self):
        ts = _parse_timestamp_from_id("1700000000000-0")
        assert ts.year >= 2023

    def test_invalid_id(self):
        ts = _parse_timestamp_from_id("not-a-valid-id")
        assert ts is not None  # Falls back to now()

    def test_empty_id(self):
        ts = _parse_timestamp_from_id("")
        assert ts is not None
