"""Redis Streams event system for the file organizer.

Provides event-driven architecture support using Redis Streams
for publishing and consuming file organization events, with a
pub/sub layer for topic-based routing, middleware support,
event replay, monitoring, audit logging, service bus, service
discovery, and health checking capabilities.

Example:
    >>> from file_organizer.events import EventPublisher, EventType
    >>> publisher = EventPublisher()
    >>> publisher.connect()
    >>> publisher.publish_file_event(
    ...     EventType.FILE_CREATED, "/path/to/file.txt"
    ... )

    >>> from file_organizer.events import PubSubManager
    >>> pubsub = PubSubManager()
    >>> pubsub.connect()
    >>> pubsub.subscribe("file.*", lambda data: print(data))
    >>> pubsub.publish("file.created", {"path": "/tmp/hello.txt"})

    >>> from file_organizer.events import ServiceBus
    >>> bus = ServiceBus(name="gateway")
    >>> bus.register_service("echo", lambda req: {"echo": req.payload})
"""

from __future__ import annotations

from file_organizer.events.audit import AuditEntry, AuditFilter, AuditLogger
from file_organizer.events.config import EventConfig
from file_organizer.events.consumer import EventConsumer
from file_organizer.events.discovery import ServiceDiscovery, ServiceInfo
from file_organizer.events.health import HealthChecker, HealthStatus, ServiceHealth
from file_organizer.events.middleware import (
    LoggingMiddleware,
    MetricsMiddleware,
    MiddlewarePipeline,
    RetryMiddleware,
)
from file_organizer.events.monitor import ConsumerLag, EventMonitor, StreamStats
from file_organizer.events.publisher import EventPublisher
from file_organizer.events.pubsub import PubSubManager
from file_organizer.events.replay import EventReplayManager, ReplayConfig
from file_organizer.events.service_bus import ServiceBus, ServiceRequest, ServiceResponse
from file_organizer.events.stream import Event, RedisStreamManager
from file_organizer.events.subscription import Subscription, SubscriptionRegistry
from file_organizer.events.types import EventType, FileEvent, ScanEvent

__all__ = [
    "AuditEntry",
    "AuditFilter",
    "AuditLogger",
    "ConsumerLag",
    "Event",
    "EventConfig",
    "EventConsumer",
    "EventMonitor",
    "EventPublisher",
    "EventReplayManager",
    "EventType",
    "FileEvent",
    "HealthChecker",
    "HealthStatus",
    "LoggingMiddleware",
    "MetricsMiddleware",
    "MiddlewarePipeline",
    "PubSubManager",
    "RedisStreamManager",
    "ReplayConfig",
    "RetryMiddleware",
    "ScanEvent",
    "ServiceBus",
    "ServiceDiscovery",
    "ServiceHealth",
    "ServiceInfo",
    "ServiceRequest",
    "ServiceResponse",
    "StreamStats",
    "Subscription",
    "SubscriptionRegistry",
]
