"""
Unit tests for ServiceDiscovery and ServiceInfo.

Tests service registration, deregistration, lookup, heartbeat,
JSON file persistence, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from file_organizer.events.discovery import ServiceDiscovery, ServiceInfo

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def registry_path(tmp_path: Path) -> Path:
    """Return a temporary path for the JSON registry."""
    return tmp_path / "service_registry.json"


@pytest.fixture
def discovery(registry_path: Path) -> ServiceDiscovery:
    """Create a ServiceDiscovery with a temporary registry file."""
    return ServiceDiscovery(registry_path=registry_path)


# ------------------------------------------------------------------
# ServiceInfo dataclass
# ------------------------------------------------------------------


class TestServiceInfo:
    """Tests for the ServiceInfo dataclass."""

    def test_creation_defaults(self) -> None:
        """ServiceInfo populates timestamps automatically."""
        info = ServiceInfo(name="svc", endpoint="local://svc:8000")
        assert info.name == "svc"
        assert info.endpoint == "local://svc:8000"
        assert info.metadata == {}
        assert info.registered_at != ""
        assert info.last_heartbeat != ""

    def test_creation_with_metadata(self) -> None:
        """ServiceInfo accepts arbitrary metadata."""
        info = ServiceInfo(
            name="svc",
            endpoint="local://svc:8000",
            metadata={"version": "1.0"},
        )
        assert info.metadata == {"version": "1.0"}

    def test_to_dict(self) -> None:
        """to_dict includes all fields."""
        info = ServiceInfo(
            name="svc",
            endpoint="http://localhost:9000",
            metadata={"tag": "v2"},
        )
        d = info.to_dict()
        assert d["name"] == "svc"
        assert d["endpoint"] == "http://localhost:9000"
        assert d["metadata"] == {"tag": "v2"}
        assert "registered_at" in d
        assert "last_heartbeat" in d

    def test_from_dict_round_trip(self) -> None:
        """from_dict reconstructs a ServiceInfo from to_dict output."""
        original = ServiceInfo(
            name="roundtrip",
            endpoint="tcp://host:1234",
            metadata={"key": "val"},
        )
        restored = ServiceInfo.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.endpoint == original.endpoint
        assert restored.metadata == original.metadata
        assert restored.registered_at == original.registered_at


# ------------------------------------------------------------------
# Registration
# ------------------------------------------------------------------


class TestRegistration:
    """Tests for service registration and deregistration."""

    def test_register_creates_entry(self, discovery: ServiceDiscovery) -> None:
        """register() adds a service to the registry."""
        info = discovery.register("classifier", "local://clf:8001")
        assert discovery.count == 1
        assert info.name == "classifier"
        assert info.endpoint == "local://clf:8001"

    def test_register_with_metadata(self, discovery: ServiceDiscovery) -> None:
        """register() stores metadata."""
        info = discovery.register("indexer", "local://idx:8002", {"version": "2.0"})
        assert info.metadata == {"version": "2.0"}

    def test_register_overwrite(self, discovery: ServiceDiscovery) -> None:
        """Registering the same name overwrites the existing entry."""
        discovery.register("svc", "endpoint-1")
        discovery.register("svc", "endpoint-2")
        assert discovery.count == 1
        info = discovery.discover("svc")
        assert info is not None
        assert info.endpoint == "endpoint-2"

    def test_deregister_existing(self, discovery: ServiceDiscovery) -> None:
        """deregister() removes a known service."""
        discovery.register("temp", "local://temp:9000")
        assert discovery.deregister("temp") is True
        assert discovery.count == 0

    def test_deregister_nonexistent(self, discovery: ServiceDiscovery) -> None:
        """deregister() returns False for unknown services."""
        assert discovery.deregister("ghost") is False


# ------------------------------------------------------------------
# Lookup
# ------------------------------------------------------------------


class TestLookup:
    """Tests for service lookup / discovery."""

    def test_discover_existing(self, discovery: ServiceDiscovery) -> None:
        """discover() returns ServiceInfo for registered services."""
        discovery.register("finder", "local://finder:7000")
        info = discovery.discover("finder")
        assert info is not None
        assert info.name == "finder"

    def test_discover_nonexistent(self, discovery: ServiceDiscovery) -> None:
        """discover() returns None for unknown services."""
        assert discovery.discover("nope") is None

    def test_list_services_sorted(self, discovery: ServiceDiscovery) -> None:
        """list_services() returns entries sorted by name."""
        discovery.register("zebra", "z://z")
        discovery.register("alpha", "a://a")
        discovery.register("middle", "m://m")
        names = [s.name for s in discovery.list_services()]
        assert names == ["alpha", "middle", "zebra"]

    def test_list_services_empty(self, discovery: ServiceDiscovery) -> None:
        """list_services() returns empty list when registry is empty."""
        assert discovery.list_services() == []


# ------------------------------------------------------------------
# Heartbeat
# ------------------------------------------------------------------


class TestHeartbeat:
    """Tests for the heartbeat mechanism."""

    def test_heartbeat_updates_timestamp(self, discovery: ServiceDiscovery) -> None:
        """heartbeat() updates last_heartbeat."""
        info = discovery.register("hb-svc", "local://hb:5000")
        original_hb = info.last_heartbeat
        # Force a small time difference
        import time

        time.sleep(0.01)
        assert discovery.heartbeat("hb-svc") is True
        updated = discovery.discover("hb-svc")
        assert updated is not None
        assert updated.last_heartbeat >= original_hb

    def test_heartbeat_unknown_service(self, discovery: ServiceDiscovery) -> None:
        """heartbeat() returns False for unknown services."""
        assert discovery.heartbeat("ghost") is False


# ------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------


class TestPersistence:
    """Tests for JSON file-based persistence."""

    def test_save_and_reload(self, registry_path: Path) -> None:
        """Registry survives a save/reload cycle."""
        disc1 = ServiceDiscovery(registry_path=registry_path)
        disc1.register("persist-svc", "local://persist:6000", {"v": "1"})

        # Reload from same file
        disc2 = ServiceDiscovery(registry_path=registry_path)
        assert disc2.count == 1
        info = disc2.discover("persist-svc")
        assert info is not None
        assert info.endpoint == "local://persist:6000"
        assert info.metadata == {"v": "1"}

    def test_registry_file_created(self, registry_path: Path) -> None:
        """Registration creates the registry file."""
        disc = ServiceDiscovery(registry_path=registry_path)
        disc.register("file-test", "local://ft:1000")
        assert registry_path.exists()
        content = json.loads(registry_path.read_text())
        assert "file-test" in content

    def test_corrupt_registry_handled(self, registry_path: Path) -> None:
        """Corrupt JSON is handled gracefully."""
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_text("not valid json!!!")
        disc = ServiceDiscovery(registry_path=registry_path)
        assert disc.count == 0  # starts fresh

    def test_missing_registry_starts_empty(self, tmp_path: Path) -> None:
        """Missing registry file starts with empty state."""
        disc = ServiceDiscovery(registry_path=tmp_path / "nonexistent" / "registry.json")
        assert disc.count == 0


# ------------------------------------------------------------------
# Utility / edge cases
# ------------------------------------------------------------------


class TestDiscoveryUtility:
    """Tests for utility methods and edge cases."""

    def test_clear(self, discovery: ServiceDiscovery) -> None:
        """clear() removes all services and returns count."""
        discovery.register("a", "a://a")
        discovery.register("b", "b://b")
        removed = discovery.clear()
        assert removed == 2
        assert discovery.count == 0

    def test_registry_path_property(self, discovery: ServiceDiscovery, registry_path: Path) -> None:
        """registry_path property returns the configured path."""
        assert discovery.registry_path == registry_path

    def test_repr(self, discovery: ServiceDiscovery) -> None:
        """repr includes service count and path."""
        r = repr(discovery)
        assert "services=" in r
        assert "path=" in r
