"""Integration tests for the events package.

Covers EventConfig, EventType, FileEvent, ScanEvent, Subscription, SubscriptionRegistry,
AuditEntry/AuditLogger, ServiceRequest/ServiceResponse, MiddlewarePipeline,
and EventConsumer handler registration (no Redis required).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# EventConfig
# ---------------------------------------------------------------------------


class TestEventConfig:
    """Tests for EventConfig defaults and stream name building."""

    def test_default_values(self) -> None:
        """Verify EventConfig initialises with expected default field values."""
        from file_organizer.events.config import EventConfig

        cfg = EventConfig()
        assert cfg.redis_url == "redis://localhost:6379/0"
        assert cfg.stream_prefix == "fileorg"
        assert cfg.consumer_group == "file-organizer"
        assert cfg.max_retries == 3
        assert cfg.retry_delay == 1.0
        assert cfg.block_ms == 5000
        assert cfg.batch_size == 10

    def test_get_stream_name(self) -> None:
        """Verify stream name is built as prefix:suffix."""
        from file_organizer.events.config import EventConfig

        cfg = EventConfig(stream_prefix="myapp")
        name = cfg.get_stream_name("events")
        assert name == "myapp:events"

    def test_custom_config(self) -> None:
        """Verify custom redis_url and batch_size are stored correctly."""
        from file_organizer.events.config import EventConfig

        cfg = EventConfig(redis_url="redis://remote:6379/1", batch_size=25)
        assert cfg.redis_url == "redis://remote:6379/1"
        assert cfg.batch_size == 25

    def test_none_max_stream_length(self) -> None:
        """Verify max_stream_length can be set to None."""
        from file_organizer.events.config import EventConfig

        cfg = EventConfig(max_stream_length=None)
        assert cfg.max_stream_length is None


# ---------------------------------------------------------------------------
# EventType
# ---------------------------------------------------------------------------


class TestEventType:
    """Tests for EventType enum values."""

    def test_all_event_types_exist(self) -> None:
        """Verify all expected event type values are present in the enum."""
        from file_organizer.events.types import EventType

        expected = {
            "file.created",
            "file.modified",
            "file.deleted",
            "file.organized",
            "scan.started",
            "scan.completed",
            "error",
        }
        actual = {et.value for et in EventType}
        assert actual == expected

    def test_event_type_values(self) -> None:
        """Verify specific EventType members map to their expected string values."""
        from file_organizer.events.types import EventType

        assert EventType.FILE_CREATED.value == "file.created"
        assert EventType.SCAN_COMPLETED.value == "scan.completed"
        assert EventType.ERROR.value == "error"


# ---------------------------------------------------------------------------
# FileEvent
# ---------------------------------------------------------------------------


class TestFileEvent:
    """Tests for FileEvent serialization and deserialization."""

    def test_to_dict_contains_all_fields(self) -> None:
        """Verify to_dict includes event_type, file_path, metadata, and timestamp."""
        from file_organizer.events.types import EventType, FileEvent

        event = FileEvent(
            event_type=EventType.FILE_CREATED,
            file_path="docs/doc.pdf",
            metadata={"size": 1024},
        )
        d = event.to_dict()
        assert d["event_type"] == "file.created"
        assert d["file_path"] == "docs/doc.pdf"
        assert "metadata" in d
        assert "timestamp" in d

    def test_roundtrip(self) -> None:
        """Verify from_dict restores all fields set during construction."""
        from file_organizer.events.types import EventType, FileEvent

        ts = datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC)
        event = FileEvent(
            event_type=EventType.FILE_MODIFIED,
            file_path="reports/report.xlsx",
            metadata={"source": "watcher"},
            timestamp=ts,
        )
        d = event.to_dict()
        restored = FileEvent.from_dict(d)
        assert restored.event_type == EventType.FILE_MODIFIED
        assert restored.file_path == "reports/report.xlsx"
        assert restored.metadata == {"source": "watcher"}
        assert restored.timestamp == ts

    def test_from_dict_invalid_event_type_raises(self) -> None:
        """Verify from_dict raises ValueError for an unrecognised event_type string."""
        from file_organizer.events.types import FileEvent

        d = {
            "event_type": "not.real",
            "file_path": "/x.txt",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        with pytest.raises(ValueError):
            FileEvent.from_dict(d)

    def test_from_dict_missing_required_field_raises(self) -> None:
        """Verify from_dict raises KeyError when event_type is absent."""
        from file_organizer.events.types import FileEvent

        with pytest.raises(KeyError):
            FileEvent.from_dict({"file_path": "/x.txt"})

    def test_default_empty_metadata(self) -> None:
        """Verify metadata defaults to an empty dict when not provided."""
        from file_organizer.events.types import EventType, FileEvent

        event = FileEvent(event_type=EventType.FILE_DELETED, file_path="/f.txt")
        assert event.metadata == {}

    def test_metadata_preserved_through_roundtrip(self) -> None:
        """Verify nested metadata is preserved after to_dict/from_dict round-trip."""
        from file_organizer.events.types import EventType, FileEvent

        meta = {"key": "value", "nested": {"a": 1}}
        event = FileEvent(
            event_type=EventType.FILE_ORGANIZED,
            file_path="/f.txt",
            metadata=meta,
            timestamp=datetime.now(UTC),
        )
        d = event.to_dict()
        restored = FileEvent.from_dict(d)
        assert restored.metadata == meta


# ---------------------------------------------------------------------------
# ScanEvent
# ---------------------------------------------------------------------------


class TestScanEvent:
    """Tests for ScanEvent serialization."""

    def test_to_dict_fields(self) -> None:
        """Verify to_dict includes scan_id, status, stats, and timestamp."""
        from file_organizer.events.types import ScanEvent

        event = ScanEvent(
            scan_id="scan-001",
            status="started",
            stats={"files_found": 42},
        )
        d = event.to_dict()
        assert d["scan_id"] == "scan-001"
        assert d["status"] == "started"
        assert "stats" in d
        assert "timestamp" in d

    def test_roundtrip(self) -> None:
        """Verify from_dict restores all ScanEvent fields correctly."""
        from file_organizer.events.types import ScanEvent

        ts = datetime(2025, 1, 1, 0, 0, 0, tzinfo=UTC)
        event = ScanEvent(
            scan_id="scan-rt",
            status="completed",
            stats={"processed": 100, "errors": 2},
            timestamp=ts,
        )
        d = event.to_dict()
        restored = ScanEvent.from_dict(d)
        assert restored.scan_id == "scan-rt"
        assert restored.status == "completed"
        assert restored.stats == {"processed": 100, "errors": 2}
        assert restored.timestamp == ts

    def test_empty_stats_default(self) -> None:
        """Verify stats defaults to an empty dict and survives a round-trip."""
        from file_organizer.events.types import ScanEvent

        event = ScanEvent(scan_id="s", status="started", timestamp=datetime.now(UTC))
        d = event.to_dict()
        restored = ScanEvent.from_dict(d)
        assert restored.stats == {}


# ---------------------------------------------------------------------------
# Subscription and SubscriptionRegistry
# ---------------------------------------------------------------------------


class TestSubscription:
    """Tests for Subscription topic matching and filter functions."""

    def test_exact_topic_match(self) -> None:
        """Verify matches_topic returns True only for the exact topic string."""
        from file_organizer.events.subscription import Subscription

        sub = Subscription(topic="file.created", handler=lambda d: None)
        assert sub.matches_topic("file.created") is True
        assert sub.matches_topic("file.deleted") is False

    def test_single_wildcard_match(self) -> None:
        """Verify single wildcard (*) matches one path segment only."""
        from file_organizer.events.subscription import Subscription

        sub = Subscription(topic="file.*", handler=lambda d: None)
        assert sub.matches_topic("file.created") is True
        assert sub.matches_topic("file.deleted") is True
        assert sub.matches_topic("file.a.b") is False
        assert sub.matches_topic("scan.started") is False

    def test_double_wildcard_match(self) -> None:
        """Verify double wildcard (**) matches any number of path segments."""
        from file_organizer.events.subscription import Subscription

        sub = Subscription(topic="file.**", handler=lambda d: None)
        assert sub.matches_topic("file.created") is True
        assert sub.matches_topic("file.a.b") is True
        assert sub.matches_topic("scan.started") is False

    def test_filter_function_blocks(self) -> None:
        """Verify passes_filter delegates to the provided filter_fn."""
        from file_organizer.events.subscription import Subscription

        sub = Subscription(
            topic="file.created",
            handler=lambda d: None,
            filter_fn=lambda d: d.get("important") is True,
        )
        assert sub.passes_filter({"important": True}) is True
        assert sub.passes_filter({"important": False}) is False
        assert sub.passes_filter({}) is False

    def test_no_filter_always_passes(self) -> None:
        """Verify passes_filter returns True for any data when no filter_fn is set."""
        from file_organizer.events.subscription import Subscription

        sub = Subscription(topic="x", handler=lambda d: None)
        assert sub.passes_filter({}) is True
        assert sub.passes_filter({"any": "data"}) is True

    def test_filter_exception_returns_false(self) -> None:
        """Verify passes_filter returns False when filter_fn raises an exception."""
        from file_organizer.events.subscription import Subscription

        def bad_filter(data: dict) -> bool:
            raise RuntimeError("boom")

        sub = Subscription(topic="x", handler=lambda d: None, filter_fn=bad_filter)
        assert sub.passes_filter({}) is False


class TestSubscriptionRegistry:
    """Tests for SubscriptionRegistry management."""

    def test_register_and_count(self) -> None:
        """Verify count increments when a subscription is added."""
        from file_organizer.events.subscription import SubscriptionRegistry

        registry = SubscriptionRegistry()
        assert registry.count == 0

        def handler(d: object) -> None:
            pass

        registry.add("file.created", handler)
        assert registry.count == 1

    def test_get_for_topic_returns_matching(self) -> None:
        """Verify get_for_topic returns only subscriptions matching the given topic."""
        from file_organizer.events.subscription import SubscriptionRegistry

        registry = SubscriptionRegistry()

        def h1(d: object) -> None:
            pass

        def h2(d: object) -> None:
            pass

        registry.add("file.created", h1)
        registry.add("file.deleted", h2)

        matching = registry.get_for_topic("file.created")
        assert len(matching) == 1
        assert matching[0].topic == "file.created"

    def test_inactive_subscription_not_returned(self) -> None:
        """Verify deactivated subscriptions are excluded from get_for_topic results."""
        from file_organizer.events.subscription import SubscriptionRegistry

        registry = SubscriptionRegistry()

        def handler(d: object) -> None:
            pass

        registry.add("file.created", handler)
        registry.deactivate("file.created", handler)

        matching = registry.get_for_topic("file.created")
        assert len(matching) == 0

    def test_get_active_excludes_deactivated(self) -> None:
        """Verify get_active omits deactivated subscriptions."""
        from file_organizer.events.subscription import SubscriptionRegistry

        registry = SubscriptionRegistry()

        def ha(d: object) -> None:
            pass

        def hb(d: object) -> None:
            pass

        registry.add("a", ha)
        registry.add("b", hb)
        registry.deactivate("b", hb)

        active = registry.get_active()
        assert len(active) == 1
        assert active[0].topic == "a"

    def test_repr(self) -> None:
        """Verify repr includes the SubscriptionRegistry class name."""
        from file_organizer.events.subscription import SubscriptionRegistry

        registry = SubscriptionRegistry()
        r = repr(registry)
        assert "SubscriptionRegistry" in r

    def test_len(self) -> None:
        """Verify len(registry) reflects the number of registered subscriptions."""
        from file_organizer.events.subscription import SubscriptionRegistry

        registry = SubscriptionRegistry()

        def handler(d: object) -> None:
            pass

        registry.add("x", handler)
        assert len(registry) == 1


# ---------------------------------------------------------------------------
# AuditEntry and AuditLogger
# ---------------------------------------------------------------------------


class TestAuditEntry:
    """Tests for AuditEntry serialization."""

    def test_to_dict_fields(self) -> None:
        """Verify to_dict includes all expected AuditEntry fields."""
        from file_organizer.events.audit import AuditEntry

        ts = datetime(2025, 3, 15, 10, 0, 0, tzinfo=UTC)
        entry = AuditEntry(
            timestamp=ts,
            event_id="msg-001",
            stream="fileorg:events",
            action="published",
            metadata={"topic": "file.created"},
        )
        d = entry.to_dict()
        assert d["event_id"] == "msg-001"
        assert d["stream"] == "fileorg:events"
        assert d["action"] == "published"
        assert d["metadata"]["topic"] == "file.created"
        assert "2025-03-15" in d["timestamp"]

    def test_roundtrip(self) -> None:
        """Verify from_dict restores all AuditEntry fields correctly."""
        from file_organizer.events.audit import AuditEntry

        ts = datetime(2025, 6, 1, 0, 0, 0, tzinfo=UTC)
        entry = AuditEntry(
            timestamp=ts,
            event_id="e-123",
            stream="s1",
            action="consumed",
        )
        d = entry.to_dict()
        restored = AuditEntry.from_dict(d)
        assert restored.event_id == "e-123"
        assert restored.stream == "s1"
        assert restored.action == "consumed"
        assert restored.timestamp == ts


def _make_event(event_id: str = "msg-001", stream: str = "fileorg:events") -> object:
    from file_organizer.events.stream import Event

    return Event(id=event_id, stream=stream, data={"path": "/f.txt"})


class TestAuditLogger:
    """Tests for AuditLogger file-based persistence."""

    def test_log_event_and_count(self, tmp_path: Path) -> None:
        """Verify logging one event increments the entry count to 1."""
        from file_organizer.events.audit import AuditLogger

        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_file)
        entry = logger.log_event(_make_event("e-001"), "published")
        assert entry.event_id == "e-001"
        assert logger.get_entry_count() == 1

    def test_multiple_events(self, tmp_path: Path) -> None:
        """Verify logging five events yields a count of 5."""
        from file_organizer.events.audit import AuditLogger

        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_file)
        for i in range(5):
            logger.log_event(_make_event(f"e-{i:03d}"), "published")
        assert logger.get_entry_count() == 5

    def test_clear_resets_count(self, tmp_path: Path) -> None:
        """Verify clear() resets the entry count to zero."""
        from file_organizer.events.audit import AuditLogger

        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_file)
        logger.log_event(_make_event(), "published")
        logger.clear()
        assert logger.get_entry_count() == 0

    def test_get_entries_returns_logged_entries(self, tmp_path: Path) -> None:
        """Verify query_audit_log returns all logged entries with correct actions."""
        from file_organizer.events.audit import AuditLogger

        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_file)
        logger.log_event(_make_event("e-pub"), "published")
        logger.log_event(_make_event("e-con"), "consumed")

        entries = logger.query_audit_log()
        assert len(entries) == 2
        actions = {e.action for e in entries}
        assert "published" in actions
        assert "consumed" in actions

    def test_get_entries_with_action_filter(self, tmp_path: Path) -> None:
        """Verify query_audit_log with an action filter returns only matching entries."""
        from file_organizer.events.audit import AuditFilter, AuditLogger

        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_file)
        logger.log_event(_make_event("e1"), "published")
        logger.log_event(_make_event("e2"), "consumed")
        logger.log_event(_make_event("e3"), "published")

        filt = AuditFilter(action="published")
        filtered = logger.query_audit_log(filters=filt)
        assert len(filtered) == 2
        assert all(e.action == "published" for e in filtered)

    def test_empty_log_returns_zero_count(self, tmp_path: Path) -> None:
        """Verify get_entry_count returns 0 when no events have been logged."""
        from file_organizer.events.audit import AuditLogger

        log_file = tmp_path / "nonexistent.jsonl"
        logger = AuditLogger(log_path=log_file)
        assert logger.get_entry_count() == 0

    def test_repr(self, tmp_path: Path) -> None:
        """Verify repr includes the AuditLogger class name."""
        from file_organizer.events.audit import AuditLogger

        log_file = tmp_path / "audit.jsonl"
        logger = AuditLogger(log_path=log_file)
        r = repr(logger)
        assert "AuditLogger" in r


# ---------------------------------------------------------------------------
# MiddlewarePipeline
# ---------------------------------------------------------------------------


class TestMiddlewarePipeline:
    """Tests for the event middleware pipeline."""

    def test_pipeline_runs_before_publish(self) -> None:
        """Verify before_publish middleware is called and may mutate event data."""
        from file_organizer.events.middleware import MiddlewarePipeline

        calls: list[str] = []

        class TestMW:
            def before_publish(self, topic: str, data: dict) -> dict | None:
                calls.append(f"before:{topic}")
                return data

        pipeline = MiddlewarePipeline()
        pipeline.add(TestMW())
        result = pipeline.run_before_publish("file.created", {"path": "/f.txt"})
        assert result is not None
        assert "before:file.created" in calls

    def test_pipeline_before_publish_cancel(self) -> None:
        """Verify returning None from before_publish cancels the publish."""
        from file_organizer.events.middleware import MiddlewarePipeline

        second_called = False

        class CancelMW:
            def before_publish(self, topic: str, data: dict) -> dict | None:
                return None  # cancel

        class SecondMW:
            def before_publish(self, topic: str, data: dict) -> dict | None:
                nonlocal second_called
                second_called = True
                return data

        pipeline = MiddlewarePipeline()
        pipeline.add(CancelMW())
        pipeline.add(SecondMW())
        result = pipeline.run_before_publish("file.created", {"path": "/f.txt"})
        assert result is None
        assert second_called is False

    def test_pipeline_after_publish(self) -> None:
        """Verify after_publish middleware receives the message_id."""
        from file_organizer.events.middleware import MiddlewarePipeline

        after_calls: list[str] = []

        class AfterMW:
            def after_publish(self, topic: str, data: dict, message_id: str | None) -> None:
                after_calls.append(message_id or "none")

        pipeline = MiddlewarePipeline()
        pipeline.add(AfterMW())
        pipeline.run_after_publish("file.created", {}, "msg-001")
        assert "msg-001" in after_calls

    def test_empty_pipeline_passthrough(self) -> None:
        """Verify an empty pipeline returns event data unchanged."""
        from file_organizer.events.middleware import MiddlewarePipeline

        pipeline = MiddlewarePipeline()
        data = {"path": "/x.txt"}
        result = pipeline.run_before_publish("topic", data)
        assert result == data


# ---------------------------------------------------------------------------
# ServiceRequest / ServiceResponse
# ---------------------------------------------------------------------------


class TestServiceBusDataClasses:
    """Tests for ServiceRequest and ServiceResponse serialization."""

    def test_service_request_roundtrip(self) -> None:
        """Verify ServiceRequest to_dict includes all construction fields."""
        from file_organizer.events.service_bus import ServiceRequest

        ts = datetime(2025, 5, 1, 0, 0, 0, tzinfo=UTC)
        req = ServiceRequest(
            id="req-001",
            source="organizer",
            target="indexer",
            action="index_file",
            payload={"path": "/docs/report.pdf"},
            timestamp=ts,
        )
        d = req.to_dict()
        assert d["id"] == "req-001"
        assert d["source"] == "organizer"
        assert d["target"] == "indexer"
        assert d["action"] == "index_file"
        assert d["payload"]["path"] == "/docs/report.pdf"
        assert d["timestamp"] == ts.isoformat()

    def test_service_response_fields(self) -> None:
        """Verify a successful ServiceResponse carries the expected data and no error."""
        from file_organizer.events.service_bus import ServiceResponse

        resp = ServiceResponse(
            request_id="req-001",
            success=True,
            data={"indexed": 42},
        )
        assert resp.request_id == "req-001"
        assert resp.success is True
        assert resp.data["indexed"] == 42
        assert resp.error is None

    def test_service_response_failure(self) -> None:
        """Verify a failed ServiceResponse carries the error message."""
        from file_organizer.events.service_bus import ServiceResponse

        resp = ServiceResponse(
            request_id="req-002",
            success=False,
            error="File not found",
        )
        assert resp.request_id == "req-002"
        assert resp.success is False
        assert resp.error == "File not found"
        assert not resp.data


# ---------------------------------------------------------------------------
# EventConsumer (no Redis — test handler registration only)
# ---------------------------------------------------------------------------


class TestEventConsumerHandlers:
    """Tests for EventConsumer handler registration (no Redis connection)."""

    def test_register_handler(self) -> None:
        """Verify registering a handler increments registered_handlers count."""
        from unittest.mock import MagicMock

        from file_organizer.events.consumer import EventConsumer
        from file_organizer.events.types import EventType

        mock_manager = MagicMock()
        consumer = EventConsumer(stream_manager=mock_manager)

        def handler(event: object) -> None:
            pass

        consumer.register_handler(EventType.FILE_CREATED, handler)

        assert consumer.registered_handlers[EventType.FILE_CREATED.value] == 1

    def test_multiple_handlers_same_type(self) -> None:
        """Verify registering two handlers for the same event type yields count 2."""
        from unittest.mock import MagicMock

        from file_organizer.events.consumer import EventConsumer
        from file_organizer.events.types import EventType

        mock_manager = MagicMock()
        consumer = EventConsumer(stream_manager=mock_manager)
        consumer.register_handler(EventType.FILE_CREATED, lambda e: None)
        consumer.register_handler(EventType.FILE_CREATED, lambda e: None)

        assert consumer.registered_handlers[EventType.FILE_CREATED.value] == 2

    def test_consumer_not_running_initially(self) -> None:
        """Verify a newly created EventConsumer is not running."""
        from unittest.mock import MagicMock

        from file_organizer.events.consumer import EventConsumer

        mock_manager = MagicMock()
        consumer = EventConsumer(stream_manager=mock_manager)
        assert consumer.is_running is False

    def test_consumer_stores_name(self) -> None:
        """Verify consumer_name is stored and accessible via _consumer_name."""
        from unittest.mock import MagicMock

        from file_organizer.events.consumer import EventConsumer

        mock_manager = MagicMock()
        consumer = EventConsumer(stream_manager=mock_manager, consumer_name="worker-99")
        assert consumer._consumer_name == "worker-99"


# ---------------------------------------------------------------------------
# Health and Monitor (no Redis — test construction/config)
# ---------------------------------------------------------------------------


class TestHealthChecker:
    """Tests for HealthChecker configuration."""

    def test_construction_with_service_bus(self) -> None:
        """Verify HealthChecker stores the passed service bus as its internal bus."""
        from unittest.mock import MagicMock

        from file_organizer.events.health import HealthChecker

        mock_bus = MagicMock()
        checker = HealthChecker(service_bus=mock_bus)
        assert checker._bus is mock_bus

    def test_threshold_properties(self) -> None:
        """Verify degraded and unhealthy threshold properties reflect constructor args."""
        from unittest.mock import MagicMock

        from file_organizer.events.health import HealthChecker

        mock_bus = MagicMock()
        checker = HealthChecker(
            service_bus=mock_bus,
            degraded_threshold_ms=200.0,
            unhealthy_threshold_ms=1000.0,
        )
        assert checker.degraded_threshold_ms == 200.0
        assert checker.unhealthy_threshold_ms == 1000.0
