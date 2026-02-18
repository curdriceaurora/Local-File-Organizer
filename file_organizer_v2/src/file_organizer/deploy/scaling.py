"""Auto-scaling configuration and decision engine for containerized deployments.

Evaluates system resource metrics against configurable thresholds to produce
scaling decisions (scale up, scale down, or no change) while respecting
cooldown periods and replica bounds.
"""

from __future__ import annotations

import enum
import logging
import time
from dataclasses import dataclass

from file_organizer.optimization.resource_monitor import ResourceMonitor

logger = logging.getLogger(__name__)


class ScalingAction(enum.Enum):
    """Possible scaling actions."""

    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    NO_CHANGE = "no_change"


@dataclass(frozen=True)
class ScalingConfig:
    """Configuration for the auto-scaler.

    Attributes:
        min_replicas: Minimum number of service replicas.
        max_replicas: Maximum number of service replicas.
        target_cpu_percent: Desired average CPU utilisation percentage.
        target_memory_percent: Desired average memory utilisation percentage.
        scale_up_threshold: CPU/memory percentage above which to add replicas.
        scale_down_threshold: CPU/memory percentage below which to remove replicas.
        cooldown_seconds: Minimum seconds between consecutive scaling actions.
    """

    min_replicas: int = 1
    max_replicas: int = 10
    target_cpu_percent: float = 70.0
    target_memory_percent: float = 75.0
    scale_up_threshold: float = 80.0
    scale_down_threshold: float = 30.0
    cooldown_seconds: int = 300

    def __post_init__(self) -> None:
        """Validate configuration values."""
        if self.min_replicas < 1:
            raise ValueError(f"min_replicas must be >= 1, got {self.min_replicas}")
        if self.max_replicas < self.min_replicas:
            raise ValueError(
                f"max_replicas ({self.max_replicas}) must be >= min_replicas ({self.min_replicas})"
            )
        if not 0.0 < self.scale_down_threshold < self.scale_up_threshold <= 100.0:
            raise ValueError(
                f"Thresholds must satisfy 0 < scale_down ({self.scale_down_threshold}) "
                f"< scale_up ({self.scale_up_threshold}) <= 100"
            )
        if self.cooldown_seconds < 0:
            raise ValueError(f"cooldown_seconds must be >= 0, got {self.cooldown_seconds}")


@dataclass(frozen=True)
class ScalingMetrics:
    """Current resource utilisation metrics used for scaling decisions.

    Attributes:
        cpu_percent: Current CPU utilisation percentage (0-100).
        memory_percent: Current memory utilisation percentage (0-100).
        request_rate: Requests per second being processed.
        queue_depth: Number of requests waiting in queue.
    """

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    request_rate: float = 0.0
    queue_depth: int = 0


@dataclass(frozen=True)
class ScalingDecision:
    """Result of a scaling evaluation.

    Attributes:
        action: The recommended scaling action.
        current_replicas: Current number of replicas.
        desired_replicas: Recommended number of replicas after action.
        reason: Human-readable explanation for the decision.
    """

    action: ScalingAction
    current_replicas: int
    desired_replicas: int
    reason: str


