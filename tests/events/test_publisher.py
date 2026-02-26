"""
Unit tests for EventPublisher.

Tests publishing file events and scan events through the high-level
publisher API. All tests mock the underlying RedisStreamManager.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.events.config import EventConfig
from file_organizer.events.publisher import EventPublisher
from file_organizer.events.stream import RedisStreamManager
from file_organizer.events.types import EventType


@pytest.fixture
def mock_manager() -> MagicMock:
    """Create a mock RedisStreamManager."""
    manager = MagicMock(spec=RedisStreamManager)
    manager.is_connected = True
    manager.connect.return_value = True
    manager.publish.return_value = "1700000000000-0"
    return manager


@pytest.fixture
def publisher(mock_manager: MagicMock) -> EventPublisher:
    """Create an EventPublisher with a mocked stream manager."""
    return EventPublisher(stream_manager=mock_manager)


class TestEventPublisherInit:
    """Tests for EventPublisher initialization."""

    def test_default_init(self):
        """Test initialization with defaults."""
        pub = EventPublisher()
        assert pub.event_count == 0
        assert pub.is_connected is False

    def test_init_with_config(self):
        """Test initialization with custom config."""
        config = EventConfig(redis_url="redis://custom:6380/1")
        pub = EventPublisher(config=config)
        assert pub.event_count == 0

    def test_init_with_manager(self, mock_manager: MagicMock):
        """Test initialization with a pre-configured manager."""
        pub = EventPublisher(stream_manager=mock_manager)
        assert pub.is_connected is True

    def test_repr(self, publisher: EventPublisher):
        """Test string representation."""
        result = repr(publisher)
        assert "EventPublisher" in result
        assert "events_published=0" in result


class TestEventPublisherConnect:
    """Tests for connect/disconnect lifecycle."""

    def test_connect(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test connecting to Redis."""
        result = publisher.connect()
        assert result is True
        mock_manager.connect.assert_called_once_with(None)

    def test_connect_with_url(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test connecting with a custom URL."""
        publisher.connect("redis://other:6380")
        mock_manager.connect.assert_called_once_with("redis://other:6380")

    def test_disconnect(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test disconnecting."""
        publisher.disconnect()
        mock_manager.disconnect.assert_called_once()


class TestEventPublisherFileEvents:
    """Tests for publishing file events."""

    def test_publish_file_created(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test publishing a FILE_CREATED event."""
        result = publisher.publish_file_event(EventType.FILE_CREATED, "/path/to/file.txt")

        assert result == "1700000000000-0"
        assert publisher.event_count == 1
        mock_manager.publish.assert_called_once()

        call_args = mock_manager.publish.call_args
        assert call_args.kwargs["stream_name"] == "file-events"
        event_data = call_args.kwargs["event_data"]
        assert event_data["event_type"] == "file.created"
        assert event_data["file_path"] == "/path/to/file.txt"

    def test_publish_file_modified_with_metadata(
        self, publisher: EventPublisher, mock_manager: MagicMock
    ):
        """Test publishing a FILE_MODIFIED event with metadata."""
        metadata = {"size": 1024, "mime_type": "text/plain"}
        result = publisher.publish_file_event(
            EventType.FILE_MODIFIED, "/path/to/file.txt", metadata
        )

        assert result == "1700000000000-0"
        call_args = mock_manager.publish.call_args
        event_data = call_args.kwargs["event_data"]
        assert event_data["event_type"] == "file.modified"
        assert '"size": 1024' in event_data["metadata"]

    def test_publish_file_deleted(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test publishing a FILE_DELETED event."""
        result = publisher.publish_file_event(EventType.FILE_DELETED, "/path/to/removed.txt")
        assert result is not None
        call_args = mock_manager.publish.call_args
        assert call_args.kwargs["event_data"]["event_type"] == "file.deleted"

    def test_publish_file_organized(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test publishing a FILE_ORGANIZED event."""
        metadata = {"destination": "/organized/docs/report.txt"}
        result = publisher.publish_file_event(
            EventType.FILE_ORGANIZED, "/path/to/report.txt", metadata
        )
        assert result is not None
        call_args = mock_manager.publish.call_args
        assert call_args.kwargs["event_data"]["event_type"] == "file.organized"

    def test_publish_file_event_when_disconnected(self, mock_manager: MagicMock):
        """Test that publishing when disconnected returns None."""
        mock_manager.is_connected = False
        mock_manager.publish.return_value = None
        publisher = EventPublisher(stream_manager=mock_manager)

        result = publisher.publish_file_event(EventType.FILE_CREATED, "/path/to/file.txt")
        assert result is None
        assert publisher.event_count == 0

    def test_event_count_increments(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test that event count increments on successful publish."""
        publisher.publish_file_event(EventType.FILE_CREATED, "/a.txt")
        publisher.publish_file_event(EventType.FILE_MODIFIED, "/b.txt")
        publisher.publish_file_event(EventType.FILE_DELETED, "/c.txt")

        assert publisher.event_count == 3

    def test_publish_file_event_default_metadata(
        self, publisher: EventPublisher, mock_manager: MagicMock
    ):
        """Test that default metadata is an empty dict when not provided."""
        publisher.publish_file_event(EventType.FILE_CREATED, "/test.txt")

        call_args = mock_manager.publish.call_args
        event_data = call_args.kwargs["event_data"]
        assert event_data["metadata"] == "{}"

    def test_publish_file_event_contains_timestamp(
        self, publisher: EventPublisher, mock_manager: MagicMock
    ):
        """Test that published file events contain a timestamp."""
        publisher.publish_file_event(EventType.FILE_CREATED, "/test.txt")

        call_args = mock_manager.publish.call_args
        event_data = call_args.kwargs["event_data"]
        assert "timestamp" in event_data


class TestEventPublisherScanEvents:
    """Tests for publishing scan events."""

    def test_publish_scan_started(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test publishing a scan started event."""
        result = publisher.publish_scan_event("scan-001", "started")

        assert result == "1700000000000-0"
        assert publisher.event_count == 1
        call_args = mock_manager.publish.call_args
        assert call_args.kwargs["stream_name"] == "scan-events"
        event_data = call_args.kwargs["event_data"]
        assert event_data["scan_id"] == "scan-001"
        assert event_data["status"] == "started"

    def test_publish_scan_completed_with_stats(
        self, publisher: EventPublisher, mock_manager: MagicMock
    ):
        """Test publishing a scan completed event with stats."""
        stats = {"files_found": 42, "errors": 0, "duration_ms": 1500}
        result = publisher.publish_scan_event("scan-002", "completed", stats)

        assert result is not None
        call_args = mock_manager.publish.call_args
        event_data = call_args.kwargs["event_data"]
        assert event_data["status"] == "completed"
        assert '"files_found": 42' in event_data["stats"]

    def test_publish_scan_failed(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test publishing a scan failed event."""
        stats = {"error_message": "Permission denied"}
        result = publisher.publish_scan_event("scan-003", "failed", stats)
        assert result is not None

    def test_publish_scan_event_when_disconnected(self, mock_manager: MagicMock):
        """Test that publishing a scan event when Redis returns None does not increment count."""
        mock_manager.publish.return_value = None
        publisher = EventPublisher(stream_manager=mock_manager)

        result = publisher.publish_scan_event("scan-x", "started")

        assert result is None
        assert publisher.event_count == 0

    def test_publish_scan_event_default_stats(
        self, publisher: EventPublisher, mock_manager: MagicMock
    ):
        """Test that default stats is an empty dict when not provided."""
        publisher.publish_scan_event("scan-y", "completed")

        call_args = mock_manager.publish.call_args
        event_data = call_args.kwargs["event_data"]
        assert event_data["stats"] == "{}"

    def test_publish_scan_event_contains_timestamp(
        self, publisher: EventPublisher, mock_manager: MagicMock
    ):
        """Test that published scan events contain a timestamp."""
        publisher.publish_scan_event("s1", "started")

        call_args = mock_manager.publish.call_args
        event_data = call_args.kwargs["event_data"]
        assert "timestamp" in event_data


class TestEventPublisherContextManager:
    """Tests for context manager protocol."""

    def test_context_manager(self, mock_manager: MagicMock):
        """Test using publisher as context manager."""
        with EventPublisher(stream_manager=mock_manager) as pub:
            assert pub.is_connected is True
            pub.publish_file_event(EventType.FILE_CREATED, "/a.txt")

        mock_manager.disconnect.assert_called_once()


class TestEventPublisherEdgeCases:
    """Additional edge case tests for EventPublisher."""

    def test_repr_after_publishing(self, publisher: EventPublisher, mock_manager: MagicMock):
        """Test repr reflects updated event count."""
        publisher.publish_file_event(EventType.FILE_CREATED, "/a.txt")
        result = repr(publisher)
        assert "events_published=1" in result

    def test_stream_constants(self):
        """Test that file and scan stream names are defined."""
        assert EventPublisher.FILE_STREAM == "file-events"
        assert EventPublisher.SCAN_STREAM == "scan-events"

    def test_mixed_event_types_increment_count(
        self, publisher: EventPublisher, mock_manager: MagicMock
    ):
        """Test that file and scan events both increment the same counter."""
        publisher.publish_file_event(EventType.FILE_CREATED, "/a.txt")
        publisher.publish_scan_event("scan-1", "started")
        publisher.publish_file_event(EventType.FILE_DELETED, "/b.txt")

        assert publisher.event_count == 3
