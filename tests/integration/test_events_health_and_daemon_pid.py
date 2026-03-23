"""Integration tests for events/health.py and daemon/pid.py.

Covers:
- HealthStatus: enum values
- ServiceHealth: to_dict, fields
- HealthChecker: properties, check_service (unknown, success, failure,
  HEALTHY/DEGRADED/UNHEALTHY thresholds), check_all (bus only, bus+discovery),
  get_history, clear_history (single/all), _resolve_status, _record ring buffer,
  repr
- PidFileManager: write_pid (current pid, explicit pid), read_pid (exists,
  missing, empty, invalid), remove_pid (exists, missing), is_running
  (current process, dead pid, missing file)
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bus(service_names: list[str] | None = None):
    """Build a mock ServiceBus with the given registered service names."""
    from file_organizer.events.service_bus import ServiceResponse

    bus = MagicMock()
    names = service_names or []
    bus.has_service.side_effect = lambda name: name in names
    bus.list_services.return_value = names

    def _send(target, action, payload, timeout):
        return ServiceResponse(request_id="req-1", success=True, data={})

    bus.send_request.side_effect = _send
    return bus


def _make_checker(service_names: list[str] | None = None, **kwargs):
    from file_organizer.events.health import HealthChecker

    bus = _make_bus(service_names)
    return HealthChecker(bus, **kwargs)


# ---------------------------------------------------------------------------
# HealthStatus
# ---------------------------------------------------------------------------


class TestHealthStatus:
    def test_values(self) -> None:
        from file_organizer.events.health import HealthStatus

        assert HealthStatus.HEALTHY.value == "healthy"
        assert HealthStatus.DEGRADED.value == "degraded"
        assert HealthStatus.UNHEALTHY.value == "unhealthy"
        assert HealthStatus.UNKNOWN.value == "unknown"


# ---------------------------------------------------------------------------
# ServiceHealth
# ---------------------------------------------------------------------------


class TestServiceHealth:
    def test_to_dict_contains_all_fields(self) -> None:
        from file_organizer.events.health import HealthStatus, ServiceHealth

        health = ServiceHealth(name="svc", status=HealthStatus.HEALTHY, latency_ms=12.3)
        d = health.to_dict()
        assert d["name"] == "svc"
        assert d["status"] == "healthy"
        assert d["latency_ms"] == pytest.approx(12.3)
        assert "last_check" in d
        assert "details" in d

    def test_default_latency_is_zero(self) -> None:
        from file_organizer.events.health import HealthStatus, ServiceHealth

        health = ServiceHealth(name="s", status=HealthStatus.UNKNOWN)
        assert health.latency_ms == 0.0

    def test_details_dict_serialized(self) -> None:
        from file_organizer.events.health import HealthStatus, ServiceHealth

        health = ServiceHealth(name="s", status=HealthStatus.DEGRADED, details={"version": "1.0"})
        assert health.to_dict()["details"] == {"version": "1.0"}


# ---------------------------------------------------------------------------
# HealthChecker properties
# ---------------------------------------------------------------------------


class TestHealthCheckerProperties:
    def test_degraded_threshold_ms_property(self) -> None:
        checker = _make_checker(degraded_threshold_ms=300.0)
        assert checker.degraded_threshold_ms == pytest.approx(300.0)

    def test_unhealthy_threshold_ms_property(self) -> None:
        checker = _make_checker(unhealthy_threshold_ms=1500.0)
        assert checker.unhealthy_threshold_ms == pytest.approx(1500.0)

    def test_repr_contains_counts(self) -> None:
        checker = _make_checker()
        r = repr(checker)
        assert "HealthChecker" in r
        assert "degraded_ms" in r


# ---------------------------------------------------------------------------
# HealthChecker.check_service
# ---------------------------------------------------------------------------


class TestHealthCheckerCheckService:
    def test_unknown_when_service_not_on_bus(self) -> None:
        from file_organizer.events.health import HealthStatus

        checker = _make_checker(service_names=[])
        health = checker.check_service("unknown_svc")
        assert health.status == HealthStatus.UNKNOWN
        assert health.name == "unknown_svc"

    def test_healthy_when_fast_response(self) -> None:
        from file_organizer.events.health import HealthStatus

        checker = _make_checker(
            service_names=["fast_svc"],
            degraded_threshold_ms=500.0,
            unhealthy_threshold_ms=2000.0,
        )
        health = checker.check_service("fast_svc")
        assert health.status == HealthStatus.HEALTHY

    def test_unhealthy_when_request_fails(self) -> None:
        from file_organizer.events.health import HealthStatus
        from file_organizer.events.service_bus import ServiceResponse

        bus = _make_bus(["failing_svc"])
        bus.send_request.side_effect = None
        bus.send_request.return_value = ServiceResponse(
            request_id="r", success=False, error="Timeout"
        )
        from file_organizer.events.health import HealthChecker

        checker = HealthChecker(bus)
        health = checker.check_service("failing_svc")
        assert health.status == HealthStatus.UNHEALTHY
        assert "Timeout" in health.details.get("error", "")

    def test_degraded_when_latency_exceeds_degraded_threshold(self) -> None:

        from file_organizer.events.health import HealthStatus
        from file_organizer.events.service_bus import ServiceResponse

        bus = _make_bus(["slow_svc"])
        bus.send_request.side_effect = None
        bus.send_request.return_value = ServiceResponse(request_id="r", success=True)
        from file_organizer.events.health import HealthChecker

        checker = HealthChecker(bus, degraded_threshold_ms=0.0, unhealthy_threshold_ms=10000.0)
        health = checker.check_service("slow_svc")
        assert health.status == HealthStatus.DEGRADED

    def test_check_service_records_in_history(self) -> None:
        checker = _make_checker(service_names=["svc"])
        checker.check_service("svc")
        history = checker.get_history("svc")
        assert len(history) == 1

    def test_unknown_service_also_recorded_in_history(self) -> None:
        checker = _make_checker(service_names=[])
        checker.check_service("ghost")
        assert len(checker.get_history("ghost")) == 1

    def test_response_data_included_in_details_on_success(self) -> None:
        from file_organizer.events.service_bus import ServiceResponse

        bus = _make_bus(["svc"])
        bus.send_request.side_effect = None
        bus.send_request.return_value = ServiceResponse(
            request_id="r", success=True, data={"uptime": 42}
        )
        from file_organizer.events.health import HealthChecker

        checker = HealthChecker(bus)
        health = checker.check_service("svc")
        assert health.details.get("uptime") == 42

    def test_unhealthy_when_error_is_none(self) -> None:
        from file_organizer.events.health import HealthStatus
        from file_organizer.events.service_bus import ServiceResponse

        bus = _make_bus(["svc"])
        bus.send_request.side_effect = None
        bus.send_request.return_value = ServiceResponse(request_id="r", success=False, error=None)
        from file_organizer.events.health import HealthChecker

        checker = HealthChecker(bus)
        health = checker.check_service("svc")
        assert health.status == HealthStatus.UNHEALTHY
        assert "Unknown failure" in health.details.get("error", "")


# ---------------------------------------------------------------------------
# HealthChecker.check_all
# ---------------------------------------------------------------------------


class TestHealthCheckerCheckAll:
    def test_check_all_returns_dict_for_all_bus_services(self) -> None:
        checker = _make_checker(service_names=["a", "b"])
        results = checker.check_all()
        assert set(results.keys()) == {"a", "b"}

    def test_check_all_empty_bus_returns_empty_dict(self) -> None:
        checker = _make_checker(service_names=[])
        assert checker.check_all() == {}

    def test_check_all_includes_discovery_services(self, tmp_path: Path) -> None:
        from file_organizer.events.discovery import ServiceDiscovery
        from file_organizer.events.health import HealthChecker

        bus = _make_bus(["svc_a"])
        disc = ServiceDiscovery(registry_path=tmp_path / "r.json")
        disc.register("svc_b", "endpoint")

        checker = HealthChecker(bus, discovery=disc)
        results = checker.check_all()
        assert "svc_a" in results
        assert "svc_b" in results

    def test_check_all_results_are_service_health_instances(self) -> None:
        from file_organizer.events.health import ServiceHealth

        checker = _make_checker(service_names=["x"])
        results = checker.check_all()
        assert all(isinstance(v, ServiceHealth) for v in results.values())


# ---------------------------------------------------------------------------
# HealthChecker history
# ---------------------------------------------------------------------------


class TestHealthCheckerHistory:
    def test_get_history_empty_before_checks(self) -> None:
        checker = _make_checker()
        assert checker.get_history("svc") == []

    def test_get_history_accumulates_checks(self) -> None:
        checker = _make_checker(service_names=["svc"])
        checker.check_service("svc")
        checker.check_service("svc")
        assert len(checker.get_history("svc")) == 2

    def test_clear_history_single_service(self) -> None:
        checker = _make_checker(service_names=["a", "b"])
        checker.check_service("a")
        checker.check_service("b")
        removed = checker.clear_history("a")
        assert removed == 1
        assert checker.get_history("a") == []
        assert len(checker.get_history("b")) == 1

    def test_clear_history_all(self) -> None:
        checker = _make_checker(service_names=["x", "y"])
        checker.check_service("x")
        checker.check_service("y")
        removed = checker.clear_history()
        assert removed == 2
        assert checker.get_history("x") == []
        assert checker.get_history("y") == []

    def test_clear_history_missing_service_returns_zero(self) -> None:
        checker = _make_checker()
        assert checker.clear_history("ghost") == 0

    def test_history_ring_buffer_max_100(self) -> None:
        checker = _make_checker(service_names=["svc"])
        for _ in range(105):
            checker.check_service("svc")
        assert len(checker.get_history("svc")) == 100


# ---------------------------------------------------------------------------
# HealthChecker._resolve_status
# ---------------------------------------------------------------------------


class TestHealthCheckerResolveStatus:
    def test_healthy_below_degraded_threshold(self) -> None:
        from file_organizer.events.health import HealthStatus

        checker = _make_checker(degraded_threshold_ms=500.0, unhealthy_threshold_ms=2000.0)
        assert checker._resolve_status(100.0) == HealthStatus.HEALTHY

    def test_degraded_between_thresholds(self) -> None:
        from file_organizer.events.health import HealthStatus

        checker = _make_checker(degraded_threshold_ms=500.0, unhealthy_threshold_ms=2000.0)
        assert checker._resolve_status(1000.0) == HealthStatus.DEGRADED

    def test_unhealthy_at_or_above_unhealthy_threshold(self) -> None:
        from file_organizer.events.health import HealthStatus

        checker = _make_checker(degraded_threshold_ms=500.0, unhealthy_threshold_ms=2000.0)
        assert checker._resolve_status(2000.0) == HealthStatus.UNHEALTHY
        assert checker._resolve_status(3000.0) == HealthStatus.UNHEALTHY


# ---------------------------------------------------------------------------
# PidFileManager
# ---------------------------------------------------------------------------


class TestPidFileManager:
    def test_write_pid_uses_current_process_by_default(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        pid_file = tmp_path / "daemon.pid"
        mgr.write_pid(pid_file)
        assert pid_file.exists()
        content = pid_file.read_text().strip()
        assert int(content) == os.getpid()

    def test_write_pid_uses_explicit_pid(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        pid_file = tmp_path / "daemon.pid"
        mgr.write_pid(pid_file, pid=12345)
        assert pid_file.read_text().strip() == "12345"

    def test_write_pid_creates_parent_dirs(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        nested = tmp_path / "a" / "b" / "daemon.pid"
        mgr.write_pid(nested)
        assert nested.exists()

    def test_write_pid_accepts_string_path(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        pid_file = tmp_path / "daemon.pid"
        mgr.write_pid(str(pid_file))
        assert pid_file.exists()

    def test_read_pid_returns_int_when_file_exists(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        pid_file = tmp_path / "daemon.pid"
        mgr.write_pid(pid_file, pid=9999)
        assert mgr.read_pid(pid_file) == 9999

    def test_read_pid_returns_none_when_missing(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        assert mgr.read_pid(tmp_path / "ghost.pid") is None

    def test_read_pid_returns_none_for_empty_file(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        pid_file = tmp_path / "empty.pid"
        pid_file.write_text("")
        assert mgr.read_pid(pid_file) is None

    def test_read_pid_returns_none_for_invalid_content(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        pid_file = tmp_path / "bad.pid"
        pid_file.write_text("not-a-number")
        assert mgr.read_pid(pid_file) is None

    def test_remove_pid_returns_true_when_exists(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        pid_file = tmp_path / "daemon.pid"
        mgr.write_pid(pid_file)
        assert mgr.remove_pid(pid_file) is True
        assert not pid_file.exists()

    def test_remove_pid_returns_false_when_missing(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        assert mgr.remove_pid(tmp_path / "ghost.pid") is False

    def test_is_running_current_process(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        pid_file = tmp_path / "daemon.pid"
        mgr.write_pid(pid_file)  # writes current PID
        assert mgr.is_running(pid_file) is True

    def test_is_running_false_when_file_missing(self, tmp_path: Path) -> None:
        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        assert mgr.is_running(tmp_path / "ghost.pid") is False

    def test_is_running_false_for_dead_pid(self, tmp_path: Path) -> None:
        from unittest.mock import patch

        from file_organizer.daemon.pid import PidFileManager

        mgr = PidFileManager()
        pid_file = tmp_path / "daemon.pid"
        mgr.write_pid(pid_file, pid=99999999)
        with patch("file_organizer.daemon.pid.os.kill", side_effect=ProcessLookupError):
            result = mgr.is_running(pid_file)
        assert result is False
