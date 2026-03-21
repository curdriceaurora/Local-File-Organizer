"""Integration tests targeting uncovered branches in stream.py.

Targets: subscribe() async generator, error paths in get_stream_length /
get_pending_count, RedisConnectionError, xreadgroup param verification,
and publish with no-maxlen config branch.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.events.config import EventConfig
from file_organizer.events.stream import (
    Event,
    RedisConnectionError,
    RedisStreamManager,
    _parse_timestamp_from_id,
)

# ---------------------------------------------------------------------------
# RedisConnectionError
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRedisConnectionError:
    """RedisConnectionError is a real exception class that can be raised/caught."""

    def test_is_exception_subclass(self):
        assert issubclass(RedisConnectionError, Exception)

    def test_can_raise_and_catch(self):
        with pytest.raises(RedisConnectionError, match="no connection"):
            raise RedisConnectionError("no connection")

    def test_message_preserved(self):
        exc = RedisConnectionError("custom message")
        assert str(exc) == "custom message"

    def test_not_caught_by_value_error(self):
        with pytest.raises(RedisConnectionError):
            try:
                raise RedisConnectionError("oops")
            except ValueError:
                pass


# ---------------------------------------------------------------------------
# _parse_timestamp_from_id — branch: non-numeric ms part
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestParseTimestampFromIdBranches:
    """Covers the fallback branch in _parse_timestamp_from_id."""

    def test_non_numeric_ms_part_falls_back_to_now(self):
        from datetime import UTC, datetime

        before = datetime.now(UTC)
        result = _parse_timestamp_from_id("not_a_number-0")
        after = datetime.now(UTC)
        assert result.tzinfo == UTC
        assert before <= result <= after

    def test_missing_dash_falls_back_to_now(self):
        from datetime import UTC, datetime

        before = datetime.now(UTC)
        result = _parse_timestamp_from_id("nodash")
        after = datetime.now(UTC)
        assert before <= result <= after

    def test_known_epoch_ms_parsed_correctly(self):
        from datetime import UTC

        result = _parse_timestamp_from_id("1000000000000-0")
        assert result.year == 2001
        assert result.tzinfo == UTC


# ---------------------------------------------------------------------------
# connect — verify exact call args
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestConnectExactArgs:
    """Verifies connect() calls Redis.from_url with correct keyword args."""

    @patch("file_organizer.events.stream.redis")
    def test_connect_uses_configured_url(self, mock_redis_mod: MagicMock):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager(EventConfig(redis_url="redis://myhost:1234/3"))
        result = manager.connect()

        assert result is True
        mock_redis_mod.Redis.from_url.assert_called_once_with(
            "redis://myhost:1234/3",
            decode_responses=True,
            socket_timeout=5,
        )

    @patch("file_organizer.events.stream.redis")
    def test_connect_override_url_used_not_config_url(self, mock_redis_mod: MagicMock):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager(EventConfig(redis_url="redis://default:6379/0"))
        result = manager.connect("redis://override:9999/5")

        assert result is True
        mock_redis_mod.Redis.from_url.assert_called_once_with(
            "redis://override:9999/5",
            decode_responses=True,
            socket_timeout=5,
        )

    @patch("file_organizer.events.stream.redis")
    def test_connect_sets_is_connected_true_on_success(self, mock_redis_mod: MagicMock):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        assert manager.is_connected is False
        manager.connect()
        assert manager.is_connected is True

    @patch("file_organizer.events.stream.redis")
    def test_connect_failure_clears_redis_attribute(self, mock_redis_mod: MagicMock):
        mock_redis_mod.Redis.from_url.side_effect = RuntimeError("refused")
        manager = RedisStreamManager()
        manager.connect()
        assert manager._redis is None
        assert manager.is_connected is False


# ---------------------------------------------------------------------------
# publish — branch: no maxlen when config has None
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPublishNoMaxlenBranch:
    """Covers the branch where max_stream_length is None — no maxlen kwarg added."""

    @patch("file_organizer.events.stream.redis")
    def test_publish_no_maxlen_kwarg_when_config_none(self, mock_redis_mod: MagicMock):
        config = EventConfig(max_stream_length=None)
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xadd.return_value = "9999-0"
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager(config)
        manager.connect()
        result = manager.publish("events", {"k": "v"})

        assert result == "9999-0"
        call_kwargs = mock_client.xadd.call_args.kwargs
        assert "maxlen" not in call_kwargs
        assert "approximate" not in call_kwargs

    @patch("file_organizer.events.stream.redis")
    def test_publish_with_explicit_max_len_overrides_none_config(self, mock_redis_mod: MagicMock):
        config = EventConfig(max_stream_length=None)
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xadd.return_value = "1-0"
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager(config)
        manager.connect()
        result = manager.publish("events", {"k": "v"}, max_len=250)

        assert result == "1-0"
        call_kwargs = mock_client.xadd.call_args.kwargs
        assert call_kwargs["maxlen"] == 250
        assert call_kwargs["approximate"] is True

    @patch("file_organizer.events.stream.redis")
    def test_publish_stream_name_prefixed_exactly(self, mock_redis_mod: MagicMock):
        config = EventConfig(stream_prefix="myns", max_stream_length=None)
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_client.xadd.return_value = "2-0"
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager(config)
        manager.connect()
        manager.publish("updates", {"x": "y"})

        call_kwargs = mock_client.xadd.call_args.kwargs
        assert call_kwargs["name"] == "myns:updates"
        assert call_kwargs["fields"] == {"x": "y"}


# ---------------------------------------------------------------------------
# get_stream_length — error branch
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetStreamLengthErrorBranch:
    """Covers the except branch in get_stream_length."""

    def test_xlen_exception_returns_zero(self):
        mock_redis = MagicMock()
        mock_redis.xlen.side_effect = RuntimeError("stream gone")
        manager = RedisStreamManager()
        manager._redis = mock_redis
        manager._connected = True

        result = manager.get_stream_length("events")
        assert result == 0

    def test_xlen_uses_prefixed_name(self):
        config = EventConfig(stream_prefix="pfx")
        mock_redis = MagicMock()
        mock_redis.xlen.return_value = 7
        manager = RedisStreamManager(config)
        manager._redis = mock_redis
        manager._connected = True

        result = manager.get_stream_length("mystream")
        assert result == 7
        mock_redis.xlen.assert_called_once_with("pfx:mystream")


# ---------------------------------------------------------------------------
# get_pending_count — None info branch and error branch
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetPendingCountBranches:
    """Covers None-info and exception branches in get_pending_count."""

    def test_xpending_returns_none_gives_zero(self):
        mock_redis = MagicMock()
        mock_redis.xpending.return_value = None
        manager = RedisStreamManager()
        manager._redis = mock_redis
        manager._connected = True

        result = manager.get_pending_count("stream")
        assert result == 0

    def test_xpending_empty_dict_gives_zero(self):
        mock_redis = MagicMock()
        mock_redis.xpending.return_value = {}
        manager = RedisStreamManager()
        manager._redis = mock_redis
        manager._connected = True

        result = manager.get_pending_count("stream")
        assert result == 0

    def test_xpending_exception_gives_zero(self):
        mock_redis = MagicMock()
        mock_redis.xpending.side_effect = RuntimeError("server gone")
        manager = RedisStreamManager()
        manager._redis = mock_redis
        manager._connected = True

        result = manager.get_pending_count("stream")
        assert result == 0

    def test_xpending_uses_custom_group_name(self):
        config = EventConfig(consumer_group="default-group")
        mock_redis = MagicMock()
        mock_redis.xpending.return_value = {"pending": 3}
        manager = RedisStreamManager(config)
        manager._redis = mock_redis
        manager._connected = True

        result = manager.get_pending_count("stream", group_name="my-group")
        assert result == 3
        mock_redis.xpending.assert_called_once_with("fileorg:stream", "my-group")


# ---------------------------------------------------------------------------
# read_group — verify exact xreadgroup call args
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReadGroupExactArgs:
    """Verifies that xreadgroup is called with the correct argument structure."""

    def test_read_group_default_params_sent_to_xreadgroup(self):
        config = EventConfig(
            consumer_group="mygroup",
            batch_size=15,
            block_ms=2000,
        )
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = []
        manager = RedisStreamManager(config)
        manager._redis = mock_redis
        manager._connected = True

        manager.read_group("events")

        mock_redis.xreadgroup.assert_called_once_with(
            groupname="mygroup",
            consumername="worker-1",
            streams={"fileorg:events": ">"},
            count=15,
            block=2000,
        )

    def test_read_group_custom_consumer_name_forwarded(self):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = []
        manager = RedisStreamManager()
        manager._redis = mock_redis
        manager._connected = True

        manager.read_group("events", consumer_name="consumer-99")

        call_kwargs = mock_redis.xreadgroup.call_args.kwargs
        assert call_kwargs["consumername"] == "consumer-99"

    def test_read_group_with_block_ms_zero_non_blocking(self):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = []
        manager = RedisStreamManager()
        manager._redis = mock_redis
        manager._connected = True

        manager.read_group("events", block_ms=0)

        call_kwargs = mock_redis.xreadgroup.call_args.kwargs
        assert call_kwargs["block"] == 0

    def test_read_group_event_timestamp_parsed_from_id(self):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = [
            ("fileorg:events", [("1700000000000-0", {"event_type": "file.created"})])
        ]
        manager = RedisStreamManager()
        manager._redis = mock_redis
        manager._connected = True

        events = manager.read_group("events")

        assert len(events) == 1
        assert events[0].timestamp.year == 2023
        assert events[0].stream == "fileorg:events"

    def test_read_group_multiple_messages_all_returned(self):
        mock_redis = MagicMock()
        mock_redis.xreadgroup.return_value = [
            (
                "fileorg:stream",
                [
                    ("1-0", {"a": "1"}),
                    ("2-0", {"b": "2"}),
                    ("3-0", {"c": "3"}),
                ],
            )
        ]
        manager = RedisStreamManager()
        manager._redis = mock_redis
        manager._connected = True

        events = manager.read_group("stream")

        assert len(events) == 3
        assert events[0].id == "1-0"
        assert events[0].data == {"a": "1"}
        assert events[2].id == "3-0"
        assert events[2].data == {"c": "3"}


# ---------------------------------------------------------------------------
# acknowledge — custom group name
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestAcknowledgeExactArgs:
    """Verifies xack receives prefixed stream name and correct group."""

    def test_acknowledge_uses_default_group(self):
        config = EventConfig(consumer_group="mygroup")
        mock_redis = MagicMock()
        mock_redis.xack.return_value = 1
        manager = RedisStreamManager(config)
        manager._redis = mock_redis
        manager._connected = True

        result = manager.acknowledge("events", message_id="5-0")
        assert result is True
        mock_redis.xack.assert_called_once_with("fileorg:events", "mygroup", "5-0")

    def test_acknowledge_custom_group_overrides_config(self):
        config = EventConfig(consumer_group="default-grp")
        mock_redis = MagicMock()
        mock_redis.xack.return_value = 1
        manager = RedisStreamManager(config)
        manager._redis = mock_redis
        manager._connected = True

        result = manager.acknowledge("events", group_name="override-grp", message_id="7-0")
        assert result is True
        mock_redis.xack.assert_called_once_with("fileorg:events", "override-grp", "7-0")

    def test_acknowledge_returns_false_when_ack_count_is_zero(self):
        mock_redis = MagicMock()
        mock_redis.xack.return_value = 0
        manager = RedisStreamManager()
        manager._redis = mock_redis
        manager._connected = True

        result = manager.acknowledge("events", message_id="999-0")
        assert result is False


# ---------------------------------------------------------------------------
# subscribe — async generator
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestSubscribeAsyncGenerator:
    """Tests for the subscribe() async generator covering disconnected and
    connected-then-drained branches."""

    def test_subscribe_yields_nothing_when_disconnected(self):
        manager = RedisStreamManager()
        assert manager.is_connected is False

        async def collect():
            results = []
            async for event in manager.subscribe("events"):
                results.append(event)
            return results

        events = asyncio.get_event_loop().run_until_complete(collect())
        assert events == []

    @patch("file_organizer.events.stream.redis")
    def test_subscribe_yields_events_then_stops(self, mock_redis_mod: MagicMock):
        """subscribe() yields events from read_group until disconnected.

        We simulate: first read_group call returns one event, then we flip
        _connected=False to break the loop.
        """
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager(EventConfig(block_ms=100))
        manager.connect()

        seen: list[Event] = []

        read_calls = 0

        def fake_xreadgroup(**kwargs):
            nonlocal read_calls
            read_calls += 1
            if read_calls == 1:
                return [("fileorg:events", [("1700000000000-0", {"event_type": "file.created"})])]
            manager._connected = False
            return []

        mock_client.xreadgroup.side_effect = fake_xreadgroup
        mock_client.xgroup_create.return_value = True

        async def run():
            async for event in manager.subscribe("events"):
                seen.append(event)

        asyncio.get_event_loop().run_until_complete(run())

        assert len(seen) == 1
        assert seen[0].id == "1700000000000-0"
        assert seen[0].data == {"event_type": "file.created"}

    @patch("file_organizer.events.stream.redis")
    def test_subscribe_calls_create_consumer_group_before_reading(self, mock_redis_mod: MagicMock):
        """subscribe() must call create_consumer_group before starting the read loop."""
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        call_order: list[str] = []

        def fake_xgroup_create(**kwargs):
            call_order.append("group_create")
            return True

        def fake_xreadgroup(**kwargs):
            call_order.append("xreadgroup")
            manager._connected = False
            return []

        mock_client.xgroup_create.side_effect = fake_xgroup_create
        mock_client.xreadgroup.side_effect = fake_xreadgroup

        async def run():
            async for _ in manager.subscribe("events"):
                pass

        asyncio.get_event_loop().run_until_complete(run())

        assert call_order[0] == "group_create"
        assert "xreadgroup" in call_order

    @patch("file_organizer.events.stream.redis")
    def test_subscribe_with_custom_consumer_name(self, mock_redis_mod: MagicMock):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()

        def fake_xreadgroup(**kwargs):
            manager._connected = False
            return []

        mock_client.xreadgroup.side_effect = fake_xreadgroup
        mock_client.xgroup_create.return_value = True

        async def run():
            async for _ in manager.subscribe("events", consumer_name="custom-worker"):
                pass

        asyncio.get_event_loop().run_until_complete(run())

        call_kwargs = mock_client.xreadgroup.call_args.kwargs
        assert call_kwargs["consumername"] == "custom-worker"


# ---------------------------------------------------------------------------
# repr — connected state
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReprConnectedState:
    """repr() reflects connected state accurately."""

    @patch("file_organizer.events.stream.redis")
    def test_repr_shows_connected_true_when_connected(self, mock_redis_mod: MagicMock):
        mock_client = MagicMock()
        mock_client.ping.return_value = True
        mock_redis_mod.Redis.from_url.return_value = mock_client

        manager = RedisStreamManager()
        manager.connect()
        result = repr(manager)
        assert "connected=True" in result
        assert "redis://localhost:6379/0" in result

    def test_repr_shows_connected_false_when_disconnected(self):
        manager = RedisStreamManager()
        result = repr(manager)
        assert "connected=False" in result
