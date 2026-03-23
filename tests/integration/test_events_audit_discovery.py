"""Integration tests for events/audit.py and events/discovery.py.

Covers:
- AuditEntry: to_dict, from_dict, roundtrip
- AuditFilter: all field combinations
- AuditLogger: log_event, query_audit_log (no filter, stream filter, action
  filter, event_id filter, time-range filter, combined), get_entry_count,
  clear, malformed line handling, missing file fallback, log_path property
- ServiceInfo: __post_init__ timestamps, to_dict, from_dict
- ServiceDiscovery: register (new + overwrite), deregister (found/missing),
  discover (found/missing), list_services, heartbeat (found/missing),
  count, registry_path, clear, persist-reload cycle, corrupt file fallback
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(event_id: str = "1-0", stream: str = "files", data: dict | None = None):
    from file_organizer.events.stream import Event

    return Event(id=event_id, stream=stream, data=data or {"type": "created"})


# ---------------------------------------------------------------------------
# AuditEntry
# ---------------------------------------------------------------------------


class TestAuditEntry:
    def test_to_dict_contains_all_fields(self) -> None:
        from file_organizer.events.audit import AuditEntry

        ts = datetime(2026, 1, 15, 10, 30, tzinfo=UTC)
        entry = AuditEntry(
            timestamp=ts,
            event_id="99-0",
            stream="events.files",
            action="consumed",
            metadata={"worker": "w1"},
        )
        d = entry.to_dict()
        assert d["timestamp"] == ts.isoformat()
        assert d["event_id"] == "99-0"
        assert d["stream"] == "events.files"
        assert d["action"] == "consumed"
        assert d["metadata"] == {"worker": "w1"}

    def test_from_dict_roundtrip(self) -> None:
        from file_organizer.events.audit import AuditEntry

        ts = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
        entry = AuditEntry(
            timestamp=ts, event_id="5-0", stream="s", action="published", metadata={"k": "v"}
        )
        restored = AuditEntry.from_dict(entry.to_dict())
        assert restored.event_id == "5-0"
        assert restored.stream == "s"
        assert restored.action == "published"
        assert restored.metadata == {"k": "v"}
        assert restored.timestamp == ts

    def test_from_dict_missing_metadata_defaults_to_empty(self) -> None:
        from file_organizer.events.audit import AuditEntry

        data = {
            "timestamp": datetime(2026, 1, 1, tzinfo=UTC).isoformat(),
            "event_id": "1-0",
            "stream": "test",
            "action": "replayed",
        }
        entry = AuditEntry.from_dict(data)
        assert entry.metadata == {}

    def test_to_dict_timestamp_is_string(self) -> None:
        from file_organizer.events.audit import AuditEntry

        entry = AuditEntry(timestamp=datetime.now(UTC), event_id="x", stream="s", action="a")
        d = entry.to_dict()
        assert isinstance(d["timestamp"], str)
        assert len(d["timestamp"]) > 0


# ---------------------------------------------------------------------------
# AuditLogger
# ---------------------------------------------------------------------------


class TestAuditLogger:
    def test_log_event_returns_audit_entry(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditEntry, AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        event = _make_event()
        entry = log.log_event(event, "published")
        assert isinstance(entry, AuditEntry)
        assert entry.event_id == "1-0"
        assert entry.stream == "files"
        assert entry.action == "published"

    def test_log_event_persists_to_file(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        log.log_event(_make_event(), "consumed")
        assert (tmp_path / "audit.jsonl").exists()
        content = (tmp_path / "audit.jsonl").read_text()
        assert "consumed" in content

    def test_log_event_creates_parent_dirs(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        nested = tmp_path / "a" / "b" / "c" / "audit.jsonl"
        log = AuditLogger(nested)
        log.log_event(_make_event(), "published")
        assert nested.exists()

    def test_log_path_property(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        path = tmp_path / "audit.jsonl"
        log = AuditLogger(path)
        assert log.log_path == path

    def test_query_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        log = AuditLogger(tmp_path / "missing.jsonl")
        assert log.query_audit_log() == []

    def test_query_returns_all_entries_without_filter(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        log.log_event(_make_event("1-0", "stream.a"), "published")
        log.log_event(_make_event("2-0", "stream.b"), "consumed")
        entries = log.query_audit_log()
        assert len(entries) == 2

    def test_query_filter_by_stream(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditFilter, AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        log.log_event(_make_event("1-0", "stream.a"), "published")
        log.log_event(_make_event("2-0", "stream.b"), "published")
        results = log.query_audit_log(AuditFilter(stream="stream.a"))
        assert len(results) == 1
        assert results[0].stream == "stream.a"

    def test_query_filter_by_action(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditFilter, AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        log.log_event(_make_event("1-0"), "published")
        log.log_event(_make_event("2-0"), "consumed")
        log.log_event(_make_event("3-0"), "consumed")
        results = log.query_audit_log(AuditFilter(action="consumed"))
        assert len(results) == 2
        assert all(e.action == "consumed" for e in results)

    def test_query_filter_by_event_id(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditFilter, AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        log.log_event(_make_event("abc-0"), "published")
        log.log_event(_make_event("xyz-0"), "published")
        results = log.query_audit_log(AuditFilter(event_id="abc-0"))
        assert len(results) == 1
        assert results[0].event_id == "abc-0"

    def test_query_filter_by_time_range(self, tmp_path: Path) -> None:
        import json

        from file_organizer.events.audit import AuditEntry, AuditFilter, AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        t_old = datetime(2025, 1, 1, tzinfo=UTC)
        t_new = datetime(2026, 1, 1, tzinfo=UTC)
        entry_old = AuditEntry(timestamp=t_old, event_id="old", stream="s", action="a")
        entry_new = AuditEntry(timestamp=t_new, event_id="new", stream="s", action="a")
        with open(tmp_path / "audit.jsonl", "w") as f:
            f.write(json.dumps(entry_old.to_dict()) + "\n")
            f.write(json.dumps(entry_new.to_dict()) + "\n")

        cutoff = datetime(2025, 6, 1, tzinfo=UTC)
        results = log.query_audit_log(AuditFilter(start_time=cutoff))
        assert len(results) == 1
        assert results[0].event_id == "new"

    def test_query_filter_by_end_time(self, tmp_path: Path) -> None:
        import json

        from file_organizer.events.audit import AuditEntry, AuditFilter, AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        t_old = datetime(2025, 1, 1, tzinfo=UTC)
        t_new = datetime(2026, 1, 1, tzinfo=UTC)
        entry_old = AuditEntry(timestamp=t_old, event_id="old", stream="s", action="a")
        entry_new = AuditEntry(timestamp=t_new, event_id="new", stream="s", action="a")
        with open(tmp_path / "audit.jsonl", "w") as f:
            f.write(json.dumps(entry_old.to_dict()) + "\n")
            f.write(json.dumps(entry_new.to_dict()) + "\n")

        cutoff = datetime(2025, 6, 1, tzinfo=UTC)
        results = log.query_audit_log(AuditFilter(end_time=cutoff))
        assert len(results) == 1
        assert results[0].event_id == "old"

    def test_query_combined_filters(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditFilter, AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        log.log_event(_make_event("1-0", "stream.a"), "published")
        log.log_event(_make_event("2-0", "stream.a"), "consumed")
        log.log_event(_make_event("3-0", "stream.b"), "published")
        results = log.query_audit_log(AuditFilter(stream="stream.a", action="published"))
        assert len(results) == 1
        assert results[0].event_id == "1-0"

    def test_query_skips_malformed_lines(self, tmp_path: Path) -> None:
        import json

        from file_organizer.events.audit import AuditEntry, AuditLogger

        log_path = tmp_path / "audit.jsonl"
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        good = AuditEntry(timestamp=ts, event_id="ok", stream="s", action="a")
        with open(log_path, "w") as f:
            f.write("{ invalid json }\n")
            f.write(json.dumps(good.to_dict()) + "\n")

        log = AuditLogger(log_path)
        results = log.query_audit_log()
        assert len(results) == 1
        assert results[0].event_id == "ok"

    def test_query_skips_blank_lines(self, tmp_path: Path) -> None:
        import json

        from file_organizer.events.audit import AuditEntry, AuditLogger

        log_path = tmp_path / "audit.jsonl"
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        entry = AuditEntry(timestamp=ts, event_id="ok", stream="s", action="a")
        with open(log_path, "w") as f:
            f.write("\n")
            f.write("  \n")
            f.write(json.dumps(entry.to_dict()) + "\n")

        log = AuditLogger(log_path)
        results = log.query_audit_log()
        assert len(results) == 1

    def test_get_entry_count_zero_when_no_file(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        log = AuditLogger(tmp_path / "missing.jsonl")
        assert log.get_entry_count() == 0

    def test_get_entry_count_matches_logged_events(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        for i in range(5):
            log.log_event(_make_event(f"{i}-0"), "published")
        assert log.get_entry_count() == 5

    def test_clear_removes_log_file(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        log.log_event(_make_event(), "published")
        assert log.get_entry_count() == 1
        log.clear()
        assert not (tmp_path / "audit.jsonl").exists()
        assert log.get_entry_count() == 0

    def test_clear_on_missing_file_is_noop(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        log = AuditLogger(tmp_path / "nonexistent.jsonl")
        log.clear()  # Should not raise

    def test_log_event_includes_event_data_in_metadata(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        log = AuditLogger(tmp_path / "audit.jsonl")
        event = _make_event(data={"type": "moved", "dest": "/new/path"})
        entry = log.log_event(event, "consumed")
        assert entry.metadata == {"type": "moved", "dest": "/new/path"}

    def test_repr_contains_path(self, tmp_path: Path) -> None:
        from file_organizer.events.audit import AuditLogger

        path = tmp_path / "audit.jsonl"
        log = AuditLogger(path)
        assert str(path) in repr(log)


# ---------------------------------------------------------------------------
# AuditFilter
# ---------------------------------------------------------------------------


class TestAuditFilter:
    def test_none_filter_matches_all(self) -> None:
        from file_organizer.events.audit import AuditEntry, AuditLogger

        entry = AuditEntry(timestamp=datetime.now(UTC), event_id="x", stream="s", action="a")
        assert AuditLogger._matches_filter(entry, None) is True

    def test_stream_filter_no_match(self) -> None:
        from file_organizer.events.audit import AuditEntry, AuditFilter, AuditLogger

        entry = AuditEntry(timestamp=datetime.now(UTC), event_id="x", stream="s1", action="a")
        assert AuditLogger._matches_filter(entry, AuditFilter(stream="s2")) is False

    def test_action_filter_match(self) -> None:
        from file_organizer.events.audit import AuditEntry, AuditFilter, AuditLogger

        entry = AuditEntry(
            timestamp=datetime.now(UTC), event_id="x", stream="s", action="published"
        )
        assert AuditLogger._matches_filter(entry, AuditFilter(action="published")) is True

    def test_event_id_filter_no_match(self) -> None:
        from file_organizer.events.audit import AuditEntry, AuditFilter, AuditLogger

        entry = AuditEntry(timestamp=datetime.now(UTC), event_id="abc", stream="s", action="a")
        assert AuditLogger._matches_filter(entry, AuditFilter(event_id="xyz")) is False


# ---------------------------------------------------------------------------
# ServiceInfo
# ---------------------------------------------------------------------------


class TestServiceInfo:
    def test_registered_at_auto_set(self) -> None:
        from file_organizer.events.discovery import ServiceInfo

        info = ServiceInfo(name="svc", endpoint="http://localhost:8080")
        assert info.registered_at != ""
        assert "T" in info.registered_at  # ISO format has T separator

    def test_last_heartbeat_auto_set(self) -> None:
        from file_organizer.events.discovery import ServiceInfo

        info = ServiceInfo(name="svc", endpoint="http://localhost:8080")
        assert info.last_heartbeat != ""

    def test_explicit_timestamps_preserved(self) -> None:
        from file_organizer.events.discovery import ServiceInfo

        ts = "2025-01-01T00:00:00+00:00"
        info = ServiceInfo(name="svc", endpoint="e", registered_at=ts, last_heartbeat=ts)
        assert info.registered_at == ts
        assert info.last_heartbeat == ts

    def test_to_dict_contains_all_fields(self) -> None:
        from file_organizer.events.discovery import ServiceInfo

        info = ServiceInfo(name="svc", endpoint="e", metadata={"k": "v"})
        d = info.to_dict()
        assert d["name"] == "svc"
        assert d["endpoint"] == "e"
        assert d["metadata"] == {"k": "v"}

    def test_from_dict_roundtrip(self) -> None:
        from file_organizer.events.discovery import ServiceInfo

        info = ServiceInfo(name="svc", endpoint="e", metadata={"x": 1})
        restored = ServiceInfo.from_dict(info.to_dict())
        assert restored.name == "svc"
        assert restored.endpoint == "e"
        assert restored.metadata == {"x": 1}

    def test_from_dict_missing_metadata_defaults_empty(self) -> None:
        from file_organizer.events.discovery import ServiceInfo

        info = ServiceInfo.from_dict({"name": "s", "endpoint": "e"})
        assert info.metadata == {}


# ---------------------------------------------------------------------------
# ServiceDiscovery
# ---------------------------------------------------------------------------


class TestServiceDiscovery:
    def test_register_returns_service_info(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery, ServiceInfo

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        info = disc.register("classifier", "local://classifier:8001")
        assert isinstance(info, ServiceInfo)
        assert info.name == "classifier"
        assert info.endpoint == "local://classifier:8001"

    def test_register_with_metadata(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        info = disc.register("svc", "e", metadata={"version": "2.0"})
        assert info.metadata == {"version": "2.0"}

    def test_register_overwrites_existing(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        disc.register("svc", "endpoint-v1")
        disc.register("svc", "endpoint-v2")
        assert disc.discover("svc").endpoint == "endpoint-v2"
        assert disc.count == 1

    def test_discover_returns_service_info(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery, ServiceInfo

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        disc.register("svc", "e")
        result = disc.discover("svc")
        assert isinstance(result, ServiceInfo)
        assert result.name == "svc"

    def test_discover_returns_none_for_missing(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        assert disc.discover("ghost") is None

    def test_deregister_returns_true_when_found(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        disc.register("svc", "e")
        assert disc.deregister("svc") is True
        assert disc.discover("svc") is None

    def test_deregister_returns_false_when_not_found(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        assert disc.deregister("ghost") is False

    def test_list_services_returns_sorted_by_name(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        disc.register("z_svc", "e1")
        disc.register("a_svc", "e2")
        disc.register("m_svc", "e3")
        services = disc.list_services()
        assert [s.name for s in services] == ["a_svc", "m_svc", "z_svc"]

    def test_list_services_empty_when_no_services(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        assert disc.list_services() == []

    def test_heartbeat_updates_timestamp(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        disc.register("svc", "e")
        old_hb = disc.discover("svc").last_heartbeat
        disc.heartbeat("svc")
        new_hb = disc.discover("svc").last_heartbeat
        assert new_hb > old_hb

    def test_heartbeat_returns_true_when_found(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        disc.register("svc", "e")
        assert disc.heartbeat("svc") is True

    def test_heartbeat_returns_false_when_not_found(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        assert disc.heartbeat("ghost") is False

    def test_count_reflects_registrations(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        assert disc.count == 0
        disc.register("a", "e1")
        disc.register("b", "e2")
        assert disc.count == 2
        disc.deregister("a")
        assert disc.count == 1

    def test_clear_removes_all_services(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "registry.json")
        disc.register("a", "e1")
        disc.register("b", "e2")
        removed = disc.clear()
        assert removed == 2
        assert disc.count == 0

    def test_registry_path_property(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        path = tmp_path / "registry.json"
        disc = ServiceDiscovery(registry_path=path)
        assert disc.registry_path == path

    def test_persist_and_reload(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        registry = tmp_path / "registry.json"
        disc = ServiceDiscovery(registry_path=registry)
        disc.register("svc", "http://localhost:9000", metadata={"env": "prod"})

        disc2 = ServiceDiscovery(registry_path=registry)
        info = disc2.discover("svc")
        assert info is not None
        assert info.endpoint == "http://localhost:9000"
        assert info.metadata == {"env": "prod"}

    def test_corrupt_file_starts_fresh(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        registry = tmp_path / "registry.json"
        registry.write_text("{ invalid json }", encoding="utf-8")
        disc = ServiceDiscovery(registry_path=registry)
        assert disc.count == 0

    def test_repr_contains_service_count(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        disc = ServiceDiscovery(registry_path=tmp_path / "r.json")
        disc.register("svc", "e")
        assert "1" in repr(disc)

    def test_register_persists_to_disk(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        registry = tmp_path / "registry.json"
        disc = ServiceDiscovery(registry_path=registry)
        disc.register("svc", "e")
        assert registry.exists()
        content = registry.read_text()
        assert "svc" in content

    def test_deregister_persists_to_disk(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery

        registry = tmp_path / "registry.json"
        disc = ServiceDiscovery(registry_path=registry)
        disc.register("svc", "e")
        disc.deregister("svc")

        disc2 = ServiceDiscovery(registry_path=registry)
        assert disc2.discover("svc") is None
