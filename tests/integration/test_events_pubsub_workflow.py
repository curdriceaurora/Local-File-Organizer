"""Integration coverage for event publisher/pubsub/service-bus workflows."""

from __future__ import annotations

from typing import Any

import pytest

from file_organizer.events.middleware import MiddlewarePipeline
from file_organizer.events.publisher import EventPublisher
from file_organizer.events.pubsub import PubSubManager
from file_organizer.events.service_bus import ServiceBus
from file_organizer.events.types import EventType

pytestmark = pytest.mark.integration


class _FakeStreamManager:
    def __init__(self) -> None:
        self.is_connected = False
        self.published: list[tuple[str, dict[str, Any]]] = []

    def connect(self, redis_url: str | None = None) -> bool:
        self.is_connected = True
        return True

    def disconnect(self) -> None:
        self.is_connected = False

    def publish(self, stream_name: str, event_data: dict[str, Any]) -> str:
        self.published.append((stream_name, event_data))
        return f"id-{len(self.published)}"


class _CancelPublishMiddleware:
    def before_publish(self, topic: str, data: dict[str, Any]) -> dict[str, Any] | None:
        if topic == "file.cancelled":
            return None
        payload = dict(data)
        payload["seen_by_before_publish"] = True
        return payload

    def after_publish(self, topic: str, data: dict[str, Any], message_id: str | None) -> None:
        return None

    def before_consume(self, topic: str, data: dict[str, Any]) -> dict[str, Any] | None:
        payload = dict(data)
        payload["seen_by_before_consume"] = True
        return payload

    def after_consume(
        self,
        topic: str,
        data: dict[str, Any],
        error: Exception | None,
    ) -> None:
        return None


def test_event_publisher_and_pubsub_dispatch_work_together() -> None:
    stream_manager = _FakeStreamManager()
    publisher = EventPublisher(stream_manager=stream_manager)

    assert publisher.connect() is True
    file_id = publisher.publish_file_event(
        EventType.FILE_CREATED,
        "/tmp/example.txt",
        {"size": 12},
    )
    scan_id = publisher.publish_scan_event("scan-1", "completed", {"processed": 3})
    assert file_id == "id-1"
    assert scan_id == "id-2"
    assert publisher.event_count == 2
    assert stream_manager.published[0][0] == EventPublisher.FILE_STREAM
    assert stream_manager.published[1][0] == EventPublisher.SCAN_STREAM
    publisher.disconnect()
    assert publisher.is_connected is False

    pipeline = MiddlewarePipeline()
    pipeline.add(_CancelPublishMiddleware())
    pubsub = PubSubManager(stream_manager=stream_manager, pipeline=pipeline)

    received: list[dict[str, Any]] = []

    def handler(data: dict[str, Any]) -> None:
        received.append(data)

    sub = pubsub.subscribe("file.*", handler, filter_fn=lambda data: data.get("ok") is True)
    message_id = pubsub.publish("file.created", {"ok": True, "path": "/tmp/example.txt"})
    assert message_id == "id-3"
    assert received[0]["seen_by_before_publish"] is True
    assert received[0]["seen_by_before_consume"] is True

    pubsub.registry.deactivate("file.*", handler)
    assert sub.active is False
    pubsub.publish("file.created", {"ok": True, "path": "/tmp/ignored.txt"})
    assert len(received) == 1

    pubsub.registry.activate("file.*", handler)
    cancelled = pubsub.publish("file.cancelled", {"ok": True})
    assert cancelled is None
    assert len(received) == 1

    assert pubsub.unsubscribe("file.*", handler) is True
    pubsub.publish("file.created", {"ok": True, "path": "/tmp/after-unsubscribe.txt"})
    assert len(received) == 1


def test_service_bus_request_response_and_broadcast_smoke() -> None:
    stream_manager = _FakeStreamManager()
    pubsub = PubSubManager(stream_manager=stream_manager)
    bus = ServiceBus(name="gateway", pubsub=pubsub)

    bus.register_service("echo", lambda request: {"echo": request.payload["message"]})
    bus.register_service("upper", lambda request: {"echo": request.payload["message"].upper()})

    success = bus.send_request("echo", "ping", {"message": "hello"})
    assert success.success is True
    assert success.data == {"echo": "hello"}

    missing = bus.send_request("missing", "ping", {"message": "hello"})
    assert missing.success is False
    assert "not found" in (missing.error or "")

    responses = bus.broadcast("announce", {"message": "hey"})
    assert responses["echo"].success is True
    assert responses["upper"].data["echo"] == "HEY"

    published_topics = [topic for topic, _ in stream_manager.published]
    assert "pubsub:service:request:echo:ping" in published_topics
    assert "pubsub:service:response:echo:ping" in published_topics
