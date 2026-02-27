"""
Unit tests for EventReplayManager.

Tests event replay by time range, by message ID, and replay-to-consumer
functionality. All tests mock Redis to avoid requiring a running instance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.events.consumer import EventConsumer
from file_organizer.events.replay import (
    EventReplayManager,
    ReplayConfig,
    _datetime_to_redis_ms,
    _increment_id,
    _parse_timestamp_from_id,
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
def replay_manager(connected_manager: RedisStreamManager) -> EventReplayManager:
    """Create an EventReplayManager with a connected stream manager."""
    return EventReplayManager(connected_manager)


# --- ReplayConfig Tests ---


@pytest.mark.unit
class TestReplayConfig:
    """Tests for the ReplayConfig dataclass."""

    def test_default_values(self):
        """Test ReplayConfig has sensible defaults."""
        config = ReplayConfig()
        assert config.batch_size == 100
        assert config.delay_between_events == 0.0
        assert config.dry_run is False

    def test_custom_values(self):
        """Test ReplayConfig accepts custom values."""
        config = ReplayConfig(
            batch_size=50,
            delay_between_events=0.5,
            dry_run=True,
        )
        assert config.batch_size == 50
        assert config.delay_between_events == 0.5
        assert config.dry_run is True


# --- Helper Function Tests ---


@pytest.mark.unit
class TestDatetimeToRedisMs:
    """Tests for the _datetime_to_redis_ms helper."""

    def test_converts_datetime_to_ms_string(self):
        """Test converting a datetime to Redis millisecond timestamp."""
        dt = datetime(2024, 1, 15, 12, 0, 0, tzinfo=UTC)
        result = _datetime_to_redis_ms(dt)
        assert result == str(int(dt.timestamp() * 1000))
        assert result.isdigit()

    def test_preserves_millisecond_precision(self):
        """Test that millisecond precision is preserved."""
        dt = datetime(2024, 1, 15, 12, 0, 0, 500000, tzinfo=UTC)
        result = _datetime_to_redis_ms(dt)
        expected_ms = int(dt.timestamp() * 1000)
        assert result == str(expected_ms)


@pytest.mark.unit
class TestParseTimestampFromId:
    """Tests for the _parse_timestamp_from_id helper."""

    def test_parse_valid_id(self):
        """Test parsing a valid Redis Stream message ID."""
        result = _parse_timestamp_from_id("1700000000000-0")
        assert result.year == 2023
        assert result.tzinfo == UTC

    def test_parse_invalid_id_returns_now(self):
        """Test that invalid IDs return current time."""
        before = datetime.now(UTC)
        result = _parse_timestamp_from_id("invalid")
        after = datetime.now(UTC)
        assert before <= result <= after


@pytest.mark.unit
class TestIncrementId:
    """Tests for the _increment_id helper."""

    def test_increment_sequence(self):
        """Test incrementing the sequence number."""
        assert _increment_id("1700000000000-0") == "1700000000000-1"
        assert _increment_id("1700000000000-5") == "1700000000000-6"

    def test_invalid_id_returns_unchanged(self):
        """Test that an invalid ID is returned unchanged."""
        assert _increment_id("invalid") == "invalid"
        assert _increment_id("") == ""


# --- EventReplayManager Tests ---


@pytest.mark.unit
class TestEventReplayManagerInit:
    """Tests for EventReplayManager initialization."""

    def test_default_config(self, connected_manager: RedisStreamManager):
        """Test initialization with default replay config."""
        replay = EventReplayManager(connected_manager)
        assert replay.config.batch_size == 100
        assert replay.config.dry_run is False

    def test_custom_config(self, connected_manager: RedisStreamManager):
        """Test initialization with custom replay config."""
        config = ReplayConfig(batch_size=50, dry_run=True)
        replay = EventReplayManager(connected_manager, replay_config=config)
        assert replay.config.batch_size == 50
        assert replay.config.dry_run is True

    def test_repr(self, replay_manager: EventReplayManager):
        """Test string representation."""
        result = repr(replay_manager)
        assert "EventReplayManager" in result
        assert "connected=True" in result
        assert "batch_size=100" in result


@pytest.mark.unit
class TestReplayRange:
    """Tests for the replay_range method."""

    def test_replay_range_returns_events(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test replaying events within a time range."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        mock_redis_client.xrange.return_value = [
            ("1704067200000-0", {"event_type": "file.created", "file_path": "/a.txt"}),
            ("1704067200001-0", {"event_type": "file.modified", "file_path": "/b.txt"}),
        ]

        events = replay_manager.replay_range("file-events", start, end)

        assert len(events) == 2
        assert events[0].id == "1704067200000-0"
        assert events[0].data["file_path"] == "/a.txt"
        assert events[1].id == "1704067200001-0"

    def test_replay_range_empty_results(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test replaying when no events exist in range."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        mock_redis_client.xrange.return_value = []

        events = replay_manager.replay_range("file-events", start, end)
        assert events == []

    def test_replay_range_handles_redis_error(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test graceful handling of Redis errors during replay."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        mock_redis_client.xrange.side_effect = RuntimeError("connection lost")

        events = replay_manager.replay_range("file-events", start, end)
        assert events == []

    def test_replay_range_when_disconnected(self):
        """Test replay returns empty list when not connected."""
        manager = RedisStreamManager()
        replay = EventReplayManager(manager)

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        events = replay.replay_range("file-events", start, end)
        assert events == []

    def test_replay_range_batching(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """Test that replay correctly batches large result sets."""
        config = ReplayConfig(batch_size=2)
        replay = EventReplayManager(connected_manager, replay_config=config)

        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        # First call returns batch_size (2) results, second returns less
        mock_redis_client.xrange.side_effect = [
            [
                ("1704067200000-0", {"event_type": "file.created"}),
                ("1704067200001-0", {"event_type": "file.modified"}),
            ],
            [
                ("1704067200002-0", {"event_type": "file.deleted"}),
            ],
        ]

        events = replay.replay_range("file-events", start, end)

        assert len(events) == 3
        assert mock_redis_client.xrange.call_count == 2

    def test_replay_range_uses_prefixed_stream_name(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test that stream names are properly prefixed."""
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        mock_redis_client.xrange.return_value = []

        replay_manager.replay_range("file-events", start, end)

        call_args = mock_redis_client.xrange.call_args
        assert call_args[0][0] == "fileorg:file-events"


