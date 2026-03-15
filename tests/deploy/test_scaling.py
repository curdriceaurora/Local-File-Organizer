"""Tests for auto-scaling configuration and decision engine."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.deploy.scaling import (
    AutoScaler,
    ScalingAction,
    ScalingConfig,
    ScalingDecision,
    ScalingMetrics,
)
from file_organizer.optimization.resource_monitor import MemoryInfo

# ---------------------------------------------------------------------------
# ScalingConfig validation tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScalingConfig:
    """Tests for ScalingConfig dataclass validation."""

    def test_default_config(self) -> None:
        """Test that default configuration is valid."""
        config = ScalingConfig()
        assert config.min_replicas == 1
        assert config.max_replicas == 10
        assert config.target_cpu_percent == 70.0
        assert config.target_memory_percent == 75.0
        assert config.scale_up_threshold == 80.0
        assert config.scale_down_threshold == 30.0
        assert config.cooldown_seconds == 300

    def test_custom_config(self) -> None:
        """Test creating a config with custom values."""
        config = ScalingConfig(
            min_replicas=2,
            max_replicas=20,
            target_cpu_percent=60.0,
            target_memory_percent=65.0,
            scale_up_threshold=85.0,
            scale_down_threshold=20.0,
            cooldown_seconds=120,
        )
        assert config.min_replicas == 2
        assert config.max_replicas == 20
        assert config.cooldown_seconds == 120

    def test_config_frozen(self) -> None:
        """Test that ScalingConfig is immutable."""
        config = ScalingConfig()
        with pytest.raises(AttributeError):
            config.min_replicas = 5  # type: ignore[misc]

    def test_invalid_min_replicas(self) -> None:
        """Test that min_replicas < 1 raises ValueError."""
        with pytest.raises(ValueError, match="min_replicas must be >= 1"):
            ScalingConfig(min_replicas=0)

    def test_invalid_max_less_than_min(self) -> None:
        """Test that max_replicas < min_replicas raises ValueError."""
        with pytest.raises(ValueError, match=r"max_replicas.*must be >= min_replicas"):
            ScalingConfig(min_replicas=5, max_replicas=3)

    def test_invalid_thresholds_reversed(self) -> None:
        """Test that scale_down >= scale_up raises ValueError."""
        with pytest.raises(ValueError, match="Thresholds must satisfy"):
            ScalingConfig(scale_up_threshold=30.0, scale_down_threshold=80.0)

    def test_invalid_thresholds_equal(self) -> None:
        """Test that equal thresholds raise ValueError."""
        with pytest.raises(ValueError, match="Thresholds must satisfy"):
            ScalingConfig(scale_up_threshold=50.0, scale_down_threshold=50.0)

    def test_invalid_negative_cooldown(self) -> None:
        """Test that negative cooldown raises ValueError."""
        with pytest.raises(ValueError, match="cooldown_seconds must be >= 0"):
            ScalingConfig(cooldown_seconds=-1)

    def test_zero_cooldown_allowed(self) -> None:
        """Test that zero cooldown is allowed."""
        config = ScalingConfig(cooldown_seconds=0)
        assert config.cooldown_seconds == 0


# ---------------------------------------------------------------------------
# ScalingMetrics tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScalingMetrics:
    """Tests for ScalingMetrics dataclass."""

    def test_default_metrics(self) -> None:
        """Test that default metrics are all zero."""
        metrics = ScalingMetrics()
        assert metrics.cpu_percent == 0.0
        assert metrics.memory_percent == 0.0
        assert metrics.request_rate == 0.0
        assert metrics.queue_depth == 0

    def test_custom_metrics(self) -> None:
        """Test creating metrics with custom values."""
        metrics = ScalingMetrics(
            cpu_percent=75.0,
            memory_percent=60.0,
            request_rate=150.5,
            queue_depth=42,
        )
        assert metrics.cpu_percent == 75.0
        assert metrics.queue_depth == 42

    def test_metrics_frozen(self) -> None:
        """Test that ScalingMetrics is immutable."""
        metrics = ScalingMetrics()
        with pytest.raises(AttributeError):
            metrics.cpu_percent = 50.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ScalingDecision tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestScalingDecision:
    """Tests for ScalingDecision dataclass."""

    def test_scale_up_decision(self) -> None:
        """Test creating a scale-up decision."""
        decision = ScalingDecision(
            action=ScalingAction.SCALE_UP,
            current_replicas=2,
            desired_replicas=3,
            reason="High CPU",
        )
        assert decision.action == ScalingAction.SCALE_UP
        assert decision.desired_replicas == 3

    def test_no_change_decision(self) -> None:
        """Test creating a no-change decision."""
        decision = ScalingDecision(
            action=ScalingAction.NO_CHANGE,
            current_replicas=2,
            desired_replicas=2,
            reason="Within range",
        )
        assert decision.action == ScalingAction.NO_CHANGE
        assert decision.current_replicas == decision.desired_replicas


# ---------------------------------------------------------------------------
# AutoScaler.evaluate() tests
# ---------------------------------------------------------------------------


class _FakeClock:
    """Deterministic clock for testing cooldown logic."""

    def __init__(self, start: float = 0.0) -> None:
        self._time = start

    def time(self) -> float:
        return self._time

    def advance(self, seconds: float) -> None:
        self._time += seconds


@pytest.mark.unit
class TestAutoScalerEvaluate:
    """Tests for the AutoScaler.evaluate method."""

    def _make_scaler(
        self,
        *,
        config: ScalingConfig | None = None,
        clock: _FakeClock | None = None,
    ) -> AutoScaler:
        cfg = config or ScalingConfig(cooldown_seconds=60)
        clk = clock or _FakeClock(start=1000.0)
        monitor = MagicMock()
        return AutoScaler(cfg, resource_monitor=monitor, clock=clk)

    def test_scale_up_on_high_cpu(self) -> None:
        """Test that high CPU triggers scale-up."""
        scaler = self._make_scaler()
        metrics = ScalingMetrics(cpu_percent=90.0, memory_percent=50.0)
        decision = scaler.evaluate(current_replicas=2, metrics=metrics)

        assert decision.action == ScalingAction.SCALE_UP
        assert decision.desired_replicas == 3
        assert "exceeded scale-up threshold" in decision.reason

    def test_scale_up_on_high_memory(self) -> None:
        """Test that high memory triggers scale-up."""
        scaler = self._make_scaler()
        metrics = ScalingMetrics(cpu_percent=50.0, memory_percent=95.0)
        decision = scaler.evaluate(current_replicas=1, metrics=metrics)

        assert decision.action == ScalingAction.SCALE_UP
        assert decision.desired_replicas == 2

    def test_scale_down_on_low_utilisation(self) -> None:
        """Test that low utilisation triggers scale-down."""
        scaler = self._make_scaler()
        metrics = ScalingMetrics(cpu_percent=10.0, memory_percent=15.0)
        decision = scaler.evaluate(current_replicas=5, metrics=metrics)

        assert decision.action == ScalingAction.SCALE_DOWN
        assert decision.desired_replicas == 4
        assert "below scale-down threshold" in decision.reason

    def test_no_change_within_range(self) -> None:
        """Test no action when metrics are within thresholds."""
        scaler = self._make_scaler()
        metrics = ScalingMetrics(cpu_percent=50.0, memory_percent=50.0)
        decision = scaler.evaluate(current_replicas=3, metrics=metrics)

        assert decision.action == ScalingAction.NO_CHANGE
        assert decision.desired_replicas == 3
        assert "within target range" in decision.reason

    def test_scale_up_capped_at_max_replicas(self) -> None:
        """Test that scale-up does not exceed max_replicas."""
        config = ScalingConfig(max_replicas=3, cooldown_seconds=0)
        scaler = self._make_scaler(config=config)
        metrics = ScalingMetrics(cpu_percent=95.0, memory_percent=95.0)
        decision = scaler.evaluate(current_replicas=3, metrics=metrics)

        assert decision.action == ScalingAction.NO_CHANGE
        assert decision.desired_replicas == 3
        assert "already at max_replicas" in decision.reason

    def test_scale_down_capped_at_min_replicas(self) -> None:
        """Test that scale-down does not go below min_replicas."""
        config = ScalingConfig(min_replicas=2, cooldown_seconds=0)
        scaler = self._make_scaler(config=config)
        metrics = ScalingMetrics(cpu_percent=5.0, memory_percent=5.0)
        decision = scaler.evaluate(current_replicas=2, metrics=metrics)

        assert decision.action == ScalingAction.NO_CHANGE
        assert decision.desired_replicas == 2
        assert "already at min_replicas" in decision.reason

    def test_cooldown_prevents_scale_up(self) -> None:
        """Test that cooldown period prevents consecutive scale-ups."""
        clock = _FakeClock(start=1000.0)
        config = ScalingConfig(cooldown_seconds=300)
        scaler = self._make_scaler(config=config, clock=clock)

        high = ScalingMetrics(cpu_percent=95.0, memory_percent=50.0)

        # First scale-up should succeed
        d1 = scaler.evaluate(current_replicas=2, metrics=high)
        assert d1.action == ScalingAction.SCALE_UP

        # Second scale-up within cooldown should be blocked
        clock.advance(60)  # only 60s, cooldown is 300s
        d2 = scaler.evaluate(current_replicas=3, metrics=high)
        assert d2.action == ScalingAction.NO_CHANGE
        assert "cooldown" in d2.reason

    def test_cooldown_expires_allows_scale_up(self) -> None:
        """Test that scaling works again after cooldown expires."""
        clock = _FakeClock(start=1000.0)
        config = ScalingConfig(cooldown_seconds=300)
        scaler = self._make_scaler(config=config, clock=clock)

        high = ScalingMetrics(cpu_percent=95.0, memory_percent=50.0)

        d1 = scaler.evaluate(current_replicas=2, metrics=high)
        assert d1.action == ScalingAction.SCALE_UP

        clock.advance(301)
        d2 = scaler.evaluate(current_replicas=3, metrics=high)
        assert d2.action == ScalingAction.SCALE_UP
        assert d2.desired_replicas == 4

    def test_cooldown_prevents_scale_down(self) -> None:
        """Test that cooldown period prevents consecutive scale-downs."""
        clock = _FakeClock(start=1000.0)
        config = ScalingConfig(cooldown_seconds=300)
        scaler = self._make_scaler(config=config, clock=clock)

        low = ScalingMetrics(cpu_percent=5.0, memory_percent=5.0)

        d1 = scaler.evaluate(current_replicas=5, metrics=low)
        assert d1.action == ScalingAction.SCALE_DOWN

        clock.advance(100)
        d2 = scaler.evaluate(current_replicas=4, metrics=low)
        assert d2.action == ScalingAction.NO_CHANGE
        assert "cooldown" in d2.reason

    def test_get_metrics_delegates_to_monitor(self) -> None:
        """Test that get_metrics calls ResourceMonitor."""
        monitor = MagicMock()
        monitor.get_memory_usage.return_value = MemoryInfo(
            rss=1_000_000, vms=2_000_000, percent=42.5
        )
        scaler = AutoScaler(ScalingConfig(), resource_monitor=monitor)
        metrics = scaler.get_metrics()

        assert metrics.cpu_percent == 42.5
        assert metrics.memory_percent == 42.5
        monitor.get_memory_usage.assert_called_once()

    def test_evaluate_auto_collects_metrics(self) -> None:
        """Test that evaluate collects metrics when none provided."""
        monitor = MagicMock()
        monitor.get_memory_usage.return_value = MemoryInfo(
            rss=1_000_000, vms=2_000_000, percent=50.0
        )
        scaler = AutoScaler(
            ScalingConfig(cooldown_seconds=0),
            resource_monitor=monitor,
        )
        decision = scaler.evaluate(current_replicas=2)

        assert decision.action == ScalingAction.NO_CHANGE
        monitor.get_memory_usage.assert_called_once()

    def test_config_property(self) -> None:
        """Test that the config property returns the configuration."""
        config = ScalingConfig(min_replicas=3)
        scaler = self._make_scaler(config=config)
        assert scaler.config.min_replicas == 3

    def test_scaling_action_enum_values(self) -> None:
        """Test ScalingAction enum has expected values."""
        assert ScalingAction.SCALE_UP.value == "scale_up"
        assert ScalingAction.SCALE_DOWN.value == "scale_down"
        assert ScalingAction.NO_CHANGE.value == "no_change"