class AutoScaler:
    """Evaluates metrics and produces scaling decisions.

    Uses a :class:`ResourceMonitor` to collect live system metrics and
    compares them against the thresholds defined in :class:`ScalingConfig`
    to determine whether services should be scaled up, down, or left
    unchanged.

    Example:
        >>> config = ScalingConfig(min_replicas=1, max_replicas=5)
        >>> scaler = AutoScaler(config)
        >>> decision = scaler.evaluate(current_replicas=2)
        >>> print(decision.action)
    """

    def __init__(
        self,
        config: ScalingConfig,
        *,
        resource_monitor: ResourceMonitor | None = None,
        clock: object | None = None,
    ) -> None:
        self._config = config
        self._monitor = resource_monitor or ResourceMonitor()
        self._clock = clock  # injectable for testing
        self._last_scale_time: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def config(self) -> ScalingConfig:
        """Return the current scaling configuration."""
        return self._config

    def get_metrics(self) -> ScalingMetrics:
        """Collect current resource metrics from the system.

        Returns:
            ScalingMetrics with live CPU and memory data.
        """
        mem = self._monitor.get_memory_usage()
        # CPU percentage is approximated from memory pressure in the
        # absence of a dedicated CPU sampler; real deployments would
        # plug in container-level cAdvisor or cgroup metrics here.
        return ScalingMetrics(
            cpu_percent=mem.percent,
            memory_percent=mem.percent,
            request_rate=0.0,
            queue_depth=0,
        )

    def evaluate(
        self,
        current_replicas: int,
        *,
        metrics: ScalingMetrics | None = None,
    ) -> ScalingDecision:
        """Evaluate whether scaling is needed.

        Args:
            current_replicas: The number of replicas currently running.
            metrics: Optional pre-collected metrics.  When *None*,
                :meth:`get_metrics` is called automatically.

        Returns:
            A :class:`ScalingDecision` describing the recommended action.
        """
        if metrics is None:
            metrics = self.get_metrics()

        now = self._now()
        elapsed = now - self._last_scale_time
        in_cooldown = elapsed < self._config.cooldown_seconds

        # --- scale-up check ---
        if (
            metrics.cpu_percent > self._config.scale_up_threshold
            or metrics.memory_percent > self._config.scale_up_threshold
        ):
            if current_replicas >= self._config.max_replicas:
                return ScalingDecision(
                    action=ScalingAction.NO_CHANGE,
                    current_replicas=current_replicas,
                    desired_replicas=current_replicas,
                    reason=(
                        f"Scale-up warranted (cpu={metrics.cpu_percent:.1f}%, "
                        f"mem={metrics.memory_percent:.1f}%) but already at "
                        f"max_replicas ({self._config.max_replicas})"
                    ),
                )
            if in_cooldown:
                return ScalingDecision(
                    action=ScalingAction.NO_CHANGE,
                    current_replicas=current_replicas,
                    desired_replicas=current_replicas,
                    reason=(
                        f"Scale-up warranted but in cooldown "
                        f"({elapsed:.0f}s / {self._config.cooldown_seconds}s)"
                    ),
                )
            desired = min(current_replicas + 1, self._config.max_replicas)
            self._last_scale_time = now
            return ScalingDecision(
                action=ScalingAction.SCALE_UP,
                current_replicas=current_replicas,
                desired_replicas=desired,
                reason=(
                    f"CPU {metrics.cpu_percent:.1f}% or memory "
                    f"{metrics.memory_percent:.1f}% exceeded scale-up "
                    f"threshold {self._config.scale_up_threshold:.1f}%"
                ),
            )

        # --- scale-down check ---
        if (
            metrics.cpu_percent < self._config.scale_down_threshold
            and metrics.memory_percent < self._config.scale_down_threshold
        ):
            if current_replicas <= self._config.min_replicas:
                return ScalingDecision(
                    action=ScalingAction.NO_CHANGE,
                    current_replicas=current_replicas,
                    desired_replicas=current_replicas,
                    reason=(
                        f"Scale-down warranted (cpu={metrics.cpu_percent:.1f}%, "
                        f"mem={metrics.memory_percent:.1f}%) but already at "
                        f"min_replicas ({self._config.min_replicas})"
                    ),
                )
            if in_cooldown:
                return ScalingDecision(
                    action=ScalingAction.NO_CHANGE,
                    current_replicas=current_replicas,
                    desired_replicas=current_replicas,
                    reason=(
                        f"Scale-down warranted but in cooldown "
                        f"({elapsed:.0f}s / {self._config.cooldown_seconds}s)"
                    ),
                )
            desired = max(current_replicas - 1, self._config.min_replicas)
            self._last_scale_time = now
            return ScalingDecision(
                action=ScalingAction.SCALE_DOWN,
                current_replicas=current_replicas,
                desired_replicas=desired,
                reason=(
                    f"CPU {metrics.cpu_percent:.1f}% and memory "
                    f"{metrics.memory_percent:.1f}% below scale-down "
                    f"threshold {self._config.scale_down_threshold:.1f}%"
                ),
            )

        # --- within target range ---
        return ScalingDecision(
            action=ScalingAction.NO_CHANGE,
            current_replicas=current_replicas,
            desired_replicas=current_replicas,
            reason=(
                f"Metrics within target range "
                f"(cpu={metrics.cpu_percent:.1f}%, "
                f"mem={metrics.memory_percent:.1f}%)"
            ),
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now(self) -> float:
        """Return current monotonic time (overridable for testing)."""
        if self._clock is not None and hasattr(self._clock, "time"):
            return self._clock.time()  # type: ignore[union-attr]
        return time.monotonic()
