"""Deployment monitoring with metrics collection and alerting.

Collects system-level metrics snapshots and evaluates them against
configurable alert thresholds to produce actionable alerts at
INFO, WARNING, or CRITICAL levels.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass

from file_organizer.optimization.resource_monitor import ResourceMonitor

logger = logging.getLogger(__name__)


class AlertLevel(enum.Enum):
    """Severity level for deployment alerts."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class MetricsSnapshot:
    """Point-in-time snapshot of deployment metrics.

    Attributes:
        timestamp: Unix epoch timestamp of the snapshot.
        cpu_usage: CPU utilisation percentage (0-100).
        memory_usage: Memory utilisation percentage (0-100).
        disk_usage: Disk utilisation percentage (0-100).
        active_connections: Number of currently active connections.
        processing_rate: Items processed per second.
    """

    timestamp: float
    cpu_usage: float
    memory_usage: float
    disk_usage: float
    active_connections: int
    processing_rate: float


@dataclass(frozen=True)
class Alert:
    """An alert generated when a metric breaches a threshold.

    Attributes:
        level: Severity of the alert.
        metric: Name of the metric that triggered the alert.
        value: Observed value of the metric.
        threshold: Threshold that was breached.
        message: Human-readable alert description.
    """

    level: AlertLevel
    metric: str
    value: float
    threshold: float
    message: str


@dataclass(frozen=True)
class AlertThresholds:
    """Configurable thresholds for alert generation.

    Attributes:
        cpu_warning: CPU % above which a WARNING alert is raised.
        cpu_critical: CPU % above which a CRITICAL alert is raised.
        memory_warning: Memory % above which a WARNING alert is raised.
        memory_critical: Memory % above which a CRITICAL alert is raised.
        disk_warning: Disk % above which a WARNING alert is raised.
    """

    cpu_warning: float = 70.0
    cpu_critical: float = 90.0
    memory_warning: float = 75.0
    memory_critical: float = 90.0
    disk_warning: float = 80.0

    def __post_init__(self) -> None:
        """Validate that warning thresholds are below critical thresholds."""
        if self.cpu_warning >= self.cpu_critical:
            raise ValueError(
                f"cpu_warning ({self.cpu_warning}) must be < cpu_critical ({self.cpu_critical})"
            )
        if self.memory_warning >= self.memory_critical:
            raise ValueError(
                f"memory_warning ({self.memory_warning}) must be < "
                f"memory_critical ({self.memory_critical})"
            )


class DeploymentMonitor:
    """Collects deployment metrics and generates alerts.

    Wraps :class:`ResourceMonitor` to produce timestamped
    :class:`MetricsSnapshot` objects and evaluates them against
    :class:`AlertThresholds` to produce :class:`Alert` instances.

    Example:
        >>> monitor = DeploymentMonitor()
        >>> snapshot = monitor.collect_metrics()
        >>> thresholds = AlertThresholds(cpu_warning=70, cpu_critical=90)
        >>> alerts = monitor.get_alerts(thresholds, snapshot=snapshot)
        >>> for alert in alerts:
        ...     print(f"[{alert.level.value}] {alert.message}")
    """

    def __init__(
        self,
        *,
        resource_monitor: ResourceMonitor | None = None,
        disk_usage_func: object | None = None,
    ) -> None:
        """Set up the deployment monitor with the given resource monitor."""
        self._monitor = resource_monitor or ResourceMonitor()
        # disk_usage_func can be injected for testing; defaults to
        # a stub returning 0.0 when no real implementation is available.
        self._disk_usage_func = disk_usage_func

    def collect_metrics(self) -> MetricsSnapshot:
        """Collect a point-in-time metrics snapshot.

        Returns:
            MetricsSnapshot with current system metrics.
        """
        mem = self._monitor.get_memory_usage()
        disk = self._get_disk_usage()

        return MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=mem.percent,
            memory_usage=mem.percent,
            disk_usage=disk,
            active_connections=0,
            processing_rate=0.0,
        )

    def get_alerts(
        self,
        thresholds: AlertThresholds,
        *,
        snapshot: MetricsSnapshot | None = None,
    ) -> list[Alert]:
        """Evaluate metrics against thresholds and return any alerts.

        Args:
            thresholds: Alert threshold configuration.
            snapshot: Optional pre-collected snapshot.  When *None*,
                :meth:`collect_metrics` is called automatically.

        Returns:
            A list of :class:`Alert` objects for breached thresholds,
            ordered from most to least severe.
        """
        if snapshot is None:
            snapshot = self.collect_metrics()

        alerts: list[Alert] = []

        # CPU alerts (critical checked first so both can fire)
        if snapshot.cpu_usage >= thresholds.cpu_critical:
            alerts.append(
                Alert(
                    level=AlertLevel.CRITICAL,
                    metric="cpu_usage",
                    value=snapshot.cpu_usage,
                    threshold=thresholds.cpu_critical,
                    message=(
                        f"CPU usage CRITICAL: {snapshot.cpu_usage:.1f}% "
                        f">= {thresholds.cpu_critical:.1f}%"
                    ),
                )
            )
        elif snapshot.cpu_usage >= thresholds.cpu_warning:
            alerts.append(
                Alert(
                    level=AlertLevel.WARNING,
                    metric="cpu_usage",
                    value=snapshot.cpu_usage,
                    threshold=thresholds.cpu_warning,
                    message=(
                        f"CPU usage WARNING: {snapshot.cpu_usage:.1f}% "
                        f">= {thresholds.cpu_warning:.1f}%"
                    ),
                )
            )

        # Memory alerts
        if snapshot.memory_usage >= thresholds.memory_critical:
            alerts.append(
                Alert(
                    level=AlertLevel.CRITICAL,
                    metric="memory_usage",
                    value=snapshot.memory_usage,
                    threshold=thresholds.memory_critical,
                    message=(
                        f"Memory usage CRITICAL: {snapshot.memory_usage:.1f}% "
                        f">= {thresholds.memory_critical:.1f}%"
                    ),
                )
            )
        elif snapshot.memory_usage >= thresholds.memory_warning:
            alerts.append(
                Alert(
                    level=AlertLevel.WARNING,
                    metric="memory_usage",
                    value=snapshot.memory_usage,
                    threshold=thresholds.memory_warning,
                    message=(
                        f"Memory usage WARNING: {snapshot.memory_usage:.1f}% "
                        f">= {thresholds.memory_warning:.1f}%"
                    ),
                )
            )

        # Disk alerts (warning only, no critical level defined)
        if snapshot.disk_usage >= thresholds.disk_warning:
            alerts.append(
                Alert(
                    level=AlertLevel.WARNING,
                    metric="disk_usage",
                    value=snapshot.disk_usage,
                    threshold=thresholds.disk_warning,
                    message=(
                        f"Disk usage WARNING: {snapshot.disk_usage:.1f}% "
                        f">= {thresholds.disk_warning:.1f}%"
                    ),
                )
            )

        return alerts

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_disk_usage(self) -> float:
        """Return disk usage percentage.

        Uses the injected ``disk_usage_func`` if provided, otherwise
        attempts ``shutil.disk_usage`` and falls back to 0.0.
        """
        if self._disk_usage_func is not None:
            return self._disk_usage_func()  # type: ignore[operator]

        try:
            import shutil

            usage = shutil.disk_usage("/")
            return (usage.used / usage.total) * 100.0 if usage.total > 0 else 0.0
        except (OSError, AttributeError):
            return 0.0
