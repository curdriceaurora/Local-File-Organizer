"""
Unit tests for EventConsumer.

Tests event handler registration, dispatching, start/stop lifecycle,
and acknowledgment behavior. All tests mock the underlying
RedisStreamManager.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from file_organizer.events.config import EventConfig
from file_organizer.events.consumer import EventConsumer
from file_organizer.events.stream import Event, RedisStreamManager
from file_organizer.events.types import EventType


@pytest.fixture
def mock_manager() -> MagicMock:
    """Create a mock RedisStreamManager."""
    manager = MagicMock(spec=RedisStreamManager)
    manager.is_connected = True
    manager.connect.return_value = True
    manager.create_consumer_group.return_value = True
    manager.acknowledge.return_value = True
    return manager


@pytest.fixture
def consumer(mock_manager: MagicMock) -> EventConsumer:
    """Create an EventConsumer with a mocked stream manager."""
    return EventConsumer(stream_manager=mock_manager)


@pytest.mark.unit
class TestEventConsumerInit:
    """Tests for EventConsumer initialization."""

    def test_default_init(self):
        """Test initialization with defaults."""
        c = EventConsumer()
        assert c.is_connected is False
        assert c.is_running is False
        assert c.events_processed == 0
        assert c.registered_handlers == {}

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = EventConfig(consumer_group="custom-group")
        c = EventConsumer(config=config)
        assert c.events_processed == 0

    def test_init_with_consumer_name(self, mock_manager: MagicMock):
        """Test initialization with a custom consumer name."""
        c = EventConsumer(stream_manager=mock_manager, consumer_name="worker-5")
        assert c.is_connected is True

    def test_repr(self, consumer: EventConsumer):
        """Test string representation."""
        result = repr(consumer)
        assert "EventConsumer" in result
        assert "running=False" in result
        assert "processed=0" in result


@pytest.mark.unit
class TestEventConsumerHandlerRegistration:
    """Tests for handler registration and unregistration."""

    def test_register_handler(self, consumer: EventConsumer):
        """Test registering a single handler."""
        handler = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler)

        assert consumer.registered_handlers == {"file.created": 1}

    def test_register_multiple_handlers_same_type(self, consumer: EventConsumer):
        """Test registering multiple handlers for the same event type."""
        handler1 = MagicMock()
        handler2 = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler1)
        consumer.register_handler(EventType.FILE_CREATED, handler2)

        assert consumer.registered_handlers == {"file.created": 2}

    def test_register_handlers_different_types(self, consumer: EventConsumer):
        """Test registering handlers for different event types."""
        handler1 = MagicMock()
        handler2 = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler1)
        consumer.register_handler(EventType.FILE_DELETED, handler2)

        assert consumer.registered_handlers == {
            "file.created": 1,
            "file.deleted": 1,
        }

    def test_unregister_handler(self, consumer: EventConsumer):
        """Test unregistering a handler."""
        handler = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler)
        result = consumer.unregister_handler(EventType.FILE_CREATED, handler)

        assert result is True
        assert consumer.registered_handlers == {}

    def test_unregister_nonexistent_handler(self, consumer: EventConsumer):
        """Test unregistering a handler that was not registered."""
        handler = MagicMock()
        result = consumer.unregister_handler(EventType.FILE_CREATED, handler)
        assert result is False

    def test_unregister_one_of_multiple(self, consumer: EventConsumer):
        """Test unregistering one handler leaves others."""
        handler1 = MagicMock()
        handler2 = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler1)
        consumer.register_handler(EventType.FILE_CREATED, handler2)

        consumer.unregister_handler(EventType.FILE_CREATED, handler1)
        assert consumer.registered_handlers == {"file.created": 1}

    def test_unregister_wrong_type(self, consumer: EventConsumer):
        """Test unregistering handler from a type it was not registered for."""
        handler = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler)
        result = consumer.unregister_handler(EventType.FILE_DELETED, handler)
        assert result is False
        assert consumer.registered_handlers == {"file.created": 1}

    def test_unregister_different_handler_same_type(self, consumer: EventConsumer):
        """Test unregistering a different handler of the same type."""
        handler1 = MagicMock()
        handler2 = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler1)
        result = consumer.unregister_handler(EventType.FILE_CREATED, handler2)
        assert result is False
        assert consumer.registered_handlers == {"file.created": 1}


@pytest.mark.unit
class TestEventConsumerDispatch:
    """Tests for event dispatching to handlers."""

    def test_dispatch_calls_handler(self, consumer: EventConsumer, mock_manager: MagicMock):
        """Test that dispatching an event calls the registered handler."""
        handler = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler)

        event = Event(
            id="1-0",
            stream="fileorg:file-events",
            data={"event_type": "file.created", "file_path": "/a.txt"},
        )

        consumer._dispatch_event(event, "file-events", "file-organizer")

        handler.assert_called_once_with(event)
        mock_manager.acknowledge.assert_called_once_with("file-events", "file-organizer", "1-0")
        assert consumer.events_processed == 1

    def test_dispatch_calls_multiple_handlers(
        self, consumer: EventConsumer, mock_manager: MagicMock
    ):
        """Test dispatching calls all handlers for an event type."""
        handler1 = MagicMock()
        handler2 = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler1)
        consumer.register_handler(EventType.FILE_CREATED, handler2)

        event = Event(
            id="1-0",
            stream="fileorg:file-events",
            data={"event_type": "file.created", "file_path": "/a.txt"},
        )

        consumer._dispatch_event(event, "file-events", "file-organizer")

        handler1.assert_called_once_with(event)
        handler2.assert_called_once_with(event)

    def test_dispatch_no_handlers_acknowledges(
        self, consumer: EventConsumer, mock_manager: MagicMock
    ):
        """Test that events with no handlers are acknowledged."""
        event = Event(
            id="1-0",
            stream="fileorg:file-events",
            data={"event_type": "file.created", "file_path": "/a.txt"},
        )

        consumer._dispatch_event(event, "file-events", "file-organizer")

        mock_manager.acknowledge.assert_called_once_with("file-events", "file-organizer", "1-0")
        assert consumer.events_processed == 0

    def test_dispatch_handler_failure_skips_ack(
        self, consumer: EventConsumer, mock_manager: MagicMock
    ):
        """Test that failed handlers prevent acknowledgment."""
        handler = MagicMock(side_effect=RuntimeError("handler failed"))
        consumer.register_handler(EventType.FILE_CREATED, handler)

        event = Event(
            id="1-0",
            stream="fileorg:file-events",
            data={"event_type": "file.created", "file_path": "/a.txt"},
        )

        consumer._dispatch_event(event, "file-events", "file-organizer")

        mock_manager.acknowledge.assert_not_called()
        assert consumer.events_processed == 0

    def test_dispatch_partial_handler_failure(
        self, consumer: EventConsumer, mock_manager: MagicMock
    ):
        """Test that one failing handler prevents ack even if others succeed."""
        handler1 = MagicMock()  # Will succeed
        handler2 = MagicMock(side_effect=RuntimeError("fail"))  # Will fail
        consumer.register_handler(EventType.FILE_CREATED, handler1)
        consumer.register_handler(EventType.FILE_CREATED, handler2)

        event = Event(
            id="1-0",
            stream="fileorg:file-events",
            data={"event_type": "file.created", "file_path": "/a.txt"},
        )

        consumer._dispatch_event(event, "file-events", "file-organizer")

        handler1.assert_called_once()
        handler2.assert_called_once()
        mock_manager.acknowledge.assert_not_called()

    def test_dispatch_empty_event_type(self, consumer: EventConsumer, mock_manager: MagicMock):
        """Test dispatching an event with empty event_type acknowledges it."""
        event = Event(
            id="2-0",
            stream="fileorg:file-events",
            data={"file_path": "/a.txt"},
        )
        consumer._dispatch_event(event, "file-events", "file-organizer")
        mock_manager.acknowledge.assert_called_once_with("file-events", "file-organizer", "2-0")

    def test_dispatch_unknown_event_type_acknowledges(
        self, consumer: EventConsumer, mock_manager: MagicMock
    ):
        """Test dispatching an event with an unregistered type acknowledges it."""
        consumer.register_handler(EventType.FILE_CREATED, MagicMock())
        event = Event(
            id="3-0",
            stream="fileorg:file-events",
            data={"event_type": "some.other.type"},
        )
        consumer._dispatch_event(event, "file-events", "file-organizer")
        mock_manager.acknowledge.assert_called_once()
        assert consumer.events_processed == 0


@pytest.mark.unit
class TestEventConsumerStartStop:
    """Tests for start/stop consuming lifecycle."""

    def test_stop(self, consumer: EventConsumer):
        """Test stop signal."""
        consumer._running = True
        consumer.stop()
        assert consumer.is_running is False

    def test_stop_when_not_running(self, consumer: EventConsumer):
        """Test stop when not running is safe."""
        consumer.stop()
        assert consumer.is_running is False

    @pytest.mark.asyncio
    async def test_start_consuming_not_connected(self):
        """Test that consuming does not start when not connected."""
        mock_mgr = MagicMock(spec=RedisStreamManager)
        mock_mgr.is_connected = False
        consumer = EventConsumer(stream_manager=mock_mgr)

        await consumer.start_consuming("file-events")

        mock_mgr.create_consumer_group.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_consuming_processes_events(self, mock_manager: MagicMock):
        """Test that start_consuming processes events and can be stopped."""
        event = Event(
            id="1-0",
            stream="fileorg:file-events",
            data={"event_type": "file.created", "file_path": "/a.txt"},
        )

        # First call returns events, then consumer is stopped
        call_count = 0

        def read_side_effect(**kwargs):  # type: ignore[no-untyped-def]
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [event]
            return []

        mock_manager.read_group.side_effect = read_side_effect

        consumer = EventConsumer(stream_manager=mock_manager)
        handler = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler)

        # Run consuming in background, stop after short delay
        async def stop_after_delay():
            await asyncio.sleep(0.05)
            consumer.stop()

        await asyncio.gather(
            consumer.start_consuming("file-events"),
            stop_after_delay(),
        )

        handler.assert_called_once_with(event)
        assert consumer.events_processed == 1

    @pytest.mark.asyncio
    async def test_start_consuming_uses_custom_group(self, mock_manager: MagicMock):
        """Test that start_consuming uses a custom group name."""
        mock_manager.read_group.return_value = []

        consumer = EventConsumer(stream_manager=mock_manager)

        async def stop_quickly():
            await asyncio.sleep(0.02)
            consumer.stop()

        await asyncio.gather(
            consumer.start_consuming("file-events", group_name="custom-grp"),
            stop_quickly(),
        )

        mock_manager.create_consumer_group.assert_called_once_with("file-events", "custom-grp")

    @pytest.mark.asyncio
    async def test_start_consuming_uses_default_group(self, mock_manager: MagicMock):
        """Test that start_consuming uses the config default group."""
        mock_manager.read_group.return_value = []

        config = EventConfig(consumer_group="my-default-group")
        consumer = EventConsumer(config=config, stream_manager=mock_manager)

        async def stop_quickly():
            await asyncio.sleep(0.02)
            consumer.stop()

        await asyncio.gather(
            consumer.start_consuming("file-events"),
            stop_quickly(),
        )

        mock_manager.create_consumer_group.assert_called_once_with(
            "file-events", "my-default-group"
        )


@pytest.mark.unit
class TestEventConsumerConnectionLifecycle:
    """Tests for connect/disconnect methods."""

    def test_connect_delegates_to_manager(self, consumer: EventConsumer, mock_manager: MagicMock):
        """Test that connect delegates to the stream manager."""
        result = consumer.connect()
        assert result is True
        mock_manager.connect.assert_called_once_with(None)

    def test_connect_with_url(self, consumer: EventConsumer, mock_manager: MagicMock):
        """Test connect passes URL to stream manager."""
        consumer.connect("redis://custom:6380")
        mock_manager.connect.assert_called_once_with("redis://custom:6380")

    def test_disconnect_stops_and_disconnects(self, mock_manager: MagicMock):
        """Test that disconnect stops consuming and disconnects."""
        consumer = EventConsumer(stream_manager=mock_manager)
        consumer._running = True
        consumer.disconnect()

        assert consumer.is_running is False
        mock_manager.disconnect.assert_called_once()


@pytest.mark.unit
class TestEventConsumerContextManager:
    """Tests for context manager protocol."""

    def test_context_manager(self, mock_manager: MagicMock):
        """Test using consumer as context manager."""
        with EventConsumer(stream_manager=mock_manager) as c:
            assert c.is_connected is True

        mock_manager.disconnect.assert_called_once()

    def test_disconnect_stops_consuming(self, mock_manager: MagicMock):
        """Test that disconnect also stops consuming."""
        consumer = EventConsumer(stream_manager=mock_manager)
        consumer._running = True
        consumer.disconnect()

        assert consumer.is_running is False
        mock_manager.disconnect.assert_called_once()

    def test_repr_after_processing(self, consumer: EventConsumer, mock_manager: MagicMock):
        """Test repr reflects handler and processed counts."""
        consumer.register_handler(EventType.FILE_CREATED, MagicMock())
        result = repr(consumer)
        assert "handlers=1" in result
