"""End-to-end integration tests for the deploy subsystem.

These exercise real code paths rather than mocking the boundaries:

- :class:`ComposeScaler` runs a real ``docker-compose`` subprocess by
  putting a fake executable on ``PATH``; the fake logs its argv so we can
  assert the exact subcommand formatting and emits real ``ps --format
  json`` output that the parser counts.
- :class:`AutoScaler` and :class:`DeploymentMonitor` collect live metrics
  through a real :class:`ResourceMonitor` and real ``shutil.disk_usage``,
  then run the full decision/alert evaluation.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from file_organizer.deploy.compose_scaler import ComposeScaler
from file_organizer.deploy.monitoring import (
    AlertLevel,
    AlertThresholds,
    DeploymentMonitor,
    MetricsSnapshot,
)
from file_organizer.deploy.scaling import (
    AutoScaler,
    ScalingAction,
    ScalingConfig,
    ScalingMetrics,
)

pytestmark = [pytest.mark.integration, pytest.mark.ci]

pytestmark_windows = pytest.mark.skipif(
    sys.platform == "win32",
    reason="fake docker-compose shell shim is POSIX-only",
)


# ---------------------------------------------------------------------------
# ComposeScaler — real subprocess against a fake docker-compose
# ---------------------------------------------------------------------------


def _install_fake_compose(
    bin_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    replicas: int = 2,
    return_code: int = 0,
    ps_return_code: int = 0,
    log_file: Path | None = None,
) -> Path:
    """Write an executable fake ``docker-compose`` onto a temp PATH entry.

    The shim logs its argv (one arg per line) to *log_file*. For ``ps``
    invocations it emits *replicas* JSON lines and exits *ps_return_code*
    (so the non-zero-exit query branch can be exercised). All other
    invocations exit with *return_code*.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_file or (bin_dir / "invocation.log")
    script = bin_dir / "docker-compose"
    ps_lines = "\n".join(
        f'echo \'{{"Service":"file-organizer","State":"running","Index":{i}}}\''
        for i in range(1, replicas + 1)
    )
    script.write_text(
        "#!/usr/bin/env bash\n"
        f'printf "%s\\n" "$@" >> "{log_file}"\n'
        'for a in "$@"; do\n'
        '  if [ "$a" = "ps" ]; then\n'
        f"    {ps_lines}\n"
        f"    exit {ps_return_code}\n"
        "  fi\n"
        "done\n"
        f"exit {return_code}\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return log_file


@pytestmark_windows
def test_scale_service_builds_and_runs_real_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """scale_service runs docker-compose and formats the subcommand correctly."""
    log_file = _install_fake_compose(tmp_path / "bin", monkeypatch, return_code=0)

    scaler = ComposeScaler(compose_file="docker-compose.yml", project_name="fo")
    assert scaler.scale_service("file-organizer", 3) is True

    logged = log_file.read_text(encoding="utf-8").splitlines()
    # Exact subcommand formatting: -f <file> -p <project> up -d --scale svc=N --no-recreate svc
    assert logged == [
        "-f",
        "docker-compose.yml",
        "-p",
        "fo",
        "up",
        "-d",
        "--scale",
        "file-organizer=3",
        "--no-recreate",
        "file-organizer",
    ]


@pytestmark_windows
def test_scale_service_reports_failure_on_nonzero_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-zero docker-compose exit surfaces as False."""
    _install_fake_compose(tmp_path / "bin", monkeypatch, return_code=1)
    scaler = ComposeScaler()
    assert scaler.scale_service("file-organizer", 2) is False


@pytestmark_windows
def test_get_service_count_parses_ps_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """get_service_count counts the JSON lines emitted by docker-compose ps."""
    log_file = _install_fake_compose(tmp_path / "bin", monkeypatch, replicas=4)
    scaler = ComposeScaler(compose_file="stack.yml")

    assert scaler.get_service_count("file-organizer") == 4

    logged = log_file.read_text(encoding="utf-8").splitlines()
    assert logged == ["-f", "stack.yml", "ps", "--format", "json", "file-organizer"]


@pytestmark_windows
def test_get_service_count_zero_when_ps_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ps query that exits non-zero yields a count of 0, not an exception."""
    _install_fake_compose(tmp_path / "bin", monkeypatch, replicas=3, ps_return_code=1)
    scaler = ComposeScaler()
    assert scaler.get_service_count("file-organizer") == 0


@pytestmark_windows
def test_get_service_count_zero_when_executable_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing docker-compose executable yields a count of 0, not an exception."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    scaler = ComposeScaler()
    assert scaler.get_service_count("file-organizer") == 0


def test_scale_service_rejects_negative_replicas() -> None:
    """Negative replica counts fail fast before any subprocess call."""
    scaler = ComposeScaler()
    with pytest.raises(ValueError, match="replicas must be >= 0"):
        scaler.scale_service("file-organizer", -1)


# ---------------------------------------------------------------------------
# AutoScaler — real ResourceMonitor + decision engine
# ---------------------------------------------------------------------------


class _FakeClock:
    """A controllable clock for cooldown tests.

    ``AutoScaler`` seeds ``_last_scale_time`` to 0.0 and compares against
    ``time.monotonic()`` by default; on a freshly booted host monotonic
    time can be below the cooldown window, so the first evaluation would
    spuriously read as "in cooldown". Injecting a clock makes the elapsed
    time deterministic.
    """

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def time(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def test_autoscaler_collects_live_metrics() -> None:
    """get_metrics() reads real process memory via ResourceMonitor."""
    scaler = AutoScaler(ScalingConfig())
    metrics = scaler.get_metrics()
    assert 0.0 <= metrics.memory_percent <= 100.0
    assert metrics.cpu_percent == metrics.memory_percent


def test_autoscaler_scale_up_and_cooldown() -> None:
    """High load scales up once, then the cooldown blocks the next action."""
    config = ScalingConfig(min_replicas=1, max_replicas=5, cooldown_seconds=300)
    clock = _FakeClock(start=10_000.0)  # well past the cooldown from the 0.0 seed
    scaler = AutoScaler(config, clock=clock)
    hot = ScalingMetrics(cpu_percent=95.0, memory_percent=95.0)

    first = scaler.evaluate(current_replicas=2, metrics=hot)
    assert first.action is ScalingAction.SCALE_UP
    assert first.desired_replicas == 3

    # Re-evaluating without advancing the clock: still hot, but the cooldown
    # (0s elapsed < 300s) suppresses the action.
    second = scaler.evaluate(current_replicas=3, metrics=hot)
    assert second.action is ScalingAction.NO_CHANGE
    assert "cooldown" in second.reason

    # Once the cooldown elapses, scaling resumes.
    clock.advance(301)
    third = scaler.evaluate(current_replicas=3, metrics=hot)
    assert third.action is ScalingAction.SCALE_UP


def test_autoscaler_respects_max_replicas() -> None:
    """At max replicas, a scale-up trigger produces NO_CHANGE."""
    config = ScalingConfig(min_replicas=1, max_replicas=3)
    scaler = AutoScaler(config)
    decision = scaler.evaluate(
        current_replicas=3,
        metrics=ScalingMetrics(cpu_percent=99.0, memory_percent=99.0),
    )
    assert decision.action is ScalingAction.NO_CHANGE
    assert "max_replicas" in decision.reason


def test_autoscaler_scale_down_and_min_bound() -> None:
    """Low load scales down, and never below min_replicas."""
    config = ScalingConfig(min_replicas=1, max_replicas=5, cooldown_seconds=0)
    scaler = AutoScaler(config)
    idle = ScalingMetrics(cpu_percent=5.0, memory_percent=5.0)

    down = scaler.evaluate(current_replicas=3, metrics=idle)
    assert down.action is ScalingAction.SCALE_DOWN
    assert down.desired_replicas == 2

    at_min = scaler.evaluate(current_replicas=1, metrics=idle)
    assert at_min.action is ScalingAction.NO_CHANGE
    assert "min_replicas" in at_min.reason


def test_autoscaler_scale_down_cooldown() -> None:
    """After a scale-down, the cooldown suppresses the next scale-down."""
    config = ScalingConfig(min_replicas=1, max_replicas=5, cooldown_seconds=300)
    clock = _FakeClock(start=10_000.0)
    scaler = AutoScaler(config, clock=clock)
    idle = ScalingMetrics(cpu_percent=5.0, memory_percent=5.0)

    first = scaler.evaluate(current_replicas=4, metrics=idle)
    assert first.action is ScalingAction.SCALE_DOWN

    second = scaler.evaluate(current_replicas=3, metrics=idle)
    assert second.action is ScalingAction.NO_CHANGE
    assert "cooldown" in second.reason


def test_autoscaler_evaluate_uses_live_metrics_when_none() -> None:
    """evaluate() with no metrics collects them live via ResourceMonitor."""
    scaler = AutoScaler(ScalingConfig())
    # No metrics passed: the metrics=None branch must call get_metrics().
    decision = scaler.evaluate(current_replicas=2)
    assert decision.action in {
        ScalingAction.SCALE_UP,
        ScalingAction.SCALE_DOWN,
        ScalingAction.NO_CHANGE,
    }
    assert decision.current_replicas == 2


def test_autoscaler_within_target_range_no_change() -> None:
    """Metrics between the thresholds yield NO_CHANGE."""
    scaler = AutoScaler(ScalingConfig(scale_down_threshold=30.0, scale_up_threshold=80.0))
    decision = scaler.evaluate(
        current_replicas=2,
        metrics=ScalingMetrics(cpu_percent=50.0, memory_percent=50.0),
    )
    assert decision.action is ScalingAction.NO_CHANGE
    assert "target range" in decision.reason


def test_scaling_config_validation() -> None:
    """Invalid scaling configs fail closed at construction."""
    with pytest.raises(ValueError, match="min_replicas"):
        ScalingConfig(min_replicas=0)
    with pytest.raises(ValueError, match="max_replicas"):
        ScalingConfig(min_replicas=5, max_replicas=2)
    with pytest.raises(ValueError, match="Thresholds"):
        ScalingConfig(scale_down_threshold=90.0, scale_up_threshold=80.0)


# ---------------------------------------------------------------------------
# DeploymentMonitor — real metrics collection + alert evaluation
# ---------------------------------------------------------------------------


def test_monitor_collects_real_metrics() -> None:
    """collect_metrics() reads real memory and disk usage."""
    monitor = DeploymentMonitor()
    snapshot = monitor.collect_metrics()
    assert snapshot.timestamp > 0
    assert 0.0 <= snapshot.memory_usage <= 100.0
    assert 0.0 <= snapshot.disk_usage <= 100.0


def test_monitor_emits_critical_and_warning_alerts() -> None:
    """A hot snapshot produces CPU-critical, memory-warning, and disk-warning alerts."""
    monitor = DeploymentMonitor()
    thresholds = AlertThresholds(
        cpu_warning=70.0,
        cpu_critical=90.0,
        memory_warning=75.0,
        memory_critical=95.0,
        disk_warning=80.0,
    )
    snapshot = MetricsSnapshot(
        timestamp=1.0,
        cpu_usage=92.0,  # critical
        memory_usage=80.0,  # warning (>=75, <95)
        disk_usage=85.0,  # warning
        active_connections=0,
        processing_rate=0.0,
    )
    alerts = monitor.get_alerts(thresholds, snapshot=snapshot)
    by_metric = {a.metric: a for a in alerts}

    assert by_metric["cpu_usage"].level is AlertLevel.CRITICAL
    assert by_metric["memory_usage"].level is AlertLevel.WARNING
    assert by_metric["disk_usage"].level is AlertLevel.WARNING


def test_monitor_no_alerts_when_healthy() -> None:
    """A calm snapshot produces no alerts."""
    monitor = DeploymentMonitor(disk_usage_func=lambda: 10.0)
    snapshot = MetricsSnapshot(
        timestamp=1.0,
        cpu_usage=20.0,
        memory_usage=25.0,
        disk_usage=10.0,
        active_connections=0,
        processing_rate=0.0,
    )
    assert monitor.get_alerts(AlertThresholds(), snapshot=snapshot) == []


def test_monitor_injected_disk_usage_func() -> None:
    """An injected disk usage function is used verbatim by collect_metrics."""
    monitor = DeploymentMonitor(disk_usage_func=lambda: 42.5)
    snapshot = monitor.collect_metrics()
    assert snapshot.disk_usage == 42.5


def test_alert_thresholds_validation() -> None:
    """Warning thresholds must sit below critical thresholds."""
    with pytest.raises(ValueError, match="cpu_warning"):
        AlertThresholds(cpu_warning=95.0, cpu_critical=90.0)
    with pytest.raises(ValueError, match="memory_warning"):
        AlertThresholds(memory_warning=95.0, memory_critical=90.0)
