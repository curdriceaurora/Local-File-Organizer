"""
Unit tests for EventMonitor.

Tests stream statistics, consumer lag, and event rate calculation.
All tests mock Redis to avoid requiring a running instance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.events.monitor import (
    ConsumerLag,
    EventMonitor,
    StreamStats,
    _parse_entry_timestamp,
)
from file_organizer.events.stream import RedisStreamManager

# --- Fixtures ---


@pytest.fixture
def mock_redis_client() -> MagicMock:
    """Create a mock Redis client."""
    client = MagicMock()
    client.ping.return_value = True
    return client


@pytest.fixture
def connected_manager(mock_redis_client: MagicMock) -> RedisStreamManager:
    """Create a connected RedisStreamManager with mocked Redis."""
    with patch("file_organizer.events.stream.redis") as mock_redis_module:
        mock_redis_module.Redis.from_url.return_value = mock_redis_client
        manager = RedisStreamManager()
        manager.connect()
        yield manager


@pytest.fixture
def monitor(connected_manager: RedisStreamManager) -> EventMonitor:
    """Create an EventMonitor with a connected stream manager."""
    return EventMonitor(connected_manager)


# --- Dataclass Tests ---


class TestStreamStats:
    """Tests for the StreamStats dataclass."""

    def test_default_values(self):
        """Test StreamStats has sensible defaults."""
        stats = StreamStats()
        assert stats.length == 0
        assert stats.groups == 0
        assert stats.oldest_event is None
        assert stats.newest_event is None

    def test_custom_values(self):
        """Test StreamStats accepts custom values."""
        now = datetime.now(UTC)
        stats = StreamStats(
            length=42,
            groups=3,
            oldest_event=now,
            newest_event=now,
        )
        assert stats.length == 42
        assert stats.groups == 3
        assert stats.oldest_event == now


class TestConsumerLag:
    """Tests for the ConsumerLag dataclass."""

    def test_default_values(self):
        """Test ConsumerLag has sensible defaults."""
        lag = ConsumerLag()
        assert lag.pending == 0
        assert lag.idle_time == 0
        assert lag.consumers == 0

    def test_custom_values(self):
        """Test ConsumerLag accepts custom values."""
        lag = ConsumerLag(pending=10, idle_time=5000, consumers=3)
        assert lag.pending == 10
        assert lag.idle_time == 5000
        assert lag.consumers == 3


# --- Helper Function Tests ---


class TestParseEntryTimestamp:
    """Tests for the _parse_entry_timestamp helper."""

    def test_parse_tuple_entry(self):
        """Test parsing a timestamp from a tuple entry."""
        entry = ("1700000000000-0", {"key": "value"})
        result = _parse_entry_timestamp(entry)
        assert result is not None
        assert result.year == 2023
        assert result.tzinfo == UTC

    def test_parse_list_entry(self):
        """Test parsing a timestamp from a list entry."""
        entry = ["1700000000000-0", {"key": "value"}]
        result = _parse_entry_timestamp(entry)
        assert result is not None
        assert result.year == 2023

    def test_parse_none_returns_none(self):
        """Test that None input returns None."""
        assert _parse_entry_timestamp(None) is None

    def test_parse_invalid_entry_returns_none(self):
        """Test that an invalid entry returns None."""
        assert _parse_entry_timestamp(("invalid-id", {})) is None

    def test_parse_empty_tuple(self):
        """Test that an empty tuple returns None."""
        assert _parse_entry_timestamp(()) is None

    def test_parse_string_message_id(self):
        """Test parsing when entry is a bare string (non-list, non-tuple)."""
        result = _parse_entry_timestamp("1700000000000-0")
        assert result is not None
        assert result.year == 2023

    def test_parse_non_numeric_message_id(self):
        """Test parsing when message_id has non-numeric ms part."""
        assert _parse_entry_timestamp(("abc-0", {})) is None


# --- EventMonitor Tests ---


class TestEventMonitorInit:
    """Tests for EventMonitor initialization."""

    def test_init(self, connected_manager: RedisStreamManager):
        """Test basic initialization."""
        monitor = EventMonitor(connected_manager)
        assert repr(monitor) == "EventMonitor(connected=True)"

    def test_repr_disconnected(self):
        """Test repr when not connected."""
        manager = RedisStreamManager()
        monitor = EventMonitor(manager)
        assert "connected=False" in repr(monitor)


class TestGetStreamStats:
    """Tests for the get_stream_stats method."""

    def test_get_stream_stats_returns_stats(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test getting stream stats with valid data."""
        mock_redis_client.xinfo_stream.return_value = {
            "length": 42,
            "groups": 2,
            "first-entry": ("1700000000000-0", {"key": "value"}),
            "last-entry": ("1700000100000-0", {"key": "value"}),
        }

        stats = monitor.get_stream_stats("file-events")

        assert stats.length == 42
        assert stats.groups == 2
        assert stats.oldest_event is not None
        assert stats.newest_event is not None
        assert stats.oldest_event < stats.newest_event

    def test_get_stream_stats_empty_stream(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test stats for a stream with no entries."""
        mock_redis_client.xinfo_stream.return_value = {
            "length": 0,
            "groups": 0,
            "first-entry": None,
            "last-entry": None,
        }

        stats = monitor.get_stream_stats("file-events")

        assert stats.length == 0
        assert stats.groups == 0
        assert stats.oldest_event is None
        assert stats.newest_event is None

    def test_get_stream_stats_when_disconnected(self):
        """Test stats returns empty when not connected."""
        manager = RedisStreamManager()
        monitor = EventMonitor(manager)

        stats = monitor.get_stream_stats("file-events")

        assert stats.length == 0
        assert stats.groups == 0

    def test_get_stream_stats_handles_error(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test graceful handling of Redis errors."""
        mock_redis_client.xinfo_stream.side_effect = RuntimeError("error")

        stats = monitor.get_stream_stats("file-events")
        assert stats.length == 0

    def test_get_stream_stats_uses_prefixed_name(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test that stream names are properly prefixed."""
        mock_redis_client.xinfo_stream.return_value = {
            "length": 0,
            "groups": 0,
            "first-entry": None,
            "last-entry": None,
        }

        monitor.get_stream_stats("file-events")

        mock_redis_client.xinfo_stream.assert_called_once_with("fileorg:file-events")

    def test_get_stream_stats_missing_keys_in_response(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test stats handles missing keys in xinfo_stream response."""
        mock_redis_client.xinfo_stream.return_value = {}

        stats = monitor.get_stream_stats("file-events")
        assert stats.length == 0
        assert stats.groups == 0
        assert stats.oldest_event is None
        assert stats.newest_event is None


class TestGetConsumerLag:
    """Tests for the get_consumer_lag method."""

    def test_get_consumer_lag_returns_lag(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test getting consumer lag with valid data."""
        mock_redis_client.xpending.return_value = {"pending": 5}
        mock_redis_client.xinfo_groups.return_value = [
            {"name": "my-group", "consumers": 3, "idle": 1000},
        ]

        lag = monitor.get_consumer_lag("file-events", "my-group")

        assert lag.pending == 5
        assert lag.consumers == 3
        assert lag.idle_time == 1000

    def test_get_consumer_lag_group_not_found(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test lag when group doesn't exist in groups list."""
        mock_redis_client.xpending.return_value = {"pending": 0}
        mock_redis_client.xinfo_groups.return_value = [
            {"name": "other-group", "consumers": 1, "idle": 0},
        ]

        lag = monitor.get_consumer_lag("file-events", "my-group")

        assert lag.pending == 0
        assert lag.consumers == 0

    def test_get_consumer_lag_when_disconnected(self):
        """Test lag returns empty when not connected."""
        manager = RedisStreamManager()
        monitor = EventMonitor(manager)

        lag = monitor.get_consumer_lag("file-events", "my-group")

        assert lag.pending == 0
        assert lag.consumers == 0

    def test_get_consumer_lag_handles_error(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test graceful handling of Redis errors."""
        mock_redis_client.xpending.side_effect = RuntimeError("error")

        lag = monitor.get_consumer_lag("file-events", "my-group")
        assert lag.pending == 0

    def test_get_consumer_lag_xpending_returns_none(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test lag when xpending returns None."""
        mock_redis_client.xpending.return_value = None
        mock_redis_client.xinfo_groups.return_value = [
            {"name": "my-group", "consumers": 2, "idle": 500},
        ]

        lag = monitor.get_consumer_lag("file-events", "my-group")
        assert lag.pending == 0
        assert lag.consumers == 2

    def test_get_consumer_lag_multiple_groups(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test lag correctly finds the target group among multiple."""
        mock_redis_client.xpending.return_value = {"pending": 3}
        mock_redis_client.xinfo_groups.return_value = [
            {"name": "group-a", "consumers": 1, "idle": 100},
            {"name": "target-group", "consumers": 5, "idle": 2000},
            {"name": "group-c", "consumers": 2, "idle": 300},
        ]

        lag = monitor.get_consumer_lag("file-events", "target-group")

        assert lag.pending == 3
        assert lag.consumers == 5
        assert lag.idle_time == 2000


class TestGetEventRate:
    """Tests for the get_event_rate method."""

    def test_get_event_rate_calculates_correctly(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test event rate calculation with known events."""
        # 10 events in 60 seconds = ~0.167 events/sec
        mock_redis_client.xrange.return_value = [
            (f"17000000{i:05d}-0", {"key": "value"}) for i in range(10)
        ]

        rate = monitor.get_event_rate("file-events", window_seconds=60)

        assert abs(rate - 10 / 60) < 0.01

    def test_get_event_rate_no_events(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test rate when no events in window."""
        mock_redis_client.xrange.return_value = []

        rate = monitor.get_event_rate("file-events", window_seconds=60)
        assert rate == 0.0

    def test_get_event_rate_zero_window(
        self,
        monitor: EventMonitor,
    ):
        """Test rate with zero window returns 0."""
        rate = monitor.get_event_rate("file-events", window_seconds=0)
        assert rate == 0.0

    def test_get_event_rate_negative_window(
        self,
        monitor: EventMonitor,
    ):
        """Test rate with negative window returns 0."""
        rate = monitor.get_event_rate("file-events", window_seconds=-10)
        assert rate == 0.0

    def test_get_event_rate_when_disconnected(self):
        """Test rate returns 0 when not connected."""
        manager = RedisStreamManager()
        monitor = EventMonitor(manager)

        rate = monitor.get_event_rate("file-events")
        assert rate == 0.0

    def test_get_event_rate_handles_error(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test graceful handling of Redis errors."""
        mock_redis_client.xrange.side_effect = RuntimeError("error")

        rate = monitor.get_event_rate("file-events")
        assert rate == 0.0

    def test_get_event_rate_xrange_returns_none(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test rate when xrange returns None."""
        mock_redis_client.xrange.return_value = None

        rate = monitor.get_event_rate("file-events", window_seconds=30)
        assert rate == 0.0

    def test_get_event_rate_single_event(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test rate with a single event in the window."""
        mock_redis_client.xrange.return_value = [
            ("1700000000000-0", {"key": "value"})
        ]

        rate = monitor.get_event_rate("file-events", window_seconds=10)
        assert abs(rate - 0.1) < 0.01

    def test_get_event_rate_uses_prefixed_stream(
        self,
        monitor: EventMonitor,
        mock_redis_client: MagicMock,
    ):
        """Test that event rate uses the prefixed stream name."""
        mock_redis_client.xrange.return_value = []

        monitor.get_event_rate("my-stream", window_seconds=60)

        call_args = mock_redis_client.xrange.call_args
        assert call_args.args[0] == "fileorg:my-stream"