@pytest.mark.unit
class TestReplayById:
    """Tests for the replay_by_id method."""

    def test_replay_by_id_returns_events(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test replaying specific events by message ID."""
        mock_redis_client.xrange.side_effect = [
            [("1704067200000-0", {"event_type": "file.created"})],
            [("1704067200001-0", {"event_type": "file.modified"})],
        ]

        events = replay_manager.replay_by_id(
            "file-events",
            ["1704067200000-0", "1704067200001-0"],
        )

        assert len(events) == 2
        assert events[0].id == "1704067200000-0"
        assert events[1].id == "1704067200001-0"

    def test_replay_by_id_skips_missing(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test that missing messages are silently skipped."""
        mock_redis_client.xrange.side_effect = [
            [("1704067200000-0", {"event_type": "file.created"})],
            [],  # Second ID not found
        ]

        events = replay_manager.replay_by_id(
            "file-events",
            ["1704067200000-0", "nonexistent-0"],
        )

        assert len(events) == 1

    def test_replay_by_id_empty_list(
        self,
        replay_manager: EventReplayManager,
    ):
        """Test replaying with an empty ID list."""
        events = replay_manager.replay_by_id("file-events", [])
        assert events == []

    def test_replay_by_id_when_disconnected(self):
        """Test replay by ID returns empty list when not connected."""
        manager = RedisStreamManager()
        replay = EventReplayManager(manager)

        events = replay.replay_by_id("file-events", ["1-0"])
        assert events == []

    def test_replay_by_id_handles_redis_error(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test graceful handling of Redis errors."""
        mock_redis_client.xrange.side_effect = RuntimeError("connection lost")

        events = replay_manager.replay_by_id("file-events", ["1704067200000-0"])
        assert events == []


@pytest.mark.unit
class TestReplayToConsumer:
    """Tests for the replay_to_consumer method."""

    def test_replay_to_consumer_dispatches_events(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test replaying events to a consumer calls handlers."""
        mock_redis_client.xrange.return_value = [
            ("1704067200000-0", {"event_type": "file.created", "file_path": "/a.txt"}),
        ]

        handler = MagicMock()
        consumer = EventConsumer()
        from file_organizer.events.types import EventType

        consumer.register_handler(EventType.FILE_CREATED, handler)

        start = datetime(2024, 1, 1, tzinfo=UTC)
        count = replay_manager.replay_to_consumer("file-events", start, consumer)

        assert count == 1
        handler.assert_called_once()

    def test_replay_to_consumer_dry_run(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """Test that dry run does not dispatch events."""
        config = ReplayConfig(dry_run=True)
        replay = EventReplayManager(connected_manager, replay_config=config)

        mock_redis_client.xrange.return_value = [
            ("1704067200000-0", {"event_type": "file.created"}),
        ]

        handler = MagicMock()
        consumer = EventConsumer()
        from file_organizer.events.types import EventType

        consumer.register_handler(EventType.FILE_CREATED, handler)

        start = datetime(2024, 1, 1, tzinfo=UTC)
        count = replay.replay_to_consumer("file-events", start, consumer)

        assert count == 0
        handler.assert_not_called()

    def test_replay_to_consumer_handler_error(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test that handler errors are caught and logged."""
        mock_redis_client.xrange.return_value = [
            ("1704067200000-0", {"event_type": "file.created"}),
        ]

        handler = MagicMock(side_effect=RuntimeError("handler failed"))
        consumer = EventConsumer()
        from file_organizer.events.types import EventType

        consumer.register_handler(EventType.FILE_CREATED, handler)

        start = datetime(2024, 1, 1, tzinfo=UTC)
        count = replay_manager.replay_to_consumer("file-events", start, consumer)

        # Event is still counted as dispatched even if handler fails
        assert count == 1
        handler.assert_called_once()

    def test_replay_to_consumer_no_matching_handlers(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Test replay with no matching handlers still counts events."""
        mock_redis_client.xrange.return_value = [
            ("1704067200000-0", {"event_type": "file.created"}),
        ]

        consumer = EventConsumer()  # No handlers registered

        start = datetime(2024, 1, 1, tzinfo=UTC)
        count = replay_manager.replay_to_consumer("file-events", start, consumer)

        assert count == 1
