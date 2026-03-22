"""Integration tests targeting uncovered branches in replay.py.

Targets: replay_to_consumer with delay, full-batch pagination exact boundary,
_increment_id edge cases, replay_by_id xrange call arg verification,
repr() output, and dry_run with multiple events.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, call, patch

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
from file_organizer.events.types import EventType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_redis_client() -> MagicMock:
    """Return a MagicMock redis client with ping configured to return True."""
    client = MagicMock()
    client.ping.return_value = True
    return client


@pytest.fixture()
def connected_manager(mock_redis_client: MagicMock) -> RedisStreamManager:
    """Yield a RedisStreamManager that is already connected via a mock redis client."""
    with patch("file_organizer.events.stream.redis") as mock_redis_mod:
        mock_redis_mod.Redis.from_url.return_value = mock_redis_client
        manager = RedisStreamManager()
        manager.connect()
        yield manager


@pytest.fixture()
def replay_manager(connected_manager: RedisStreamManager) -> EventReplayManager:
    """Return an EventReplayManager backed by the connected_manager fixture."""
    return EventReplayManager(connected_manager)


# ---------------------------------------------------------------------------
# _increment_id — edge cases
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestIncrementIdEdgeCases:
    """_increment_id handles normal and malformed IDs."""

    def test_increments_sequence_from_zero(self):
        """Increments the sequence part of a Redis ID starting at zero."""
        assert _increment_id("1700000000000-0") == "1700000000000-1"

    def test_increments_sequence_from_nonzero(self):
        """Increments a non-zero sequence number correctly."""
        assert _increment_id("1700000000000-99") == "1700000000000-100"

    def test_ms_part_preserved(self):
        """Millisecond prefix is preserved after incrementing the sequence."""
        result = _increment_id("9876543210000-3")
        assert result.startswith("9876543210000-")
        assert result == "9876543210000-4"

    def test_invalid_no_dash_returns_unchanged(self):
        """Returns the ID unchanged when no dash separator is present."""
        assert _increment_id("nodash") == "nodash"

    def test_empty_string_returns_empty(self):
        """Returns an empty string unchanged."""
        assert _increment_id("") == ""

    def test_non_numeric_seq_returns_unchanged(self):
        """Returns the ID unchanged when the sequence part is non-numeric."""
        assert _increment_id("1234-abc") == "1234-abc"

    def test_multiple_dashes_uses_first_split(self):
        """Uses only the first two dash-separated parts when multiple dashes are present."""
        # "1000-5-3": only ms (parts[0]) and seq (parts[1]+1) are kept; third part is dropped
        result = _increment_id("1000-5-3")
        assert result == "1000-6"


# ---------------------------------------------------------------------------
# _datetime_to_redis_ms — precision
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestDatetimeToRedisMsPrecision:
    """_datetime_to_redis_ms produces the correct millisecond string."""

    def test_round_second_timestamp(self):
        """Converts a round-second datetime to the correct millisecond string."""
        dt = datetime(2024, 6, 1, 0, 0, 0, tzinfo=UTC)
        result = _datetime_to_redis_ms(dt)
        assert result == str(int(dt.timestamp() * 1000))
        assert result.isdigit()

    def test_sub_second_microseconds_truncated_to_ms(self):
        """Sub-second microseconds are truncated, not rounded, to milliseconds."""
        dt = datetime(2024, 6, 1, 0, 0, 0, 750000, tzinfo=UTC)
        result = _datetime_to_redis_ms(dt)
        expected = str(int(dt.timestamp() * 1000))
        assert result == expected

    def test_result_is_string(self):
        """Result is a pure integer string with no decimal point."""
        dt = datetime(2024, 1, 1, tzinfo=UTC)
        result = _datetime_to_redis_ms(dt)
        assert "." not in result


# ---------------------------------------------------------------------------
# _parse_timestamp_from_id — in replay module
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReplayParseTimestampBranches:
    """_parse_timestamp_from_id in replay.py covers same logic as stream.py."""

    def test_valid_id_gives_correct_year(self):
        """Parses a known epoch-ms ID and returns a UTC datetime with correct year."""
        result = _parse_timestamp_from_id("1700000000000-0")
        assert result.year == 2023
        assert result.tzinfo == UTC

    def test_non_numeric_part_falls_back_to_now(self):
        """Falls back to now() when the ms part of the ID is non-numeric."""
        before = datetime.now(UTC)
        result = _parse_timestamp_from_id("garbage-0")
        after = datetime.now(UTC)
        assert before <= result <= after

    def test_empty_string_falls_back_to_now(self):
        """Falls back to now() when given an empty string ID."""
        before = datetime.now(UTC)
        result = _parse_timestamp_from_id("")
        after = datetime.now(UTC)
        assert before <= result <= after


# ---------------------------------------------------------------------------
# replay_range — pagination boundary: exactly batch_size → loop continues
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReplayRangePaginationBranches:
    """Verifies the full-batch pagination loop in replay_range."""

    def test_full_batch_triggers_second_page(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """When first batch returns exactly batch_size items, must read another page."""
        config = ReplayConfig(batch_size=2)
        replay = EventReplayManager(connected_manager, replay_config=config)
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        mock_redis_client.xrange.side_effect = [
            [
                ("1704067200000-0", {"event_type": "a"}),
                ("1704067200001-0", {"event_type": "b"}),
            ],
            [],
        ]

        events = replay.replay_range("file-events", start, end)

        assert len(events) == 2
        assert mock_redis_client.xrange.call_count == 2

    def test_second_page_min_id_is_incremented(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """Second xrange call must use incremented ID of last result from first batch."""
        config = ReplayConfig(batch_size=1)
        replay = EventReplayManager(connected_manager, replay_config=config)
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        mock_redis_client.xrange.side_effect = [
            [("1704067200000-0", {"event_type": "a"})],
            [],
        ]

        replay.replay_range("file-events", start, end)

        second_call_args = mock_redis_client.xrange.call_args_list[1]
        assert second_call_args[1]["min"] == "1704067200000-1"

    def test_three_batches_collected_correctly(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """Three-batch scenario: first two full, third partial."""
        config = ReplayConfig(batch_size=2)
        replay = EventReplayManager(connected_manager, replay_config=config)
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        mock_redis_client.xrange.side_effect = [
            [
                ("1000-0", {"event_type": "a"}),
                ("1001-0", {"event_type": "b"}),
            ],
            [
                ("1002-0", {"event_type": "c"}),
                ("1003-0", {"event_type": "d"}),
            ],
            [
                ("1004-0", {"event_type": "e"}),
            ],
        ]

        events = replay.replay_range("file-events", start, end)

        assert len(events) == 5
        assert mock_redis_client.xrange.call_count == 3
        assert events[0].id == "1000-0"
        assert events[4].id == "1004-0"

    def test_replay_range_passes_count_from_batch_size(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """xrange is called with count equal to the configured batch_size."""
        config = ReplayConfig(batch_size=42)
        replay = EventReplayManager(connected_manager, replay_config=config)
        start = datetime(2024, 1, 1, tzinfo=UTC)
        end = datetime(2024, 1, 2, tzinfo=UTC)

        mock_redis_client.xrange.return_value = []

        replay.replay_range("file-events", start, end)

        call_kwargs = mock_redis_client.xrange.call_args.kwargs
        assert call_kwargs["count"] == 42


# ---------------------------------------------------------------------------
# replay_by_id — xrange call args verified exactly
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReplayByIdCallArgs:
    """Verifies that replay_by_id issues correct xrange calls per message ID."""

    def test_each_id_gets_its_own_xrange_call(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Each requested message ID triggers a separate xrange call with exact min/max/count."""
        mock_redis_client.xrange.side_effect = [
            [("1704067200000-0", {"event_type": "file.created"})],
            [("1704067200001-0", {"event_type": "file.modified"})],
        ]

        events = replay_manager.replay_by_id(
            "file-events",
            ["1704067200000-0", "1704067200001-0"],
        )

        assert len(events) == 2
        assert mock_redis_client.xrange.call_count == 2

        first_call = mock_redis_client.xrange.call_args_list[0]
        assert first_call[0][0] == "fileorg:file-events"
        assert first_call[1]["min"] == "1704067200000-0"
        assert first_call[1]["max"] == "1704067200000-0"
        assert first_call[1]["count"] == 1

        second_call = mock_redis_client.xrange.call_args_list[1]
        assert second_call[1]["min"] == "1704067200001-0"
        assert second_call[1]["max"] == "1704067200001-0"

    def test_event_data_matches_what_redis_returns(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Returned Event objects contain the id, data, and stream name from Redis."""
        mock_redis_client.xrange.return_value = [
            ("1704067200000-0", {"event_type": "file.created", "file_path": "/docs/a.pdf"})
        ]

        events = replay_manager.replay_by_id("file-events", ["1704067200000-0"])

        assert len(events) == 1
        assert events[0].id == "1704067200000-0"
        assert events[0].data["file_path"] == "/docs/a.pdf"
        assert events[0].stream == "fileorg:file-events"

    def test_all_missing_ids_returns_empty(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Returns an empty list when xrange finds no entries for any requested ID."""
        mock_redis_client.xrange.return_value = []

        events = replay_manager.replay_by_id(
            "file-events",
            ["missing-1", "missing-2"],
        )

        assert events == []
        assert mock_redis_client.xrange.call_count == 2

    def test_redis_error_returns_empty(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Returns an empty list when Redis raises an error during lookup."""
        mock_redis_client.xrange.side_effect = RuntimeError("timeout")

        events = replay_manager.replay_by_id("file-events", ["1-0"])
        assert events == []


# ---------------------------------------------------------------------------
# replay_to_consumer — delay_between_events branch
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReplayToConsumerDelayBranch:
    """Covers the time.sleep branch inside replay_to_consumer."""

    def test_sleep_called_with_correct_delay(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """time.sleep is called once per replayed event with the configured delay."""
        config = ReplayConfig(delay_between_events=0.05)
        replay = EventReplayManager(connected_manager, replay_config=config)

        mock_redis_client.xrange.return_value = [
            ("1704067200000-0", {"event_type": "file.created"}),
            ("1704067200001-0", {"event_type": "file.modified"}),
        ]

        consumer = EventConsumer()
        start = datetime(2024, 1, 1, tzinfo=UTC)

        with patch("file_organizer.events.replay.time") as mock_time:
            count = replay.replay_to_consumer("file-events", start, consumer)

        assert count == 2
        assert mock_time.sleep.call_count == 2
        mock_time.sleep.assert_has_calls([call(0.05), call(0.05)])

    def test_no_sleep_when_delay_is_zero(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """time.sleep is never called when delay_between_events is 0.0."""
        config = ReplayConfig(delay_between_events=0.0)
        replay = EventReplayManager(connected_manager, replay_config=config)

        mock_redis_client.xrange.return_value = [
            ("1704067200000-0", {"event_type": "file.created"}),
        ]

        consumer = EventConsumer()
        start = datetime(2024, 1, 1, tzinfo=UTC)

        with patch("file_organizer.events.replay.time") as mock_time:
            count = replay.replay_to_consumer("file-events", start, consumer)

        assert count == 1
        mock_time.sleep.assert_not_called()

    def test_delay_applied_once_per_event_not_per_handler(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """Sleep fires once per event, even if multiple handlers match the event type."""

        config = ReplayConfig(delay_between_events=0.01)
        replay = EventReplayManager(connected_manager, replay_config=config)

        mock_redis_client.xrange.return_value = [
            ("1704067200000-0", {"event_type": "file.created"}),
        ]

        handler_a = MagicMock()
        handler_b = MagicMock()
        consumer = EventConsumer()
        consumer.register_handler(EventType.FILE_CREATED, handler_a)
        consumer.register_handler(EventType.FILE_CREATED, handler_b)

        start = datetime(2024, 1, 1, tzinfo=UTC)

        with patch("file_organizer.events.replay.time") as mock_time:
            count = replay.replay_to_consumer("file-events", start, consumer)

        assert count == 1
        assert mock_time.sleep.call_count == 1
        handler_a.assert_called_once()
        handler_b.assert_called_once()


# ---------------------------------------------------------------------------
# replay_to_consumer — dry_run with multiple events
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReplayToConsumerDryRun:
    """dry_run=True must return 0 and never call handlers, regardless of event count."""

    def test_dry_run_returns_zero_for_multiple_events(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """dry_run=True returns 0 events and does not invoke any handlers."""
        config = ReplayConfig(dry_run=True)
        replay = EventReplayManager(connected_manager, replay_config=config)

        mock_redis_client.xrange.return_value = [
            ("1000-0", {"event_type": "file.created"}),
            ("1001-0", {"event_type": "file.modified"}),
            ("1002-0", {"event_type": "file.deleted"}),
        ]

        handler = MagicMock()
        consumer = EventConsumer()

        consumer.register_handler(EventType.FILE_CREATED, handler)

        start = datetime(2024, 1, 1, tzinfo=UTC)
        count = replay.replay_to_consumer("file-events", start, consumer)

        assert count == 0
        handler.assert_not_called()

    def test_dry_run_does_not_sleep(
        self,
        connected_manager: RedisStreamManager,
        mock_redis_client: MagicMock,
    ):
        """dry_run=True skips time.sleep even when delay_between_events is non-zero."""
        config = ReplayConfig(dry_run=True, delay_between_events=1.0)
        replay = EventReplayManager(connected_manager, replay_config=config)

        mock_redis_client.xrange.return_value = [
            ("1000-0", {"event_type": "file.created"}),
        ]

        start = datetime(2024, 1, 1, tzinfo=UTC)
        consumer = EventConsumer()

        with patch("file_organizer.events.replay.time") as mock_time:
            count = replay.replay_to_consumer("file-events", start, consumer)

        assert count == 0
        mock_time.sleep.assert_not_called()


# ---------------------------------------------------------------------------
# replay_to_consumer — handler error continues counting
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestReplayToConsumerHandlerError:
    """Handler exceptions must not prevent event count from incrementing."""

    def test_failing_handler_event_still_counted(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """Events are counted even when the registered handler raises an exception."""
        mock_redis_client.xrange.return_value = [
            ("1000-0", {"event_type": "file.created"}),
            ("1001-0", {"event_type": "file.created"}),
        ]

        failing_handler = MagicMock(side_effect=RuntimeError("boom"))
        consumer = EventConsumer()
        consumer.register_handler(EventType.FILE_CREATED, failing_handler)

        start = datetime(2024, 1, 1, tzinfo=UTC)
        count = replay_manager.replay_to_consumer("file-events", start, consumer)

        assert count == 2
        assert failing_handler.call_count == 2

    def test_second_handler_still_called_after_first_fails(
        self,
        replay_manager: EventReplayManager,
        mock_redis_client: MagicMock,
    ):
        """A second handler for the same event type still runs after the first handler fails."""
        mock_redis_client.xrange.return_value = [
            ("1000-0", {"event_type": "file.created"}),
        ]

        failing_handler = MagicMock(side_effect=RuntimeError("first fails"))
        second_handler = MagicMock()
        consumer = EventConsumer()
        consumer.register_handler(EventType.FILE_CREATED, failing_handler)
        consumer.register_handler(EventType.FILE_CREATED, second_handler)

        start = datetime(2024, 1, 1, tzinfo=UTC)
        count = replay_manager.replay_to_consumer("file-events", start, consumer)

        assert count == 1
        failing_handler.assert_called_once()
        second_handler.assert_called_once()


# ---------------------------------------------------------------------------
# repr
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestEventReplayManagerRepr:
    """repr() reflects manager state accurately."""

    def test_repr_shows_connected_and_batch_size(self, replay_manager: EventReplayManager):
        """repr() includes connected=True, batch_size, and dry_run=False for a live manager."""
        result = repr(replay_manager)
        assert "EventReplayManager" in result
        assert "connected=True" in result
        assert "batch_size=100" in result
        assert "dry_run=False" in result

    def test_repr_shows_dry_run_true(self, connected_manager: RedisStreamManager):
        """repr() reflects dry_run=True and custom batch_size when configured."""
        config = ReplayConfig(dry_run=True, batch_size=50)
        replay = EventReplayManager(connected_manager, replay_config=config)
        result = repr(replay)
        assert "dry_run=True" in result
        assert "batch_size=50" in result

    def test_repr_when_disconnected(self):
        """repr() shows connected=False when the underlying manager is not connected."""
        manager = RedisStreamManager()
        replay = EventReplayManager(manager)
        result = repr(replay)
        assert "connected=False" in result
