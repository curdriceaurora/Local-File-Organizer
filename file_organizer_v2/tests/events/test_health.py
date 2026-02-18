"""
Unit tests for HealthChecker, HealthStatus, and ServiceHealth.

Tests health checking via the service bus, status resolution from
latency thresholds, history tracking, discovery integration, and
edge cases.  All Redis operations are mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.events.discovery import ServiceDiscovery
from file_organizer.events.health import (
    HealthChecker,
    HealthStatus,
    ServiceHealth,
)
from file_organizer.events.pubsub import PubSubManager
from file_organizer.events.service_bus import ServiceBus, ServiceRequest
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
def bus(mock_manager: MagicMock) -> ServiceBus:
    """Create a ServiceBus with mocked pubsub."""
    pubsub = PubSubManager(stream_manager=mock_manager)
    return ServiceBus(name="test-bus", pubsub=pubsub)


@pytest.fixture
def discovery(tmp_path: Path) -> ServiceDiscovery:
    """Create a ServiceDiscovery with a temporary registry."""
    return ServiceDiscovery(registry_path=tmp_path / "registry.json")


@pytest.fixture
def checker(bus: ServiceBus, discovery: ServiceDiscovery) -> HealthChecker:
    """Create a HealthChecker with test bus and discovery."""
    return HealthChecker(
        service_bus=bus,
        discovery=discovery,
        degraded_threshold_ms=100.0,
        unhealthy_threshold_ms=500.0,
    )


# ------------------------------------------------------------------
# HealthStatus enum
# ------------------------------------------------------------------


class TestHealthStatus:
    """Tests for the HealthStatus enum."""

    def test_values(self) -> None:
        """HealthStatus has the expected members."""
        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


# ------------------------------------------------------------------
# ServiceHealth dataclass
# ------------------------------------------------------------------


class TestServiceHealth:
    """Tests for the ServiceHealth dataclass."""

    def test_creation(self) -> None:
        """ServiceHealth can be created with defaults."""
        h = ServiceHealth(name="svc", status=HealthStatus.HEALTHY)
        assert h.name == "svc"
        assert h.status == HealthStatus.HEALTHY
        assert h.latency_ms == 0.0
        assert h.details == {}
        assert h.last_check is not None

    def test_to_dict(self) -> None:
        """to_dict serializes all fields."""
        h = ServiceHealth(
            name="svc",
            status=HealthStatus.DEGRADED,
            latency_ms=150.0,
            details={"note": "slow"},
        )
        d = h.to_dict()
        assert d["name"] == "svc"
        assert d["status"] == "degraded"
        assert d["latency_ms"] == 150.0
        assert d["details"] == {"note": "slow"}
        assert "last_check" in d


# ------------------------------------------------------------------
# check_service
# ------------------------------------------------------------------


class TestCheckService:
    """Tests for checking a single service."""

    def test_healthy_service(self, checker: HealthChecker, bus: ServiceBus) -> None:
        """A fast, successful handler yields HEALTHY."""
        bus.register_service("fast", lambda req: {"ok": True})
        health = checker.check_service("fast")
        assert health.status == HealthStatus.HEALTHY
        assert health.latency_ms >= 0

    def test_unknown_service(self, checker: HealthChecker) -> None:
        """An unregistered service yields UNKNOWN status."""
        health = checker.check_service("ghost")
        assert health.status == HealthStatus.UNKNOWN
        assert "not registered" in health.details.get("error", "")

    def test_unhealthy_on_handler_error(self, checker: HealthChecker, bus: ServiceBus) -> None:
        """A handler that raises yields UNHEALTHY."""

        def broken(req: ServiceRequest) -> dict:
            raise RuntimeError("broken")

        bus.register_service("broken", broken)
        health = checker.check_service("broken")
        assert health.status == HealthStatus.UNHEALTHY
        assert "broken" in health.details.get("error", "")

    def test_check_records_history(self, checker: HealthChecker, bus: ServiceBus) -> None:
        """check_service records results in history."""
        bus.register_service("hist", lambda req: {})
        checker.check_service("hist")
        checker.check_service("hist")
        history = checker.get_history("hist")
        assert len(history) == 2


# ------------------------------------------------------------------
# check_all
# ------------------------------------------------------------------


class TestCheckAll:
    """Tests for checking all services."""

    def test_check_all_bus_services(self, checker: HealthChecker, bus: ServiceBus) -> None:
        """check_all includes all services registered on the bus."""
        bus.register_service("svc1", lambda req: {})
        bus.register_service("svc2", lambda req: {})
        results = checker.check_all()
        assert "svc1" in results
        assert "svc2" in results
        assert len(results) == 2

    def test_check_all_includes_discovery(
        self, checker: HealthChecker, bus: ServiceBus, discovery: ServiceDiscovery
    ) -> None:
        """check_all includes services from discovery registry."""
        bus.register_service("bus-svc", lambda req: {})
        discovery.register("disc-svc", "local://disc:1000")
        results = checker.check_all()
        assert "bus-svc" in results
        assert "disc-svc" in results

    def test_check_all_empty(self, checker: HealthChecker) -> None:
        """check_all with no services returns empty dict."""
        results = checker.check_all()
        assert results == {}


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------


class TestHistory:
    """Tests for health check history."""

    def test_get_history_empty(self, checker: HealthChecker) -> None:
        """get_history for unknown service returns empty list."""
        assert checker.get_history("nonexistent") == []

    def test_clear_history_specific(self, checker: HealthChecker, bus: ServiceBus) -> None:
        """clear_history(name) clears only that service's history."""
        bus.register_service("a", lambda req: {})
        bus.register_service("b", lambda req: {})
        checker.check_service("a")
        checker.check_service("b")
        removed = checker.clear_history("a")
        assert removed == 1
        assert checker.get_history("a") == []
        assert len(checker.get_history("b")) == 1

    def test_clear_history_all(self, checker: HealthChecker, bus: ServiceBus) -> None:
        """clear_history() without name clears all history."""
        bus.register_service("x", lambda req: {})
        checker.check_service("x")
        checker.check_service("x")
        removed = checker.clear_history()
        assert removed == 2
        assert checker.get_history("x") == []


