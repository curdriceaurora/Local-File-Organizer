"""
Unit tests for ServiceBus, ServiceRequest, and ServiceResponse.

Tests service registration, request/response lifecycle, broadcast,
error handling, timeout detection, and pubsub integration.
All Redis operations are mocked.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from file_organizer.events.pubsub import PubSubManager
from file_organizer.events.service_bus import (
    ServiceBus,
    ServiceRequest,
    ServiceResponse,
)
from file_organizer.events.stream import RedisStreamManager

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def mock_manager() -> MagicMock:
    """Create a mock RedisStreamManager."""
    manager = MagicMock(spec=RedisStreamManager)
    manager.is_connected = True
    manager.connect.return_value = True
    manager.publish.return_value = "1000000000-0"
    return manager


@pytest.fixture
def mock_pubsub(mock_manager: MagicMock) -> PubSubManager:
    """Create a PubSubManager with mocked stream manager."""
    return PubSubManager(stream_manager=mock_manager)


@pytest.fixture
def bus(mock_pubsub: PubSubManager) -> ServiceBus:
    """Create a ServiceBus with mocked pubsub."""
    return ServiceBus(name="test-bus", pubsub=mock_pubsub)


# ------------------------------------------------------------------
# ServiceRequest dataclass
# ------------------------------------------------------------------


class TestServiceRequest:
    """Tests for the ServiceRequest dataclass."""

    def test_creation(self) -> None:
        """ServiceRequest can be created with required fields."""
        req = ServiceRequest(
            id="req-1",
            source="gateway",
            target="classifier",
            action="classify",
        )
        assert req.id == "req-1"
        assert req.source == "gateway"
        assert req.target == "classifier"
        assert req.action == "classify"
        assert req.payload == {}
        assert req.timestamp is not None

    def test_creation_with_payload(self) -> None:
        """ServiceRequest accepts a payload dictionary."""
        req = ServiceRequest(
            id="req-2",
            source="gateway",
            target="classifier",
            action="classify",
            payload={"file": "test.txt"},
        )
        assert req.payload == {"file": "test.txt"}

    def test_to_dict(self) -> None:
        """to_dict serializes all fields."""
        req = ServiceRequest(
            id="req-3",
            source="a",
            target="b",
            action="ping",
            payload={"key": "value"},
        )
        d = req.to_dict()
        assert d["id"] == "req-3"
        assert d["source"] == "a"
        assert d["target"] == "b"
        assert d["action"] == "ping"
        assert d["payload"] == {"key": "value"}
        assert "timestamp" in d

    def test_frozen(self) -> None:
        """ServiceRequest is immutable."""
        req = ServiceRequest(id="r", source="a", target="b", action="c")
        with pytest.raises(AttributeError):
            req.id = "new"  # type: ignore[misc]

    def test_to_dict_timestamp_is_isoformat(self) -> None:
        """to_dict timestamp is an ISO 8601 string."""
        req = ServiceRequest(id="r", source="a", target="b", action="c")
        d = req.to_dict()
        # Should be parseable as ISO format
        assert "T" in d["timestamp"]


# ------------------------------------------------------------------
# ServiceResponse dataclass
# ------------------------------------------------------------------


class TestServiceResponse:
    """Tests for the ServiceResponse dataclass."""

    def test_success_response(self) -> None:
        """Successful response carries data and no error."""
        resp = ServiceResponse(
            request_id="req-1",
            success=True,
            data={"result": 42},
            duration_ms=1.5,
        )
        assert resp.success is True
        assert resp.data == {"result": 42}
        assert resp.error is None
        assert resp.duration_ms == 1.5

    def test_error_response(self) -> None:
        """Error response carries error string."""
        resp = ServiceResponse(
            request_id="req-2",
            success=False,
            error="not found",
        )
        assert resp.success is False
        assert resp.error == "not found"
        assert resp.data == {}

    def test_to_dict(self) -> None:
        """to_dict serializes all fields."""
        resp = ServiceResponse(
            request_id="r1",
            success=True,
            data={"k": "v"},
            duration_ms=2.0,
        )
        d = resp.to_dict()
        assert d["request_id"] == "r1"
        assert d["success"] is True
        assert d["data"] == {"k": "v"}
        assert d["duration_ms"] == 2.0

    def test_frozen(self) -> None:
        """ServiceResponse is immutable."""
        resp = ServiceResponse(request_id="r", success=True)
        with pytest.raises(AttributeError):
            resp.success = False  # type: ignore[misc]

    def test_default_duration_ms(self) -> None:
        """ServiceResponse defaults duration_ms to 0.0."""
        resp = ServiceResponse(request_id="r", success=True)
        assert resp.duration_ms == 0.0

    def test_to_dict_includes_none_error(self) -> None:
        """to_dict includes error field even when None."""
        resp = ServiceResponse(request_id="r", success=True)
        d = resp.to_dict()
        assert "error" in d
        assert d["error"] is None


# ------------------------------------------------------------------
# Service registration
# ------------------------------------------------------------------


class TestServiceRegistration:
    """Tests for service registration on the bus."""

    def test_register_service(self, bus: ServiceBus) -> None:
        """A service can be registered."""
        handler = MagicMock()
        bus.register_service("echo", handler)
        assert bus.has_service("echo")
        assert "echo" in bus.list_services()

    def test_register_duplicate_raises(self, bus: ServiceBus) -> None:
        """Registering a duplicate name raises ValueError."""
        bus.register_service("dup", MagicMock())
        with pytest.raises(ValueError, match="already registered"):
            bus.register_service("dup", MagicMock())

    def test_deregister_service(self, bus: ServiceBus) -> None:
        """A registered service can be removed."""
        bus.register_service("temp", MagicMock())
        assert bus.deregister_service("temp") is True
        assert bus.has_service("temp") is False

    def test_deregister_nonexistent(self, bus: ServiceBus) -> None:
        """Deregistering a nonexistent service returns False."""
        assert bus.deregister_service("ghost") is False

    def test_list_services_sorted(self, bus: ServiceBus) -> None:
        """list_services returns names in sorted order."""
        bus.register_service("zebra", MagicMock())
        bus.register_service("alpha", MagicMock())
        bus.register_service("middle", MagicMock())
        assert bus.list_services() == ["alpha", "middle", "zebra"]

    def test_services_property_is_copy(self, bus: ServiceBus) -> None:
        """services property returns a copy, not the internal dict."""
        bus.register_service("svc", MagicMock())
        snapshot = bus.services
        snapshot["injected"] = MagicMock()
        assert "injected" not in bus.services

    def test_has_service_nonexistent(self, bus: ServiceBus) -> None:
        """has_service returns False for unknown services."""
        assert bus.has_service("unknown") is False

    def test_register_and_deregister_cycle(self, bus: ServiceBus) -> None:
        """A service can be registered, deregistered, and re-registered."""
        handler = MagicMock()
        bus.register_service("cycle", handler)
        bus.deregister_service("cycle")
        bus.register_service("cycle", handler)
        assert bus.has_service("cycle")


# ------------------------------------------------------------------
# Request / Response
# ------------------------------------------------------------------


class TestSendRequest:
    """Tests for send_request."""

    def test_successful_request(self, bus: ServiceBus) -> None:
        """A successful handler returns a success response."""
        bus.register_service("echo", lambda req: {"echo": req.payload})
        resp = bus.send_request("echo", "ping", {"msg": "hi"})
        assert resp.success is True
        assert resp.data == {"echo": {"msg": "hi"}}
        assert resp.duration_ms >= 0
        assert bus.request_count == 1
        assert bus.error_count == 0

    def test_request_to_unknown_service(self, bus: ServiceBus) -> None:
        """Requesting an unknown service returns an error response."""
        resp = bus.send_request("ghost", "ping")
        assert resp.success is False
        assert "not found" in (resp.error or "")
        assert bus.error_count == 1

    def test_handler_exception_caught(self, bus: ServiceBus) -> None:
        """An exception in the handler produces an error response."""

        def boom(req: ServiceRequest) -> dict:
            raise RuntimeError("handler exploded")

        bus.register_service("bomb", boom)
        resp = bus.send_request("bomb", "detonate")
        assert resp.success is False
        assert "handler exploded" in (resp.error or "")
        assert resp.duration_ms >= 0
        assert bus.error_count == 1

    def test_handler_returning_non_dict(self, bus: ServiceBus) -> None:
        """Handler returning a non-dict produces empty data."""
        bus.register_service("noop", lambda req: "not a dict")
        resp = bus.send_request("noop", "run")
        assert resp.success is True
        assert resp.data == {}

    def test_request_publishes_events(self, bus: ServiceBus, mock_manager: MagicMock) -> None:
        """send_request publishes request and response events."""
        bus.register_service("svc", lambda req: {"ok": True})
        bus.send_request("svc", "act")
        # At least two publishes: request event + response event
        assert mock_manager.publish.call_count >= 2

    def test_request_with_default_payload(self, bus: ServiceBus) -> None:
        """Default payload is an empty dict."""
        bus.register_service("svc", lambda req: {"got": req.payload})
        resp = bus.send_request("svc", "act")
        assert resp.data == {"got": {}}

    def test_timeout_detection(self, bus: ServiceBus) -> None:
        """A slow handler triggers timeout error response."""

        def slow_handler(req: ServiceRequest) -> dict:
            time.sleep(0.05)
            return {"done": True}

        bus.register_service("slow", slow_handler)
        # Timeout of 0.01s should be exceeded by 0.05s sleep
        resp = bus.send_request("slow", "go", timeout=0.01)
        assert resp.success is False
        assert "timed out" in (resp.error or "")
        assert bus.error_count == 1

    def test_response_has_request_id(self, bus: ServiceBus) -> None:
        """Response carries a valid request_id (UUID format)."""
        bus.register_service("svc", lambda req: {})
        resp = bus.send_request("svc", "act")
        assert resp.request_id is not None
        assert len(resp.request_id) > 0

    def test_request_unknown_service_increments_both_counts(self, bus: ServiceBus) -> None:
        """Unknown service increments both request_count and error_count."""
        bus.send_request("ghost", "ping")
        assert bus.request_count == 1
        assert bus.error_count == 1


# ------------------------------------------------------------------
# Broadcast
# ------------------------------------------------------------------


class TestBroadcast:
    """Tests for broadcast."""

    def test_broadcast_to_all_services(self, bus: ServiceBus) -> None:
        """Broadcast sends to every registered service."""
        bus.register_service("a", lambda req: {"name": "a"})
        bus.register_service("b", lambda req: {"name": "b"})
        results = bus.broadcast("ping")
        assert len(results) == 2
        assert results["a"].success is True
        assert results["b"].success is True

    def test_broadcast_with_payload(self, bus: ServiceBus) -> None:
        """Broadcast passes the payload to all services."""
        received: list[dict] = []

        def capture(req: ServiceRequest) -> dict:
            received.append(req.payload)
            return {}

        bus.register_service("c1", capture)
        bus.register_service("c2", capture)
        bus.broadcast("ping", {"key": "val"})
        assert len(received) == 2
        assert all(r == {"key": "val"} for r in received)

    def test_broadcast_empty_bus(self, bus: ServiceBus) -> None:
        """Broadcast with no services returns empty dict."""
        results = bus.broadcast("ping")
        assert results == {}

    def test_broadcast_partial_failure(self, bus: ServiceBus) -> None:
        """Broadcast collects both successes and failures."""
        bus.register_service("ok", lambda req: {"status": "ok"})
        bus.register_service("fail", lambda req: (_ for _ in ()).throw(RuntimeError("boom")))
        results = bus.broadcast("check")
        assert results["ok"].success is True
        assert results["fail"].success is False

    def test_broadcast_increments_request_count(self, bus: ServiceBus) -> None:
        """Broadcast increments request_count for each service."""
        bus.register_service("a", lambda req: {})
        bus.register_service("b", lambda req: {})
        bus.broadcast("ping")
        assert bus.request_count == 2

    def test_broadcast_default_payload_is_empty_dict(self, bus: ServiceBus) -> None:
        """Broadcast without payload sends empty dict."""
        received: list[dict] = []

        def capture(req: ServiceRequest) -> dict:
            received.append(req.payload)
            return {}

        bus.register_service("svc", capture)
        bus.broadcast("ping")
        assert received == [{}]


# ------------------------------------------------------------------
# Utility / edge cases
# ------------------------------------------------------------------


class TestServiceBusUtility:
    """Tests for utility methods and edge cases."""

    def test_repr(self, bus: ServiceBus) -> None:
        """repr includes name, service count, request/error counts."""
        r = repr(bus)
        assert "test-bus" in r
        assert "services=" in r
        assert "requests=" in r
        assert "errors=" in r

    def test_name_property(self, bus: ServiceBus) -> None:
        """name property returns the bus name."""
        assert bus.name == "test-bus"

    def test_default_name(self, mock_pubsub: PubSubManager) -> None:
        """Default bus name is 'default'."""
        bus = ServiceBus(pubsub=mock_pubsub)
        assert bus.name == "default"

    def test_request_count_increments(self, bus: ServiceBus) -> None:
        """request_count increments for every send_request call."""
        bus.register_service("s", lambda req: {})
        bus.send_request("s", "a")
        bus.send_request("s", "b")
        bus.send_request("s", "c")
        assert bus.request_count == 3

    def test_error_count_tracks_failures(self, bus: ServiceBus) -> None:
        """error_count tracks handler errors and missing services."""
        bus.send_request("missing", "a")
        bus.register_service("bad", lambda req: (_ for _ in ()).throw(ValueError("x")))
        bus.send_request("bad", "b")
        assert bus.error_count == 2

    def test_creates_default_pubsub(self) -> None:
        """ServiceBus creates a default PubSubManager if none provided."""
        bus = ServiceBus(name="standalone")
        assert bus.name == "standalone"
        assert bus.request_count == 0

    def test_initial_counts_are_zero(self, bus: ServiceBus) -> None:
        """Initial request_count and error_count are zero."""
        assert bus.request_count == 0
        assert bus.error_count == 0

    def test_list_services_empty_bus(self, bus: ServiceBus) -> None:
        """list_services returns empty list on empty bus."""
        assert bus.list_services() == []
