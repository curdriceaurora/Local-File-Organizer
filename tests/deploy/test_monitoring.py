"""Tests for deployment monitoring and alerting."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from file_organizer.deploy.monitoring import (
    Alert,
    AlertLevel,
    AlertThresholds,
    DeploymentMonitor,
    MetricsSnapshot,
)
from file_organizer.optimization.resource_monitor import MemoryInfo

# ---------------------------------------------------------------------------
# MetricsSnapshot tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestMetricsSnapshot:
    """Tests for the MetricsSnapshot dataclass."""

    def test_create_snapshot(self) -> None:
        """Test creating a MetricsSnapshot with all fields."""
        ts = time.time()
        snap = MetricsSnapshot(
            timestamp=ts,
            cpu_usage=55.0,
            memory_usage=60.0,
            disk_usage=40.0,
            active_connections=120,
            processing_rate=35.5,
        )
        assert snap.timestamp == ts
        assert snap.cpu_usage == 55.0
        assert snap.memory_usage == 60.0
        assert snap.disk_usage == 40.0
        assert snap.active_connections == 120
        assert snap.processing_rate == 35.5

    def test_snapshot_frozen(self) -> None:
        """Test that MetricsSnapshot is immutable."""
        snap = MetricsSnapshot(
            timestamp=0.0,
            cpu_usage=0.0,
            memory_usage=0.0,
            disk_usage=0.0,
            active_connections=0,
            processing_rate=0.0,
        )
        with pytest.raises(AttributeError):
            snap.cpu_usage = 99.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Alert and AlertLevel tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAlert:
    """Tests for the Alert dataclass."""

    def test_create_alert(self) -> None:
        """Test creating an Alert with all fields."""
        alert = Alert(
            level=AlertLevel.WARNING,
            metric="cpu_usage",
            value=85.0,
            threshold=70.0,
            message="CPU high",
        )
        assert alert.level == AlertLevel.WARNING
        assert alert.metric == "cpu_usage"
        assert alert.value == 85.0
        assert alert.threshold == 70.0

    def test_alert_level_values(self) -> None:
        """Test AlertLevel enum values."""
        assert AlertLevel.INFO.value == "info"
        assert AlertLevel.WARNING.value == "warning"
        assert AlertLevel.CRITICAL.value == "critical"

    def test_alert_frozen(self) -> None:
        """Test that Alert is immutable."""
        alert = Alert(
            level=AlertLevel.INFO,
            metric="test",
            value=0.0,
            threshold=0.0,
            message="test",
        )
        with pytest.raises(AttributeError):
            alert.level = AlertLevel.CRITICAL  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AlertThresholds tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestAlertThresholds:
    """Tests for the AlertThresholds dataclass."""

    def test_default_thresholds(self) -> None:
        """Test default threshold values."""
        thresholds = AlertThresholds()
        assert thresholds.cpu_warning == 70.0
        assert thresholds.cpu_critical == 90.0
        assert thresholds.memory_warning == 75.0
        assert thresholds.memory_critical == 90.0
        assert thresholds.disk_warning == 80.0

    def test_custom_thresholds(self) -> None:
        """Test creating custom thresholds."""
        thresholds = AlertThresholds(
            cpu_warning=60.0,
            cpu_critical=85.0,
            memory_warning=65.0,
            memory_critical=88.0,
            disk_warning=70.0,
        )
        assert thresholds.cpu_warning == 60.0
        assert thresholds.disk_warning == 70.0

    def test_invalid_cpu_thresholds(self) -> None:
        """Test that cpu_warning >= cpu_critical raises ValueError."""
        with pytest.raises(ValueError, match=r"cpu_warning.*must be < cpu_critical"):
            AlertThresholds(cpu_warning=90.0, cpu_critical=70.0)

    def test_invalid_memory_thresholds(self) -> None:
        """Test that memory_warning >= memory_critical raises ValueError."""
        with pytest.raises(ValueError, match=r"memory_warning.*must be < memory_critical"):
            AlertThresholds(memory_warning=95.0, memory_critical=90.0)


# ---------------------------------------------------------------------------
# DeploymentMonitor.collect_metrics() tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeploymentMonitorCollectMetrics:
    """Tests for the collect_metrics method."""

    def test_collect_metrics_returns_snapshot(self) -> None:
        """Test that collect_metrics returns a MetricsSnapshot."""
        monitor_mock = MagicMock()
        monitor_mock.get_memory_usage.return_value = MemoryInfo(
            rss=500_000_000, vms=1_000_000_000, percent=25.0
        )
        dm = DeploymentMonitor(
            resource_monitor=monitor_mock,
            disk_usage_func=lambda: 45.0,
        )
        snap = dm.collect_metrics()

        assert isinstance(snap, MetricsSnapshot)
        assert snap.cpu_usage == 25.0
        assert snap.memory_usage == 25.0
        assert snap.disk_usage == 45.0
        assert snap.timestamp > 0

    def test_collect_metrics_with_zero_disk(self) -> None:
        """Test collect_metrics when disk usage returns zero."""
        monitor_mock = MagicMock()
        monitor_mock.get_memory_usage.return_value = MemoryInfo(
            rss=100_000, vms=200_000, percent=1.0
        )
        dm = DeploymentMonitor(
            resource_monitor=monitor_mock,
            disk_usage_func=lambda: 0.0,
        )
        snap = dm.collect_metrics()
        assert snap.disk_usage == 0.0


# ---------------------------------------------------------------------------
# DeploymentMonitor.get_alerts() tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeploymentMonitorGetAlerts:
    """Tests for the get_alerts method."""

    def _make_monitor(self) -> DeploymentMonitor:
        """Create a DeploymentMonitor with a mocked ResourceMonitor."""
        monitor_mock = MagicMock()
        monitor_mock.get_memory_usage.return_value = MemoryInfo(
            rss=100_000, vms=200_000, percent=50.0
        )
        return DeploymentMonitor(
            resource_monitor=monitor_mock,
            disk_usage_func=lambda: 50.0,
        )

    def test_no_alerts_when_below_thresholds(self) -> None:
        """Test that no alerts are generated when all metrics are healthy."""
        dm = self._make_monitor()
        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=30.0,
            memory_usage=40.0,
            disk_usage=50.0,
            active_connections=10,
            processing_rate=5.0,
        )
        alerts = dm.get_alerts(AlertThresholds(), snapshot=snap)
        assert alerts == []

    def test_cpu_warning_alert(self) -> None:
        """Test WARNING alert when CPU exceeds cpu_warning threshold."""
        dm = self._make_monitor()
        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=75.0,
            memory_usage=40.0,
            disk_usage=50.0,
            active_connections=10,
            processing_rate=5.0,
        )
        alerts = dm.get_alerts(AlertThresholds(), snapshot=snap)

        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARNING
        assert alerts[0].metric == "cpu_usage"
        assert "75.0%" in alerts[0].message

    def test_cpu_critical_alert(self) -> None:
        """Test CRITICAL alert when CPU exceeds cpu_critical threshold."""
        dm = self._make_monitor()
        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=95.0,
            memory_usage=40.0,
            disk_usage=50.0,
            active_connections=10,
            processing_rate=5.0,
        )
        alerts = dm.get_alerts(AlertThresholds(), snapshot=snap)

        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.CRITICAL
        assert alerts[0].metric == "cpu_usage"

    def test_memory_warning_alert(self) -> None:
        """Test WARNING alert when memory exceeds memory_warning threshold."""
        dm = self._make_monitor()
        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=30.0,
            memory_usage=80.0,
            disk_usage=50.0,
            active_connections=10,
            processing_rate=5.0,
        )
        alerts = dm.get_alerts(AlertThresholds(), snapshot=snap)

        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARNING
        assert alerts[0].metric == "memory_usage"

    def test_memory_critical_alert(self) -> None:
        """Test CRITICAL alert when memory exceeds memory_critical threshold."""
        dm = self._make_monitor()
        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=30.0,
            memory_usage=95.0,
            disk_usage=50.0,
            active_connections=10,
            processing_rate=5.0,
        )
        alerts = dm.get_alerts(AlertThresholds(), snapshot=snap)

        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.CRITICAL
        assert alerts[0].metric == "memory_usage"

    def test_disk_warning_alert(self) -> None:
        """Test WARNING alert when disk usage exceeds disk_warning threshold."""
        dm = self._make_monitor()
        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=30.0,
            memory_usage=40.0,
            disk_usage=85.0,
            active_connections=10,
            processing_rate=5.0,
        )
        alerts = dm.get_alerts(AlertThresholds(), snapshot=snap)

        assert len(alerts) == 1
        assert alerts[0].level == AlertLevel.WARNING
        assert alerts[0].metric == "disk_usage"

    def test_multiple_alerts_simultaneously(self) -> None:
        """Test that multiple alerts fire when several thresholds are breached."""
        dm = self._make_monitor()
        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=92.0,
            memory_usage=92.0,
            disk_usage=90.0,
            active_connections=10,
            processing_rate=5.0,
        )
        alerts = dm.get_alerts(AlertThresholds(), snapshot=snap)

        # CPU critical + memory critical + disk warning = 3 alerts
        assert len(alerts) == 3
        metrics_found = {a.metric for a in alerts}
        assert metrics_found == {"cpu_usage", "memory_usage", "disk_usage"}

    def test_get_alerts_auto_collects_metrics(self) -> None:
        """Test that get_alerts collects metrics when no snapshot provided."""
        monitor_mock = MagicMock()
        monitor_mock.get_memory_usage.return_value = MemoryInfo(
            rss=100_000, vms=200_000, percent=50.0
        )
        dm = DeploymentMonitor(
            resource_monitor=monitor_mock,
            disk_usage_func=lambda: 50.0,
        )
        # No snapshot passed - should auto-collect
        alerts = dm.get_alerts(AlertThresholds())
        assert isinstance(alerts, list) and all(hasattr(a, "metric") for a in alerts)
        monitor_mock.get_memory_usage.assert_called_once()

    def test_critical_overrides_warning_for_same_metric(self) -> None:
        """Test that only CRITICAL fires when both thresholds are breached."""
        dm = self._make_monitor()
        # CPU at 95% exceeds both warning (70) and critical (90).
        # Only the CRITICAL alert should be generated, not both.
        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=95.0,
            memory_usage=40.0,
            disk_usage=40.0,
            active_connections=0,
            processing_rate=0.0,
        )
        alerts = dm.get_alerts(AlertThresholds(), snapshot=snap)
        cpu_alerts = [a for a in alerts if a.metric == "cpu_usage"]
        assert len(cpu_alerts) == 1
        assert cpu_alerts[0].level == AlertLevel.CRITICAL