# ------------------------------------------------------------------
# Threshold / status resolution
# ------------------------------------------------------------------


class TestThresholds:
    """Tests for latency threshold resolution."""

    def test_threshold_properties(self, checker: HealthChecker) -> None:
        """Threshold properties reflect constructor values."""
        assert checker.degraded_threshold_ms == 100.0
        assert checker.unhealthy_threshold_ms == 500.0

    def test_resolve_healthy(self, checker: HealthChecker) -> None:
        """Latency below degraded threshold -> HEALTHY."""
        assert checker._resolve_status(50.0) == HealthStatus.HEALTHY

    def test_resolve_degraded(self, checker: HealthChecker) -> None:
        """Latency between thresholds -> DEGRADED."""
        assert checker._resolve_status(200.0) == HealthStatus.DEGRADED

    def test_resolve_unhealthy(self, checker: HealthChecker) -> None:
        """Latency above unhealthy threshold -> UNHEALTHY."""
        assert checker._resolve_status(600.0) == HealthStatus.UNHEALTHY

    def test_resolve_boundary_degraded(self, checker: HealthChecker) -> None:
        """Latency exactly at degraded threshold -> DEGRADED."""
        assert checker._resolve_status(100.0) == HealthStatus.DEGRADED

    def test_resolve_boundary_unhealthy(self, checker: HealthChecker) -> None:
        """Latency exactly at unhealthy threshold -> UNHEALTHY."""
        assert checker._resolve_status(500.0) == HealthStatus.UNHEALTHY


# ------------------------------------------------------------------
# Utility
# ------------------------------------------------------------------


class TestHealthCheckerUtility:
    """Tests for utility methods and edge cases."""

    def test_repr(self, checker: HealthChecker) -> None:
        """repr includes checked services and thresholds."""
        r = repr(checker)
        assert "checked_services=" in r
        assert "degraded_ms=" in r
        assert "unhealthy_ms=" in r

    def test_no_discovery(self, bus: ServiceBus) -> None:
        """HealthChecker works without a discovery instance."""
        checker = HealthChecker(service_bus=bus)
        bus.register_service("solo", lambda req: {})
        results = checker.check_all()
        assert "solo" in results
