"""Coverage tests for infrastructure, deploy, events, config, and other backend modules.

Targets comprehensive statement and branch coverage for low-coverage files
identified in the coverage gap analysis.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# ===========================================================================
# 1. deploy/config.py
# ===========================================================================


class TestDeploymentConfig:
    """Tests for DeploymentConfig initialization and properties."""

    def test_default_initialization(self):
        from file_organizer.deploy.config import DeploymentConfig

        cfg = DeploymentConfig()
        assert cfg.environment == "dev"
        assert cfg.log_level == "DEBUG"
        assert cfg.max_workers == 2
        assert cfg.port == 8000
        assert cfg.is_development is True
        assert cfg.is_production is False

    def test_prod_environment(self):
        from file_organizer.deploy.config import DeploymentConfig

        cfg = DeploymentConfig(environment="prod", log_level="WARNING", max_workers=8)
        assert cfg.is_production is True
        assert cfg.is_development is False

    def test_staging_environment(self):
        from file_organizer.deploy.config import DeploymentConfig

        cfg = DeploymentConfig(environment="staging", log_level="INFO", max_workers=4)
        assert cfg.environment == "staging"

    def test_invalid_environment(self):
        from file_organizer.deploy.config import DeploymentConfig

        with pytest.raises(ValueError, match="Invalid environment"):
            DeploymentConfig(environment="unknown")

    def test_invalid_log_level(self):
        from file_organizer.deploy.config import DeploymentConfig

        with pytest.raises(ValueError, match="Invalid log_level"):
            DeploymentConfig(log_level="TRACE")

    def test_log_level_normalized_to_uppercase(self):
        from file_organizer.deploy.config import DeploymentConfig

        cfg = DeploymentConfig(log_level="debug")
        assert cfg.log_level == "DEBUG"

    def test_invalid_max_workers(self):
        from file_organizer.deploy.config import DeploymentConfig

        with pytest.raises(ValueError, match="max_workers"):
            DeploymentConfig(max_workers=0)

    def test_invalid_port(self):
        from file_organizer.deploy.config import DeploymentConfig

        with pytest.raises(ValueError, match="port"):
            DeploymentConfig(port=99999)
        with pytest.raises(ValueError, match="port"):
            DeploymentConfig(port=0)

    def test_data_directory_str_converts_to_path(self):
        from file_organizer.deploy.config import DeploymentConfig

        cfg = DeploymentConfig(data_directory="data")  # type: ignore[arg-type]
        assert isinstance(cfg.data_directory, Path)

    def test_redis_host_parsing(self):
        from file_organizer.deploy.config import DeploymentConfig

        cfg = DeploymentConfig(redis_url="redis://myhost:6380/1")
        assert cfg.redis_host == "myhost"
        assert cfg.redis_port == 6380

    def test_redis_host_no_port(self):
        from file_organizer.deploy.config import DeploymentConfig

        cfg = DeploymentConfig(redis_url="redis://myhost/0")
        assert cfg.redis_host == "myhost"
        assert cfg.redis_port == 6379

    def test_from_env(self, monkeypatch):
        from file_organizer.deploy.config import DeploymentConfig

        monkeypatch.setenv("FO_ENVIRONMENT", "staging")
        monkeypatch.setenv("FO_LOG_LEVEL", "INFO")
        monkeypatch.setenv("FO_MAX_WORKERS", "4")
        monkeypatch.setenv("FO_PORT", "9000")
        monkeypatch.setenv("FO_HOST", "127.0.0.1")
        monkeypatch.setenv("FO_REDIS_URL", "redis://redis:6379/0")
        monkeypatch.setenv("FO_DATA_DIR", "/data")

        cfg = DeploymentConfig.from_env()
        assert cfg.environment == "staging"
        assert cfg.log_level == "INFO"
        assert cfg.max_workers == 4
        assert cfg.port == 9000
        assert cfg.host == "127.0.0.1"

    def test_from_env_unknown_environment_falls_back_to_dev_defaults(self, monkeypatch):
        from file_organizer.deploy.config import DeploymentConfig

        monkeypatch.setenv("FO_ENVIRONMENT", "dev")
        # No other env vars - should use dev defaults
        cfg = DeploymentConfig.from_env()
        assert cfg.log_level == "DEBUG"


# ===========================================================================
# 2. deploy/health.py
# ===========================================================================


class TestHealthEndpoint:
    """Tests for HealthEndpoint component checks."""

    def _make_config(self, redis_url="redis://localhost:6379/0"):
        from file_organizer.deploy.config import DeploymentConfig

        return DeploymentConfig(redis_url=redis_url)

    def test_get_health_all_healthy(self):
        from file_organizer.deploy.health import HealthEndpoint

        cfg = self._make_config()
        ep = HealthEndpoint(config=cfg, min_disk_space_mb=1)

        with (
            patch.object(ep, "_check_redis") as mock_redis,
            patch.object(ep, "_check_disk_space") as mock_disk,
            patch.object(ep, "_check_model_availability") as mock_model,
        ):
            from file_organizer.deploy.health import ComponentStatus

            mock_redis.return_value = ComponentStatus(name="redis", healthy=True, message="ok")
            mock_disk.return_value = ComponentStatus(name="disk", healthy=True, message="ok")
            mock_model.return_value = ComponentStatus(name="model", healthy=True, message="ok")

            result = ep.get_health()
            assert result["status"] == "healthy"
            assert "version" in result
            assert "uptime_seconds" in result

    def test_get_health_unhealthy(self):
        from file_organizer.deploy.health import ComponentStatus, HealthEndpoint

        cfg = self._make_config()
        ep = HealthEndpoint(config=cfg)
        with (
            patch.object(ep, "_check_redis") as mock_redis,
            patch.object(ep, "_check_disk_space") as mock_disk,
            patch.object(ep, "_check_model_availability") as mock_model,
        ):
            mock_redis.return_value = ComponentStatus(name="redis", healthy=False)
            mock_disk.return_value = ComponentStatus(name="disk", healthy=True)
            mock_model.return_value = ComponentStatus(name="model", healthy=True)
            result = ep.get_health()
            assert result["status"] == "unhealthy"

    def test_check_redis_connected(self):
        from file_organizer.deploy.health import HealthEndpoint

        cfg = self._make_config()
        ep = HealthEndpoint(config=cfg)
        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            mock_sock.connect_ex.return_value = 0
            assert ep.check_redis() is True

    def test_check_redis_refused(self):
        from file_organizer.deploy.health import HealthEndpoint

        ep = HealthEndpoint(config=self._make_config())
        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            mock_sock.connect_ex.return_value = 111
            assert ep.check_redis() is False

    def test_check_redis_oserror(self):
        from file_organizer.deploy.health import HealthEndpoint

        ep = HealthEndpoint(config=self._make_config())
        with patch("socket.socket") as mock_sock_cls:
            mock_sock_cls.return_value.__enter__ = MagicMock()
            mock_sock_cls.side_effect = OSError("network error")
            # patch at the class level - socket.socket() raises
            status = ep._check_redis()
            assert status.healthy is False

    def test_check_disk_space_sufficient(self, tmp_path):
        from file_organizer.deploy.config import DeploymentConfig
        from file_organizer.deploy.health import HealthEndpoint

        cfg = DeploymentConfig(data_directory=tmp_path)
        ep = HealthEndpoint(config=cfg, min_disk_space_mb=1)
        assert ep.check_disk_space() is True

    def test_check_disk_space_directory_missing(self):
        from file_organizer.deploy.config import DeploymentConfig
        from file_organizer.deploy.health import HealthEndpoint

        cfg = DeploymentConfig(data_directory=Path("/") / "nonexistent" / "path")
        ep = HealthEndpoint(config=cfg, min_disk_space_mb=1)
        # Falls back to "/" - should still work
        result = ep._check_disk_space()
        assert result.healthy is True

    def test_check_disk_space_oserror(self):
        from file_organizer.deploy.config import DeploymentConfig
        from file_organizer.deploy.health import HealthEndpoint

        cfg = DeploymentConfig(data_directory=Path("/") / "nonexistent")
        ep = HealthEndpoint(config=cfg)
        with patch("shutil.disk_usage", side_effect=OSError("disk error")):
            status = ep._check_disk_space()
            assert status.healthy is False

    def test_check_model_available(self):
        from file_organizer.deploy.health import HealthEndpoint

        ep = HealthEndpoint(config=self._make_config(), model_host="localhost", model_port=11434)
        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            mock_sock.connect_ex.return_value = 0
            assert ep.check_model_availability() is True

    def test_check_model_unavailable(self):
        from file_organizer.deploy.health import HealthEndpoint

        ep = HealthEndpoint(config=self._make_config())
        with patch("socket.socket") as mock_sock_cls:
            mock_sock = MagicMock()
            mock_sock_cls.return_value = mock_sock
            mock_sock.connect_ex.return_value = 111
            assert ep.check_model_availability() is False


# ===========================================================================
# 3. deploy/scaling.py
# ===========================================================================


class TestAutoScaler:
    """Tests for AutoScaler scaling decisions."""

    def _make_scaler(self, **kwargs):
        from file_organizer.deploy.scaling import AutoScaler, ScalingConfig

        config = ScalingConfig(
            min_replicas=1,
            max_replicas=5,
            scale_up_threshold=80.0,
            scale_down_threshold=20.0,
            cooldown_seconds=0,  # no cooldown for tests
            **kwargs,
        )
        monitor = MagicMock()
        return AutoScaler(config, resource_monitor=monitor), monitor

    def test_scaling_config_validation_errors(self):
        from file_organizer.deploy.scaling import ScalingConfig

        with pytest.raises(ValueError, match="min_replicas"):
            ScalingConfig(min_replicas=0)
        with pytest.raises(ValueError, match="max_replicas"):
            ScalingConfig(min_replicas=5, max_replicas=3)
        with pytest.raises(ValueError, match="Thresholds"):
            ScalingConfig(scale_down_threshold=90.0, scale_up_threshold=50.0)
        with pytest.raises(ValueError, match="cooldown"):
            ScalingConfig(cooldown_seconds=-1)

    def test_scale_up_action(self):
        from file_organizer.deploy.scaling import ScalingAction, ScalingMetrics

        scaler, _ = self._make_scaler()
        metrics = ScalingMetrics(cpu_percent=90.0, memory_percent=90.0)
        decision = scaler.evaluate(2, metrics=metrics)
        assert decision.action == ScalingAction.SCALE_UP
        assert decision.desired_replicas == 3

    def test_scale_up_at_max(self):
        from file_organizer.deploy.scaling import ScalingAction, ScalingMetrics

        scaler, _ = self._make_scaler()
        metrics = ScalingMetrics(cpu_percent=90.0, memory_percent=90.0)
        decision = scaler.evaluate(5, metrics=metrics)
        assert decision.action == ScalingAction.NO_CHANGE

    def test_scale_up_in_cooldown(self):
        from file_organizer.deploy.scaling import (
            AutoScaler,
            ScalingAction,
            ScalingConfig,
            ScalingMetrics,
        )

        config = ScalingConfig(cooldown_seconds=300)
        clock = MagicMock()
        clock.time.return_value = 0.0
        scaler = AutoScaler(config, resource_monitor=MagicMock(), clock=clock)
        scaler._last_scale_time = -100.0  # 100s ago, within 300s cooldown
        metrics = ScalingMetrics(cpu_percent=90.0, memory_percent=90.0)
        decision = scaler.evaluate(2, metrics=metrics)
        assert decision.action == ScalingAction.NO_CHANGE

    def test_scale_down_action(self):
        from file_organizer.deploy.scaling import ScalingAction, ScalingMetrics

        scaler, _ = self._make_scaler()
        metrics = ScalingMetrics(cpu_percent=10.0, memory_percent=10.0)
        decision = scaler.evaluate(3, metrics=metrics)
        assert decision.action == ScalingAction.SCALE_DOWN
        assert decision.desired_replicas == 2

    def test_scale_down_at_min(self):
        from file_organizer.deploy.scaling import ScalingAction, ScalingMetrics

        scaler, _ = self._make_scaler()
        metrics = ScalingMetrics(cpu_percent=10.0, memory_percent=10.0)
        decision = scaler.evaluate(1, metrics=metrics)
        assert decision.action == ScalingAction.NO_CHANGE

    def test_scale_down_in_cooldown(self):
        from file_organizer.deploy.scaling import (
            AutoScaler,
            ScalingAction,
            ScalingConfig,
            ScalingMetrics,
        )

        config = ScalingConfig(cooldown_seconds=300)
        clock = MagicMock()
        clock.time.return_value = 0.0
        scaler = AutoScaler(config, resource_monitor=MagicMock(), clock=clock)
        scaler._last_scale_time = -100.0
        metrics = ScalingMetrics(cpu_percent=5.0, memory_percent=5.0)
        decision = scaler.evaluate(3, metrics=metrics)
        assert decision.action == ScalingAction.NO_CHANGE

    def test_no_change_in_range(self):
        from file_organizer.deploy.scaling import ScalingAction, ScalingMetrics

        scaler, _ = self._make_scaler()
        metrics = ScalingMetrics(cpu_percent=50.0, memory_percent=50.0)
        decision = scaler.evaluate(2, metrics=metrics)
        assert decision.action == ScalingAction.NO_CHANGE

    def test_get_metrics_uses_monitor(self):
        from file_organizer.deploy.scaling import AutoScaler, ScalingConfig

        config = ScalingConfig()
        monitor = MagicMock()
        mem = MagicMock()
        mem.percent = 55.0
        monitor.get_memory_usage.return_value = mem
        scaler = AutoScaler(config, resource_monitor=monitor)
        metrics = scaler.get_metrics()
        assert metrics.cpu_percent == 55.0

    def test_evaluate_without_metrics_calls_get_metrics(self):
        from file_organizer.deploy.scaling import AutoScaler, ScalingConfig

        config = ScalingConfig()
        monitor = MagicMock()
        mem = MagicMock()
        mem.percent = 50.0
        monitor.get_memory_usage.return_value = mem
        scaler = AutoScaler(config, resource_monitor=monitor)
        decision = scaler.evaluate(2)
        assert decision is not None

    def test_now_no_clock(self):
        from file_organizer.deploy.scaling import AutoScaler, ScalingConfig

        scaler = AutoScaler(ScalingConfig(), resource_monitor=MagicMock())
        t = scaler._now()
        assert isinstance(t, float)
        assert t > 0

    def test_now_with_clock(self):
        from file_organizer.deploy.scaling import AutoScaler, ScalingConfig

        clock = MagicMock()
        clock.time.return_value = 42.0
        scaler = AutoScaler(ScalingConfig(), resource_monitor=MagicMock(), clock=clock)
        assert scaler._now() == 42.0


# ===========================================================================
# 4. deploy/monitoring.py
# ===========================================================================


class TestDeploymentMonitor:
    """Tests for DeploymentMonitor metric collection and alerts."""

    def test_alert_thresholds_validation(self):
        from file_organizer.deploy.monitoring import AlertThresholds

        with pytest.raises(ValueError, match="cpu_warning"):
            AlertThresholds(cpu_warning=95.0, cpu_critical=90.0)
        with pytest.raises(ValueError, match="memory_warning"):
            AlertThresholds(memory_warning=95.0, memory_critical=90.0)

    def test_collect_metrics(self):
        from file_organizer.deploy.monitoring import DeploymentMonitor

        monitor_mock = MagicMock()
        mem = MagicMock()
        mem.percent = 60.0
        monitor_mock.get_memory_usage.return_value = mem
        dm = DeploymentMonitor(resource_monitor=monitor_mock, disk_usage_func=lambda: 45.0)
        snap = dm.collect_metrics()
        assert snap.cpu_usage == 60.0
        assert snap.disk_usage == 45.0

    def test_get_alerts_cpu_critical(self):
        import time

        from file_organizer.deploy.monitoring import (
            AlertLevel,
            AlertThresholds,
            DeploymentMonitor,
            MetricsSnapshot,
        )

        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=95.0,
            memory_usage=50.0,
            disk_usage=50.0,
            active_connections=0,
            processing_rate=0.0,
        )
        dm = DeploymentMonitor(resource_monitor=MagicMock())
        thresholds = AlertThresholds(cpu_warning=70.0, cpu_critical=90.0)
        alerts = dm.get_alerts(thresholds, snapshot=snap)
        cpu_alerts = [a for a in alerts if a.metric == "cpu_usage"]
        assert any(a.level == AlertLevel.CRITICAL for a in cpu_alerts)

    def test_get_alerts_cpu_warning(self):
        import time

        from file_organizer.deploy.monitoring import (
            AlertLevel,
            AlertThresholds,
            DeploymentMonitor,
            MetricsSnapshot,
        )

        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=75.0,
            memory_usage=50.0,
            disk_usage=50.0,
            active_connections=0,
            processing_rate=0.0,
        )
        dm = DeploymentMonitor(resource_monitor=MagicMock())
        thresholds = AlertThresholds()
        alerts = dm.get_alerts(thresholds, snapshot=snap)
        cpu_alerts = [a for a in alerts if a.metric == "cpu_usage"]
        assert any(a.level == AlertLevel.WARNING for a in cpu_alerts)

    def test_get_alerts_memory_critical(self):
        import time

        from file_organizer.deploy.monitoring import (
            AlertLevel,
            AlertThresholds,
            DeploymentMonitor,
            MetricsSnapshot,
        )

        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=50.0,
            memory_usage=95.0,
            disk_usage=50.0,
            active_connections=0,
            processing_rate=0.0,
        )
        dm = DeploymentMonitor(resource_monitor=MagicMock())
        thresholds = AlertThresholds()
        alerts = dm.get_alerts(thresholds, snapshot=snap)
        mem_alerts = [a for a in alerts if a.metric == "memory_usage"]
        assert any(a.level == AlertLevel.CRITICAL for a in mem_alerts)

    def test_get_alerts_disk_warning(self):
        import time

        from file_organizer.deploy.monitoring import (
            AlertLevel,
            AlertThresholds,
            DeploymentMonitor,
            MetricsSnapshot,
        )

        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=50.0,
            memory_usage=50.0,
            disk_usage=85.0,
            active_connections=0,
            processing_rate=0.0,
        )
        dm = DeploymentMonitor(resource_monitor=MagicMock())
        thresholds = AlertThresholds()
        alerts = dm.get_alerts(thresholds, snapshot=snap)
        disk_alerts = [a for a in alerts if a.metric == "disk_usage"]
        assert any(a.level == AlertLevel.WARNING for a in disk_alerts)

    def test_get_alerts_none_fired(self):
        import time

        from file_organizer.deploy.monitoring import (
            AlertThresholds,
            DeploymentMonitor,
            MetricsSnapshot,
        )

        snap = MetricsSnapshot(
            timestamp=time.time(),
            cpu_usage=10.0,
            memory_usage=10.0,
            disk_usage=10.0,
            active_connections=0,
            processing_rate=0.0,
        )
        dm = DeploymentMonitor(resource_monitor=MagicMock())
        thresholds = AlertThresholds()
        alerts = dm.get_alerts(thresholds, snapshot=snap)
        assert alerts == []

    def test_get_alerts_no_snapshot_calls_collect(self):
        from file_organizer.deploy.monitoring import AlertThresholds, DeploymentMonitor

        monitor_mock = MagicMock()
        mem = MagicMock()
        mem.percent = 20.0
        monitor_mock.get_memory_usage.return_value = mem
        dm = DeploymentMonitor(resource_monitor=monitor_mock, disk_usage_func=lambda: 10.0)
        alerts = dm.get_alerts(AlertThresholds())
        assert alerts == []

    def test_disk_usage_fallback_shutil(self):
        from file_organizer.deploy.monitoring import DeploymentMonitor

        dm = DeploymentMonitor(resource_monitor=MagicMock())
        with patch("shutil.disk_usage") as mock_disk:
            mock_disk.return_value = MagicMock(used=500, total=1000)
            result = dm._get_disk_usage()
            assert result == 50.0

    def test_disk_usage_fallback_oserror(self):
        from file_organizer.deploy.monitoring import DeploymentMonitor

        dm = DeploymentMonitor(resource_monitor=MagicMock())
        with patch("shutil.disk_usage", side_effect=OSError):
            result = dm._get_disk_usage()
            assert result == 0.0


# ===========================================================================
# 5. deploy/compose_scaler.py
# ===========================================================================


class TestComposeScaler:
    """Tests for ComposeScaler subprocess wrappers."""

    def test_scale_service_success(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler("docker-compose.yml")
        with patch.object(scaler, "_run_command", return_value=True) as mock_run:
            assert scaler.scale_service("web", 3) is True
            mock_run.assert_called_once()

    def test_scale_service_negative_replicas(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with pytest.raises(ValueError, match="replicas"):
            scaler.scale_service("web", -1)

    def test_scale_service_failure(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with patch.object(scaler, "_run_command", return_value=False):
            assert scaler.scale_service("web", 2) is False

    def test_get_service_count_success(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with patch.object(scaler, "_run_command_output", return_value="{}\n{}\n"):
            assert scaler.get_service_count("web") == 2

    def test_get_service_count_none_output(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with patch.object(scaler, "_run_command_output", return_value=None):
            assert scaler.get_service_count("web") == 0

    def test_build_command_with_project_name(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler("compose.yml", project_name="myproject")
        cmd = scaler._build_command("ps")
        assert "-p" in cmd
        assert "myproject" in cmd

    def test_run_command_success(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert scaler._run_command(["docker-compose", "ps"]) is True

    def test_run_command_failure(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="error", stdout="")
            assert scaler._run_command(["bad"]) is False

    def test_run_command_exception(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with patch("subprocess.run", side_effect=FileNotFoundError("docker not found")):
            assert scaler._run_command(["docker-compose"]) is False

    def test_run_command_output_success(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="json_line\n")
            assert scaler._run_command_output(["cmd"]) == "json_line\n"

    def test_run_command_output_failure(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="err", stdout="")
            assert scaler._run_command_output(["cmd"]) is None

    def test_run_command_output_exception(self):
        from file_organizer.deploy.compose_scaler import ComposeScaler

        scaler = ComposeScaler()
        with patch("subprocess.run", side_effect=OSError("timeout")):
            assert scaler._run_command_output(["cmd"]) is None


# ===========================================================================
# 6. config/migrations.py
# ===========================================================================


class TestConfigMigrations:
    """Tests for config schema migration utilities."""

    def test_version_key_numeric(self):
        from file_organizer.config.migrations import _version_key

        assert _version_key("1.0") == (1,)
        assert _version_key("1.2.3") == (1, 2, 3)
        assert _version_key("2.0.0") == (2,)

    def test_version_key_non_numeric(self):
        from file_organizer.config.migrations import _version_key

        assert _version_key("bad") == (0,)

    def test_compare_versions(self):
        from file_organizer.config.migrations import compare_versions

        assert compare_versions("1.0", "2.0") == -1
        assert compare_versions("2.0", "1.0") == 1
        assert compare_versions("1.0", "1.0") == 0
        assert compare_versions("1.0", "1.0.0") == 0

    def test_migrate_to_current_same_version(self):
        from file_organizer.config.migrations import migrate_to_current

        data = {"key": "value"}
        result = migrate_to_current(data, from_version="1.0", to_version="1.0")
        assert result is data

    def test_migrate_to_current_no_migrations(self):
        """With empty MIGRATIONS registry, returns data with a warning."""
        from file_organizer.config.migrations import migrate_to_current

        data = {"key": "value"}
        result = migrate_to_current(data, from_version="0.5", to_version="1.0")
        assert result is data

    def test_migrate_to_current_with_migration(self):
        """Monkeypatching MIGRATIONS to verify the chain runs."""
        from file_organizer.config import migrations

        def upgrade_to_1_0(data: dict) -> dict:
            data["version"] = "1.0"
            return data

        original = dict(migrations.MIGRATIONS)
        try:
            migrations.MIGRATIONS["0.5"] = migrations.Migration(
                to_version="1.0",
                transform=upgrade_to_1_0,
            )
            data: dict = {"version": "0.5"}
            result = migrations.migrate_to_current(data, from_version="0.5", to_version="1.0")
            assert result["version"] == "1.0"
        finally:
            migrations.MIGRATIONS.clear()
            migrations.MIGRATIONS.update(original)

    def test_migrate_non_increasing_to_version_stops(self):
        """A migration with a non-increasing to_version should stop the walk."""
        from file_organizer.config import migrations

        def bad_transform(data: dict) -> dict:
            return data

        original = dict(migrations.MIGRATIONS)
        try:
            # from_version "1.0" -> to_version "0.5" (non-increasing, should stop)
            migrations.MIGRATIONS["1.0"] = migrations.Migration(
                to_version="0.5",
                transform=bad_transform,
            )
            data: dict = {}
            result = migrations.migrate_to_current(data, from_version="1.0", to_version="2.0")
            assert result is data
        finally:
            migrations.MIGRATIONS.clear()
            migrations.MIGRATIONS.update(original)

    def test_migrate_transform_exception_reraises(self):
        """Exceptions from transforms are re-raised after logging."""
        from file_organizer.config import migrations

        def failing_transform(data: dict) -> dict:
            raise RuntimeError("transform failure")

        original = dict(migrations.MIGRATIONS)
        try:
            migrations.MIGRATIONS["0.5"] = migrations.Migration(
                to_version="1.0",
                transform=failing_transform,
            )
            with pytest.raises(RuntimeError, match="transform failure"):
                migrations.migrate_to_current({}, from_version="0.5", to_version="1.0")
        finally:
            migrations.MIGRATIONS.clear()
            migrations.MIGRATIONS.update(original)


# ===========================================================================
# 7. events/monitor.py
# ===========================================================================


class TestEventMonitor:
    """Tests for EventMonitor Redis stream statistics."""

    def _make_monitor(self, connected=True):
        from file_organizer.events.monitor import EventMonitor

        manager = MagicMock()
        manager.is_connected = connected
        manager.config.get_stream_name = lambda name: f"fo:{name}"
        return EventMonitor(manager), manager

    def test_get_stream_stats_not_connected(self):
        monitor, _ = self._make_monitor(connected=False)
        from file_organizer.events.monitor import StreamStats

        stats = monitor.get_stream_stats("file-events")
        assert stats == StreamStats()

    def test_get_stream_stats_connected(self):
        monitor, manager = self._make_monitor()
        redis_mock = MagicMock()
        manager._redis = redis_mock
        redis_mock.xinfo_stream.return_value = {
            "length": 10,
            "groups": 2,
            "first-entry": ("1600000000000-0", {}),
            "last-entry": ("1600000001000-0", {}),
        }
        stats = monitor.get_stream_stats("file-events")
        assert stats.length == 10
        assert stats.groups == 2
        assert stats.oldest_event is not None

    def test_get_stream_stats_exception(self):
        monitor, manager = self._make_monitor()
        manager._redis = MagicMock()
        manager._redis.xinfo_stream.side_effect = Exception("redis error")
        from file_organizer.events.monitor import StreamStats

        stats = monitor.get_stream_stats("file-events")
        assert stats == StreamStats()

    def test_get_consumer_lag_not_connected(self):
        monitor, _ = self._make_monitor(connected=False)
        from file_organizer.events.monitor import ConsumerLag

        lag = monitor.get_consumer_lag("file-events", "workers")
        assert lag == ConsumerLag()

    def test_get_consumer_lag_connected(self):
        monitor, manager = self._make_monitor()
        redis_mock = MagicMock()
        manager._redis = redis_mock
        redis_mock.xpending.return_value = {"pending": 5}
        redis_mock.xinfo_groups.return_value = [{"name": "workers", "consumers": 3, "idle": 1000}]
        lag = monitor.get_consumer_lag("file-events", "workers")
        assert lag.pending == 5
        assert lag.consumers == 3

    def test_get_consumer_lag_group_not_found(self):
        monitor, manager = self._make_monitor()
        redis_mock = MagicMock()
        manager._redis = redis_mock
        redis_mock.xpending.return_value = {"pending": 0}
        redis_mock.xinfo_groups.return_value = [{"name": "other_group"}]
        lag = monitor.get_consumer_lag("file-events", "workers")
        assert lag.consumers == 0

    def test_get_consumer_lag_exception(self):
        monitor, manager = self._make_monitor()
        manager._redis = MagicMock()
        manager._redis.xpending.side_effect = Exception("error")
        from file_organizer.events.monitor import ConsumerLag

        lag = monitor.get_consumer_lag("file-events", "workers")
        assert lag == ConsumerLag()

    def test_get_event_rate_not_connected(self):
        monitor, _ = self._make_monitor(connected=False)
        assert monitor.get_event_rate("file-events") == 0.0

    def test_get_event_rate_zero_window(self):
        monitor, _ = self._make_monitor()
        assert monitor.get_event_rate("file-events", window_seconds=0) == 0.0

    def test_get_event_rate_with_results(self):
        monitor, manager = self._make_monitor()
        redis_mock = MagicMock()
        manager._redis = redis_mock
        redis_mock.xrange.return_value = [("id1", {}), ("id2", {})]
        rate = monitor.get_event_rate("file-events", window_seconds=10)
        assert rate == pytest.approx(0.2, abs=0.01)

    def test_get_event_rate_exception(self):
        monitor, manager = self._make_monitor()
        manager._redis = MagicMock()
        manager._redis.xrange.side_effect = Exception("error")
        assert monitor.get_event_rate("file-events") == 0.0

    def test_repr(self):
        monitor, _ = self._make_monitor()
        assert "EventMonitor" in repr(monitor)

    def test_parse_entry_timestamp_none(self):
        from file_organizer.events.monitor import _parse_entry_timestamp

        assert _parse_entry_timestamp(None) is None

    def test_parse_entry_timestamp_valid(self):
        from file_organizer.events.monitor import _parse_entry_timestamp

        ts = _parse_entry_timestamp(("1600000000000-0", {}))
        assert ts is not None

    def test_parse_entry_timestamp_invalid(self):
        from file_organizer.events.monitor import _parse_entry_timestamp

        assert _parse_entry_timestamp(("bad-id", {})) is None


# ===========================================================================
# 8. events/consumer.py
# ===========================================================================


class TestEventConsumer:
    """Tests for EventConsumer handler registration and dispatch."""

    def _make_consumer(self):
        from file_organizer.events.consumer import EventConsumer

        manager = MagicMock()
        manager.is_connected = True
        return EventConsumer(stream_manager=manager), manager

    def test_initial_state(self):
        consumer, _ = self._make_consumer()
        assert consumer.is_running is False
        assert consumer.events_processed == 0
        assert consumer.registered_handlers == {}

    def test_connect_delegates(self):
        consumer, manager = self._make_consumer()
        manager.connect.return_value = True
        assert consumer.connect() is True

    def test_disconnect_stops_and_disconnects(self):
        consumer, manager = self._make_consumer()
        consumer._running = True
        consumer.disconnect()
        assert consumer.is_running is False
        manager.disconnect.assert_called_once()

    def test_register_handler(self):
        from file_organizer.events.types import EventType

        consumer, _ = self._make_consumer()
        handler = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler)
        assert consumer.registered_handlers.get(EventType.FILE_CREATED.value) == 1

    def test_register_multiple_handlers(self):
        from file_organizer.events.types import EventType

        consumer, _ = self._make_consumer()
        h1, h2 = MagicMock(), MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, h1)
        consumer.register_handler(EventType.FILE_CREATED, h2)
        assert consumer.registered_handlers[EventType.FILE_CREATED.value] == 2

    def test_unregister_handler(self):
        from file_organizer.events.types import EventType

        consumer, _ = self._make_consumer()
        handler = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler)
        result = consumer.unregister_handler(EventType.FILE_CREATED, handler)
        assert result is True
        assert EventType.FILE_CREATED.value not in consumer.registered_handlers

    def test_unregister_handler_not_registered(self):
        from file_organizer.events.types import EventType

        consumer, _ = self._make_consumer()
        result = consumer.unregister_handler(EventType.FILE_CREATED, MagicMock())
        assert result is False

    def test_stop_when_running(self):
        consumer, _ = self._make_consumer()
        consumer._running = True
        consumer.stop()
        assert consumer.is_running is False

    def test_stop_when_not_running(self):
        consumer, _ = self._make_consumer()
        consumer.stop()
        assert consumer.is_running is False

    def test_dispatch_event_no_handlers(self):
        from file_organizer.events.stream import Event

        consumer, manager = self._make_consumer()
        event = Event(id="msg1", stream="test", data={"event_type": "unknown"})
        consumer._dispatch_event(event, "test", "group1")
        manager.acknowledge.assert_called_once_with("test", "group1", "msg1")

    def test_dispatch_event_with_handler_success(self):
        from file_organizer.events.stream import Event
        from file_organizer.events.types import EventType

        consumer, manager = self._make_consumer()
        handler = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, handler)
        event = Event(id="msg1", stream="test", data={"event_type": "file.created"})
        consumer._dispatch_event(event, "test", "group1")
        handler.assert_called_once_with(event)
        manager.acknowledge.assert_called_once()
        assert consumer.events_processed == 1

    def test_dispatch_event_handler_raises(self):
        from file_organizer.events.stream import Event
        from file_organizer.events.types import EventType

        consumer, manager = self._make_consumer()
        handler = MagicMock(side_effect=RuntimeError("handler error"))
        consumer.register_handler(EventType.FILE_CREATED, handler)
        event = Event(id="msg1", stream="test", data={"event_type": "file.created"})
        consumer._dispatch_event(event, "test", "group1")
        # Not acknowledged if handler fails
        manager.acknowledge.assert_not_called()
        assert consumer.events_processed == 0

    def test_context_manager(self):
        consumer, manager = self._make_consumer()
        with consumer:
            pass
        manager.disconnect.assert_called_once()

    def test_repr(self):
        consumer, _ = self._make_consumer()
        assert "EventConsumer" in repr(consumer)

    @pytest.mark.asyncio
    async def test_start_consuming_not_connected(self):
        from file_organizer.events.consumer import EventConsumer

        manager = MagicMock()
        manager.is_connected = False
        consumer = EventConsumer(stream_manager=manager)
        # Should return immediately without running
        await consumer.start_consuming("test-stream")
        assert consumer.is_running is False

    @pytest.mark.asyncio
    async def test_start_consuming_processes_events(self):
        """Start consuming, process one batch, then stop."""

        from file_organizer.events.consumer import EventConsumer
        from file_organizer.events.stream import Event
        from file_organizer.events.types import EventType

        manager = MagicMock()
        manager.is_connected = True
        manager.config.consumer_group = "test-group"

        event = Event(id="msg1", stream="test", data={"event_type": EventType.FILE_CREATED.value})
        # First call returns events, second call consumer is stopped
        call_count = 0

        def read_group_side_effect(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [event]
            # Stop after first batch
            consumer._running = False
            return []

        manager.read_group.side_effect = read_group_side_effect

        consumer = EventConsumer(stream_manager=manager)
        mock_handler = MagicMock()
        consumer.register_handler(EventType.FILE_CREATED, mock_handler)

        await consumer.start_consuming("test-stream", group_name="test-group")
        assert call_count >= 1
        mock_handler.assert_called_once_with(event)
        assert consumer.events_processed == 1
        manager.acknowledge.assert_called_once_with("test-stream", "test-group", "msg1")


# ===========================================================================
# 9. core/backend_detector.py
# ===========================================================================


class TestBackendDetector:
    """Tests for Ollama backend detection."""

    def test_detect_ollama_not_available(self):
        with patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", False):
            from file_organizer.core.backend_detector import detect_ollama

            status = detect_ollama()
            assert status.installed is False
            assert status.running is False

    def test_detect_ollama_cli_found_service_running(self):
        with (
            patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True),
            patch("subprocess.run") as mock_run,
            patch("file_organizer.core.backend_detector.ollama") as mock_ollama,
        ):
            # CLI found
            mock_run.return_value = MagicMock(returncode=0, stdout="ollama version 0.1.0")
            # Service running with 2 models
            client_mock = MagicMock()
            mock_ollama.Client.return_value = client_mock
            models_response = MagicMock()
            models_response.models = [MagicMock(), MagicMock()]
            client_mock.list.return_value = models_response

            from file_organizer.core.backend_detector import detect_ollama

            status = detect_ollama()
            assert status.running is True
            assert status.models_count == 2

    def test_detect_ollama_cli_not_found_service_running(self):
        with (
            patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True),
            patch("subprocess.run", side_effect=FileNotFoundError),
            patch("file_organizer.core.backend_detector.ollama") as mock_ollama,
        ):
            client_mock = MagicMock()
            mock_ollama.Client.return_value = client_mock
            # Service returns dict format
            client_mock.list.return_value = {"models": [1, 2, 3]}

            from file_organizer.core.backend_detector import detect_ollama

            status = detect_ollama()
            assert status.running is True
            assert status.models_count == 3

    def test_detect_ollama_service_not_responding(self):
        with (
            patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True),
            patch("subprocess.run") as mock_run,
            patch("file_organizer.core.backend_detector.ollama") as mock_ollama,
            patch(
                "file_organizer.core.backend_detector.OLLAMA_CLIENT_EXCEPTIONS", (ConnectionError,)
            ),
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="version")
            mock_ollama.Client.return_value.list.side_effect = ConnectionError("refused")

            from file_organizer.core.backend_detector import detect_ollama

            status = detect_ollama()
            assert status.running is False

    def test_detect_ollama_models_as_list(self):
        with (
            patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True),
            patch("subprocess.run", side_effect=FileNotFoundError),
            patch("file_organizer.core.backend_detector.ollama") as mock_ollama,
        ):
            client_mock = MagicMock()
            mock_ollama.Client.return_value = client_mock
            client_mock.list.return_value = [1, 2]
            from file_organizer.core.backend_detector import detect_ollama

            status = detect_ollama()
            assert status.models_count == 2

    def test_list_installed_models_not_available(self):
        with patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", False):
            from file_organizer.core.backend_detector import list_installed_models

            assert list_installed_models() == []

    def test_list_installed_models_via_client_dataclass(self):
        with (
            patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True),
            patch("file_organizer.core.backend_detector.ollama") as mock_ollama,
        ):
            client_mock = MagicMock()
            mock_ollama.Client.return_value = client_mock
            model = MagicMock(spec=["model", "size", "modified_at"])
            model.model = "llama3:8b"
            model.size = 1024
            model.modified_at = "2024-01-01"
            response = MagicMock()
            response.models = [model]
            client_mock.list.return_value = response

            from file_organizer.core.backend_detector import list_installed_models

            models = list_installed_models()
            assert len(models) == 1
            assert models[0].name == "llama3:8b"

    def test_list_installed_models_via_client_dict_fallback(self):
        with (
            patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True),
            patch("file_organizer.core.backend_detector.ollama") as mock_ollama,
        ):
            client_mock = MagicMock()
            mock_ollama.Client.return_value = client_mock
            # Return dict format (no 'model' attr)
            client_mock.list.return_value = {"models": [{"name": "gemma:2b", "size": 500}]}

            from file_organizer.core.backend_detector import list_installed_models

            models = list_installed_models()
            assert len(models) == 1
            assert models[0].name == "gemma:2b"

    def test_list_installed_models_client_fails_cli_json(self):
        with (
            patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True),
            patch("file_organizer.core.backend_detector.ollama") as mock_ollama,
            patch("subprocess.run") as mock_run,
            patch(
                "file_organizer.core.backend_detector.OLLAMA_CLIENT_EXCEPTIONS", (ConnectionError,)
            ),
        ):
            mock_ollama.Client.return_value.list.side_effect = ConnectionError("refused")
            # CLI returns JSON
            import json

            mock_run.return_value = MagicMock(
                returncode=0,
                stdout=json.dumps({"models": [{"name": "phi3:mini"}]}),
            )
            from file_organizer.core.backend_detector import list_installed_models

            models = list_installed_models()
            assert len(models) == 1

    def test_list_installed_models_cli_fails_text_fallback(self):
        with (
            patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True),
            patch("file_organizer.core.backend_detector.ollama") as mock_ollama,
            patch("subprocess.run") as mock_run,
            patch(
                "file_organizer.core.backend_detector.OLLAMA_CLIENT_EXCEPTIONS", (ConnectionError,)
            ),
        ):
            mock_ollama.Client.return_value.list.side_effect = ConnectionError("refused")
            # CLI JSON fails
            mock_run.side_effect = [
                MagicMock(returncode=1, stdout="", stderr=""),
                MagicMock(returncode=0, stdout="NAME\nllama3:8b tag 123 3 weeks\n"),
            ]
            from file_organizer.core.backend_detector import list_installed_models

            models = list_installed_models()
            assert len(models) >= 1

    def test_list_installed_models_cli_not_found(self):
        with (
            patch("file_organizer.core.backend_detector.OLLAMA_AVAILABLE", True),
            patch("file_organizer.core.backend_detector.ollama") as mock_ollama,
            patch("subprocess.run", side_effect=FileNotFoundError),
            patch(
                "file_organizer.core.backend_detector.OLLAMA_CLIENT_EXCEPTIONS", (ConnectionError,)
            ),
        ):
            mock_ollama.Client.return_value.list.side_effect = ConnectionError("refused")
            from file_organizer.core.backend_detector import list_installed_models

            models = list_installed_models()
            assert models == []

    def test_parse_ollama_list_text(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0, stdout="NAME\nllama3:8b tag 123\nphi3:mini tag 456\n"
            )
            from file_organizer.core.backend_detector import _parse_ollama_list_text

            models = _parse_ollama_list_text()
            assert len(models) == 2

    def test_parse_ollama_list_text_exception(self):
        with patch("subprocess.run", side_effect=subprocess.SubprocessError("err")):
            from file_organizer.core.backend_detector import _parse_ollama_list_text

            assert _parse_ollama_list_text() == []


# ===========================================================================
# 10. core/hardware_profile.py
# ===========================================================================


class TestHardwareProfile:
    """Tests for hardware detection helpers and profile generation."""

    def test_hardware_profile_properties(self):
        from file_organizer.core.hardware_profile import GpuType, HardwareProfile

        p = HardwareProfile(
            gpu_type=GpuType.NONE,
            gpu_name=None,
            vram_bytes=0,
            ram_bytes=16 * 1024**3,
            cpu_cores=8,
            os_name="Linux",
            arch="x86_64",
        )
        assert p.vram_gb == 0.0
        assert p.ram_gb == 16.0
        assert p.recommended_workers() == 4
        assert "recommended_text_model" in p.to_dict()

    def test_recommended_text_model_large(self):
        from file_organizer.core.hardware_profile import GpuType, HardwareProfile

        p = HardwareProfile(
            gpu_type=GpuType.NVIDIA,
            gpu_name="RTX 4090",
            vram_bytes=24 * 1024**3,
            ram_bytes=32 * 1024**3,
            cpu_cores=16,
            os_name="Linux",
            arch="x86_64",
        )
        assert "7b" in p.recommended_text_model()

    def test_recommended_text_model_small(self):
        from file_organizer.core.hardware_profile import GpuType, HardwareProfile

        p = HardwareProfile(
            gpu_type=GpuType.NONE,
            gpu_name=None,
            vram_bytes=0,
            ram_bytes=8 * 1024**3,
            cpu_cores=4,
            os_name="Linux",
            arch="x86_64",
        )
        assert "3b" in p.recommended_text_model()

    def test_recommended_workers_minimum_one(self):
        from file_organizer.core.hardware_profile import GpuType, HardwareProfile

        p = HardwareProfile(
            gpu_type=GpuType.NONE,
            gpu_name=None,
            vram_bytes=0,
            ram_bytes=4 * 1024**3,
            cpu_cores=1,
            os_name="Linux",
            arch="x86_64",
        )
        assert p.recommended_workers() == 1

    def test_detect_nvidia_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="NVIDIA A100, 81920\n")
            from file_organizer.core.hardware_profile import _detect_nvidia

            name, vram = _detect_nvidia()
            assert name == "NVIDIA A100"
            assert vram > 0

    def test_detect_nvidia_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            from file_organizer.core.hardware_profile import _detect_nvidia

            name, vram = _detect_nvidia()
            assert name is None
            assert vram == 0

    def test_detect_nvidia_bad_returncode(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="")
            from file_organizer.core.hardware_profile import _detect_nvidia

            name, vram = _detect_nvidia()
            assert name is None

    def test_detect_apple_mps_non_darwin(self):
        with patch("platform.system", return_value="Linux"):
            from file_organizer.core.hardware_profile import _detect_apple_mps

            name, vram = _detect_apple_mps()
            assert name is None

    def test_detect_apple_mps_darwin_apple_silicon(self):
        with (
            patch("platform.system", return_value="Darwin"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="Apple M2"),
                MagicMock(returncode=0, stdout="16000000000"),
            ]
            from file_organizer.core.hardware_profile import _detect_apple_mps

            name, vram = _detect_apple_mps()
            assert name is not None
            assert vram == 16000000000

    def test_detect_apple_mps_not_apple_brand(self):
        with (
            patch("platform.system", return_value="Darwin"),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="Intel Core i7")
            from file_organizer.core.hardware_profile import _detect_apple_mps

            name, vram = _detect_apple_mps()
            assert name is None

    def test_detect_amd_success(self):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="GPU,\nRX 6800,\n"),
                MagicMock(returncode=0, stdout="VRAM,\n16384,\n"),
            ]
            from file_organizer.core.hardware_profile import _detect_amd

            name, vram = _detect_amd()
            assert name is not None

    def test_detect_amd_not_found(self):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            from file_organizer.core.hardware_profile import _detect_amd

            name, vram = _detect_amd()
            assert name is None

    def test_get_system_ram_psutil(self):
        with patch("psutil.virtual_memory") as mock_vm:
            mock_vm.return_value = MagicMock(total=8 * 1024**3)
            from file_organizer.core.hardware_profile import _get_system_ram

            assert _get_system_ram() == 8 * 1024**3

    def test_get_cpu_cores_psutil(self):
        with patch("psutil.cpu_count", return_value=8):
            from file_organizer.core.hardware_profile import _get_cpu_cores

            assert _get_cpu_cores() == 8

    def test_detect_hardware_nvidia(self):
        with (
            patch(
                "file_organizer.core.hardware_profile._detect_nvidia",
                return_value=("RTX 4090", 24 * 1024**3),
            ),
            patch(
                "file_organizer.core.hardware_profile._get_system_ram", return_value=32 * 1024**3
            ),
            patch("file_organizer.core.hardware_profile._get_cpu_cores", return_value=16),
        ):
            from file_organizer.core.hardware_profile import GpuType, detect_hardware

            profile = detect_hardware()
            assert profile.gpu_type == GpuType.NVIDIA

    def test_detect_hardware_apple_mps(self):
        with (
            patch("file_organizer.core.hardware_profile._detect_nvidia", return_value=(None, 0)),
            patch(
                "file_organizer.core.hardware_profile._detect_apple_mps",
                return_value=("Apple M2", 16 * 1024**3),
            ),
            patch(
                "file_organizer.core.hardware_profile._get_system_ram", return_value=16 * 1024**3
            ),
            patch("file_organizer.core.hardware_profile._get_cpu_cores", return_value=8),
        ):
            from file_organizer.core.hardware_profile import GpuType, detect_hardware

            profile = detect_hardware()
            assert profile.gpu_type == GpuType.APPLE_MPS

    def test_detect_hardware_amd(self):
        with (
            patch("file_organizer.core.hardware_profile._detect_nvidia", return_value=(None, 0)),
            patch("file_organizer.core.hardware_profile._detect_apple_mps", return_value=(None, 0)),
            patch(
                "file_organizer.core.hardware_profile._detect_amd",
                return_value=("RX 6800", 16 * 1024**3),
            ),
            patch(
                "file_organizer.core.hardware_profile._get_system_ram", return_value=32 * 1024**3
            ),
            patch("file_organizer.core.hardware_profile._get_cpu_cores", return_value=8),
        ):
            from file_organizer.core.hardware_profile import GpuType, detect_hardware

            profile = detect_hardware()
            assert profile.gpu_type == GpuType.AMD

    def test_detect_hardware_no_gpu(self):
        with (
            patch("file_organizer.core.hardware_profile._detect_nvidia", return_value=(None, 0)),
            patch("file_organizer.core.hardware_profile._detect_apple_mps", return_value=(None, 0)),
            patch("file_organizer.core.hardware_profile._detect_amd", return_value=(None, 0)),
            patch("file_organizer.core.hardware_profile._get_system_ram", return_value=8 * 1024**3),
            patch("file_organizer.core.hardware_profile._get_cpu_cores", return_value=4),
        ):
            from file_organizer.core.hardware_profile import GpuType, detect_hardware

            profile = detect_hardware()
            assert profile.gpu_type == GpuType.NONE


# ===========================================================================
# 11. parallel/resource_manager.py
# ===========================================================================


class TestResourceManager:
    """Tests for ResourceManager acquire/release/get operations."""

    def _make_manager(self):
        from file_organizer.parallel.resource_manager import ResourceConfig, ResourceManager

        config = ResourceConfig(
            max_cpu_percent=80.0,
            max_memory_mb=1024,
            max_io_operations=10,
            max_gpu_percent=50.0,
        )
        return ResourceManager(config)

    def test_resource_config_validation(self):
        from file_organizer.parallel.resource_manager import ResourceConfig

        with pytest.raises(ValueError, match="max_cpu_percent"):
            ResourceConfig(max_cpu_percent=0)
        with pytest.raises(ValueError, match="max_memory_mb"):
            ResourceConfig(max_memory_mb=0)
        with pytest.raises(ValueError, match="max_io_operations"):
            ResourceConfig(max_io_operations=0)
        with pytest.raises(ValueError, match="max_gpu_percent"):
            ResourceConfig(max_gpu_percent=-1)

    def test_acquire_success(self):
        manager = self._make_manager()
        assert manager.acquire("cpu", 40.0) is True
        assert manager.get_used("cpu") == 40.0

    def test_acquire_insufficient(self):
        manager = self._make_manager()
        assert manager.acquire("cpu", 90.0) is False

    def test_acquire_negative_amount(self):
        manager = self._make_manager()
        with pytest.raises(ValueError, match="amount"):
            manager.acquire("cpu", -1.0)

    def test_acquire_unknown_resource(self):
        manager = self._make_manager()
        with pytest.raises(ValueError, match="Unknown resource"):
            manager.acquire("unknown", 10.0)

    def test_release_success(self):
        manager = self._make_manager()
        manager.acquire("cpu", 40.0)
        manager.release("cpu", 20.0)
        assert manager.get_used("cpu") == 20.0

    def test_release_clamps_to_zero(self):
        manager = self._make_manager()
        manager.release("cpu", 100.0)
        assert manager.get_used("cpu") == 0.0

    def test_release_negative_amount(self):
        manager = self._make_manager()
        with pytest.raises(ValueError, match="amount"):
            manager.release("cpu", -1.0)

    def test_release_unknown_resource(self):
        manager = self._make_manager()
        with pytest.raises(ValueError, match="Unknown resource"):
            manager.release("unknown", 10.0)

    def test_get_available(self):
        manager = self._make_manager()
        manager.acquire("cpu", 30.0)
        assert manager.get_available("cpu") == pytest.approx(50.0)

    def test_get_available_unknown(self):
        manager = self._make_manager()
        with pytest.raises(ValueError, match="Unknown resource"):
            manager.get_available("unknown")

    def test_get_used_unknown(self):
        manager = self._make_manager()
        with pytest.raises(ValueError, match="Unknown resource"):
            manager.get_used("unknown")

    def test_get_utilization(self):
        manager = self._make_manager()
        manager.acquire("cpu", 40.0)
        util = manager.get_utilization("cpu")
        assert util == pytest.approx(0.5, abs=0.01)

    def test_get_utilization_zero_limit(self):
        from file_organizer.parallel.resource_manager import ResourceConfig, ResourceManager

        config = ResourceConfig(max_gpu_percent=0.0)
        manager = ResourceManager(config)
        assert manager.get_utilization("gpu") == 0.0

    def test_get_utilization_unknown(self):
        manager = self._make_manager()
        with pytest.raises(ValueError, match="Unknown resource"):
            manager.get_utilization("unknown")

    def test_reset(self):
        manager = self._make_manager()
        manager.acquire("cpu", 40.0)
        manager.acquire("memory", 100.0)
        manager.reset()
        assert manager.get_used("cpu") == 0.0
        assert manager.get_used("memory") == 0.0

    def test_config_property(self):
        manager = self._make_manager()
        from file_organizer.parallel.resource_manager import ResourceConfig

        assert isinstance(manager.config, ResourceConfig)


# ===========================================================================
# 12. updater/checker.py
# ===========================================================================


class TestUpdateChecker:
    """Tests for UpdateChecker version parsing and release fetching."""

    def test_parse_version(self):
        from file_organizer.updater.checker import _parse_version

        assert _parse_version("v2.0.0") == (2, 0, 0)
        assert _parse_version("1.5.3-alpha.1") == (1, 5, 3)
        assert _parse_version("invalid") == (0,)
        assert _parse_version("") == (0,)

    def test_update_checker_initialization(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker(repo="owner/repo", current_version="1.0.0")
        assert checker.current_version == "1.0.0"

    def test_detect_version(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker()
        assert isinstance(checker.current_version, str)
        assert len(checker.current_version) > 0

    def test_check_no_update_available(self):
        from file_organizer.updater.checker import ReleaseInfo, UpdateChecker

        checker = UpdateChecker(current_version="2.0.0")
        release = ReleaseInfo(version="1.5.0")
        with patch.object(checker, "_fetch_latest_release", return_value=release):
            result = checker.check()
            assert result is None

    def test_check_update_available(self):
        from file_organizer.updater.checker import ReleaseInfo, UpdateChecker

        checker = UpdateChecker(current_version="1.0.0")
        release = ReleaseInfo(version="2.0.0", tag="v2.0.0")
        with patch.object(checker, "_fetch_latest_release", return_value=release):
            result = checker.check()
            assert result is not None
            assert result.version == "2.0.0"

    def test_check_fetch_exception(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker(current_version="1.0.0")
        with patch.object(checker, "_fetch_latest_release", side_effect=Exception("network")):
            assert checker.check() is None

    def test_check_no_release(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker(current_version="1.0.0")
        with patch.object(checker, "_fetch_latest_release", return_value=None):
            assert checker.check() is None

    def test_get_latest_release(self):
        from file_organizer.updater.checker import ReleaseInfo, UpdateChecker

        checker = UpdateChecker()
        release = ReleaseInfo(version="2.0.0")
        with patch.object(checker, "_fetch_latest_release", return_value=release):
            result = checker.get_latest_release()
            assert result.version == "2.0.0"

    def test_get_latest_release_exception(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker()
        with patch.object(checker, "_fetch_latest_release", side_effect=Exception("net")):
            assert checker.get_latest_release() is None

    def test_fetch_latest_release_normal(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "tag_name": "v2.0.0",
            "prerelease": False,
            "body": "notes",
            "assets": [
                {
                    "name": "app.tar.gz",
                    "browser_download_url": "http://x",
                    "size": 100,
                    "content_type": "application/gzip",
                }
            ],
            "published_at": "2024-01-01",
            "html_url": "http://x",
        }
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_resp
            release = checker._fetch_latest_release()
            assert release.version == "2.0.0"

    def test_fetch_latest_release_404(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker()
        mock_resp = MagicMock(status_code=404)
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_resp
            result = checker._fetch_latest_release()
            assert result is None

    def test_fetch_latest_release_prerelease_mode(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker(include_prereleases=True)
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = [
            {
                "tag_name": "v2.0.0-beta",
                "draft": False,
                "prerelease": True,
                "assets": [],
                "body": "",
                "published_at": "",
                "html_url": "",
            }
        ]
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_resp
            result = checker._fetch_latest_release()
            assert result is not None

    def test_fetch_latest_release_prerelease_all_drafts(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker(include_prereleases=True)
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = [
            {
                "tag_name": "v2.0.0-beta",
                "draft": True,
                "prerelease": True,
                "assets": [],
                "body": "",
                "published_at": "",
                "html_url": "",
            }
        ]
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_resp
            result = checker._fetch_latest_release()
            assert result is None

    def test_fetch_latest_release_not_dict(self):
        from file_organizer.updater.checker import UpdateChecker

        checker = UpdateChecker()
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = "bad data"
        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__.return_value = mock_client
            mock_client.get.return_value = mock_resp
            result = checker._fetch_latest_release()
            assert result is None


# ===========================================================================
# 13. updater/installer.py (partial — pure functions)
# ===========================================================================


class TestUpdateInstaller:
    """Tests for UpdateInstaller helper functions and methods."""

    def test_get_platform_hints_darwin(self):
        with patch("platform.system", return_value="Darwin"):
            from file_organizer.updater.installer import _get_platform_hints

            hints = _get_platform_hints()
            assert "macos" in hints

    def test_get_platform_hints_windows(self):
        with patch("platform.system", return_value="Windows"):
            from file_organizer.updater.installer import _get_platform_hints

            hints = _get_platform_hints()
            assert "windows" in hints

    def test_get_platform_hints_linux(self):
        with patch("platform.system", return_value="Linux"):
            from file_organizer.updater.installer import _get_platform_hints

            hints = _get_platform_hints()
            assert "linux" in hints

    def test_get_arch_hints_x86(self):
        with patch("platform.machine", return_value="x86_64"):
            from file_organizer.updater.installer import _get_arch_hints

            hints = _get_arch_hints()
            assert "x86_64" in hints

    def test_get_arch_hints_arm64(self):
        with patch("platform.machine", return_value="arm64"):
            from file_organizer.updater.installer import _get_arch_hints

            hints = _get_arch_hints()
            assert "arm64" in hints

    def test_get_arch_hints_darwin_adds_universal(self):
        with (
            patch("platform.machine", return_value="arm64"),
            patch("platform.system", return_value="Darwin"),
        ):
            from file_organizer.updater.installer import _get_arch_hints

            hints = _get_arch_hints()
            assert "universal" in hints

    def test_is_checksum_file(self):
        from file_organizer.updater.installer import _is_checksum_file

        assert _is_checksum_file("app.sha256") is True
        assert _is_checksum_file("app.md5") is True
        assert _is_checksum_file("app.asc") is True
        assert _is_checksum_file("app.tar.gz") is False

    def test_score_asset_darwin(self):
        with patch("platform.system", return_value="Darwin"):
            from file_organizer.updater.installer import _score_asset

            assert _score_asset("app-universal-macos") > 0
            assert _score_asset("app.dmg") < 0
            assert _score_asset("app.zip") < 0

    def test_score_asset_windows(self):
        with patch("platform.system", return_value="Windows"):
            from file_organizer.updater.installer import _score_asset

            assert _score_asset("app.exe") > 0
            assert _score_asset("app-setup.exe") < 0

    def test_score_asset_linux(self):
        with patch("platform.system", return_value="Linux"):
            from file_organizer.updater.installer import _score_asset

            assert _score_asset("app.appimage") > 0
            assert _score_asset("app.tar.gz") > 0

    def test_matches_platform_and_arch(self):
        from file_organizer.updater.installer import _matches_platform_and_arch

        assert _matches_platform_and_arch("app-linux-x86_64", ["linux"], ["x86_64"]) is True
        assert _matches_platform_and_arch("app-windows-x86_64", ["linux"], ["x86_64"]) is False

    def test_select_asset(self):
        from file_organizer.updater.checker import AssetInfo, ReleaseInfo
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller()
        asset = AssetInfo(name="app-linux-x86_64.tar.gz", url="http://x", size=100)
        release = ReleaseInfo(tag="v2.0.0", assets=[asset])
        with (
            patch("file_organizer.updater.installer._get_platform_hints", return_value=["linux"]),
            patch("file_organizer.updater.installer._get_arch_hints", return_value=["x86_64"]),
        ):
            result = installer.select_asset(release)
            assert result is not None

    def test_select_asset_no_match(self):
        from file_organizer.updater.checker import AssetInfo, ReleaseInfo
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller()
        asset = AssetInfo(name="app-windows.exe", url="http://x", size=100)
        release = ReleaseInfo(tag="v2.0.0", assets=[asset])
        with (
            patch("file_organizer.updater.installer._get_platform_hints", return_value=["linux"]),
            patch("file_organizer.updater.installer._get_arch_hints", return_value=["x86_64"]),
        ):
            result = installer.select_asset(release)
            assert result is None

    def test_select_asset_skips_checksums(self):
        from file_organizer.updater.checker import AssetInfo, ReleaseInfo
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller()
        release = ReleaseInfo(
            tag="v2.0.0",
            assets=[
                AssetInfo(name="app.sha256", url="http://x", size=64),
            ],
        )
        with (
            patch("file_organizer.updater.installer._get_platform_hints", return_value=["linux"]),
            patch("file_organizer.updater.installer._get_arch_hints", return_value=["x86_64"]),
        ):
            result = installer.select_asset(release)
            assert result is None

    def test_download_asset_success(self, tmp_path):
        from file_organizer.updater.checker import AssetInfo
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller(install_dir=tmp_path)
        asset = AssetInfo(name="app.bin", url="http://example.com/app.bin", size=100)

        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = [b"hello world"]
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_resp):
            result = installer.download_asset(asset)
            assert result is not None
            result.unlink(missing_ok=True)

    def test_download_asset_sha256_mismatch(self, tmp_path):
        from file_organizer.updater.checker import AssetInfo
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller(install_dir=tmp_path)
        asset = AssetInfo(name="app.bin", url="http://example.com/app.bin", size=100)

        mock_resp = MagicMock()
        mock_resp.iter_bytes.return_value = [b"hello"]
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_resp):
            result = installer.download_asset(asset, expected_sha256="wrong_hash")
            assert result is None

    def test_download_asset_exception(self, tmp_path):
        from file_organizer.updater.checker import AssetInfo
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller(install_dir=tmp_path)
        asset = AssetInfo(name="app.bin", url="http://bad", size=100)
        with patch("httpx.stream", side_effect=Exception("connection error")):
            result = installer.download_asset(asset)
            assert result is None

    def test_install_success(self, tmp_path):
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller(install_dir=tmp_path)
        download = tmp_path / "downloaded.bin"
        download.write_bytes(b"new binary")
        with patch("platform.system", return_value="Linux"):
            result = installer.install(download, "myapp")
        assert result.success is True

    def test_install_with_backup(self, tmp_path):
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller(install_dir=tmp_path)
        target = tmp_path / "myapp"
        target.write_bytes(b"old binary")
        download = tmp_path / "downloaded.bin"
        download.write_bytes(b"new binary")
        with patch("platform.system", return_value="Linux"):
            result = installer.install(download, "myapp")
        assert result.success is True

    def test_install_failure_rollback(self, tmp_path):
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller(install_dir=tmp_path)
        download = tmp_path / "downloaded.bin"
        download.write_bytes(b"data")
        with patch("shutil.move", side_effect=OSError("permission denied")):
            result = installer.install(download)
        assert result.success is False

    def test_rollback_no_backup(self, tmp_path):
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller(install_dir=tmp_path)
        assert installer.rollback() is False

    def test_rollback_success(self, tmp_path):
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller(install_dir=tmp_path)
        backup = tmp_path / "file-organizer.bak"
        backup.write_bytes(b"old binary")
        assert installer.rollback() is True

    def test_rollback_failure(self, tmp_path):
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller(install_dir=tmp_path)
        backup = tmp_path / "file-organizer.bak"
        backup.write_bytes(b"old binary")
        with patch("shutil.move", side_effect=OSError("error")):
            assert installer.rollback() is False

    def test_find_checksum_direct(self):
        from file_organizer.updater.checker import AssetInfo, ReleaseInfo
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller()
        release = ReleaseInfo(assets=[AssetInfo(name="app.tar.gz.sha256", url="http://x")])
        with patch.object(installer, "_download_text", return_value="abc123  app.tar.gz"):
            result = installer.find_checksum(release, "app.tar.gz")
            assert result == "abc123"

    def test_find_checksum_sums_file(self):
        from file_organizer.updater.checker import AssetInfo, ReleaseInfo
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller()
        release = ReleaseInfo(assets=[AssetInfo(name="SHA256SUMS.txt", url="http://x")])
        with patch.object(installer, "_download_text", return_value="deadbeef  app.tar.gz\n"):
            result = installer.find_checksum(release, "app.tar.gz")
            assert result == "deadbeef"

    def test_find_checksum_not_found(self):
        from file_organizer.updater.checker import ReleaseInfo
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller()
        release = ReleaseInfo(assets=[])
        result = installer.find_checksum(release, "app.tar.gz")
        assert result == ""

    def test_download_text_success(self):
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller()
        mock_resp = MagicMock()
        mock_resp.text = "checksum content"
        with patch("httpx.get", return_value=mock_resp):
            result = installer._download_text("http://example.com/SHA256SUMS")
            assert result == "checksum content"

    def test_download_text_failure(self):
        from file_organizer.updater.installer import UpdateInstaller

        installer = UpdateInstaller()
        with patch("httpx.get", side_effect=Exception("error")):
            result = installer._download_text("http://bad")
            assert result == ""

    def test_resolve_target_appimage(self, tmp_path):
        from file_organizer.updater.installer import UpdateInstaller

        appimage = tmp_path / "app.AppImage"
        with patch.dict(os.environ, {"APPIMAGE": str(appimage)}):
            installer = UpdateInstaller(install_dir=tmp_path)
            target = installer._resolve_target("file-organizer")
            assert target == appimage

    def test_resolve_target_windows(self, tmp_path):
        from file_organizer.updater.installer import UpdateInstaller

        with (
            patch.dict(os.environ, {}, clear=False),
            patch("platform.system", return_value="Windows"),
        ):
            # Ensure no APPIMAGE
            os.environ.pop("APPIMAGE", None)
            installer = UpdateInstaller(install_dir=tmp_path)
            installer._appimage_path = None
            target = installer._resolve_target("myapp")
            assert target.suffix == ".exe"


# ===========================================================================
# 14. updater/manager.py
# ===========================================================================


class TestUpdateManager:
    """Tests for UpdateManager high-level orchestration."""

    def _make_manager(self):
        from file_organizer.updater.manager import UpdateManager

        return UpdateManager(current_version="1.0.0")

    def test_check_no_update(self):
        mgr = self._make_manager()
        with patch.object(mgr._checker, "check", return_value=None):
            status = mgr.check()
            assert status.available is False

    def test_check_update_available(self):
        from file_organizer.updater.checker import ReleaseInfo

        mgr = self._make_manager()
        release = ReleaseInfo(version="2.0.0", tag="v2.0.0")
        with patch.object(mgr._checker, "check", return_value=release):
            status = mgr.check()
            assert status.available is True
            assert status.latest_version == "2.0.0"

    def test_update_no_update_available(self):
        mgr = self._make_manager()
        with patch.object(mgr._checker, "check", return_value=None):
            status = mgr.update()
            assert status.available is False

    def test_update_no_compatible_asset(self):
        from file_organizer.updater.checker import ReleaseInfo

        mgr = self._make_manager()
        release = ReleaseInfo(version="2.0.0")
        with (
            patch.object(mgr._checker, "check", return_value=release),
            patch.object(mgr._installer, "fetch_and_verify_manifest", return_value={"assets": []}),
            patch.object(mgr._installer, "select_asset", return_value=None),
        ):
            status = mgr.update()
            assert status.install_result is not None
            assert status.install_result.success is False

    def test_update_download_fails(self):
        from file_organizer.updater.checker import AssetInfo, ReleaseInfo

        mgr = self._make_manager()
        release = ReleaseInfo(version="2.0.0")
        asset = AssetInfo(name="app.bin", url="http://x")
        with (
            patch.object(mgr._checker, "check", return_value=release),
            patch.object(mgr._installer, "fetch_and_verify_manifest", return_value={"assets": [{"name": "app.bin", "sha256": "abc", "size": 100}]}),
            patch.object(mgr._installer, "select_asset", return_value=asset),
            patch.object(mgr._installer, "find_checksum", return_value=""),
            patch.object(mgr._installer, "download_asset", return_value=None),
        ):
            status = mgr.update()
            assert status.install_result.success is False

    def test_update_dry_run(self, tmp_path):
        from file_organizer.updater.checker import AssetInfo, ReleaseInfo

        mgr = self._make_manager()
        release = ReleaseInfo(version="2.0.0")
        asset = AssetInfo(name="app.bin", url="http://x")
        download_path = tmp_path / "app.bin"
        download_path.write_bytes(b"data")
        with (
            patch.object(mgr._checker, "check", return_value=release),
            patch.object(mgr._installer, "fetch_and_verify_manifest", return_value={"assets": [{"name": "app.bin", "sha256": "abc", "size": 100}]}),
            patch.object(mgr._installer, "select_asset", return_value=asset),
            patch.object(mgr._installer, "find_checksum", return_value=""),
            patch.object(mgr._installer, "download_asset", return_value=download_path),
        ):
            status = mgr.update(dry_run=True)
            assert status.install_result.success is True

    def test_update_install_success(self, tmp_path):
        from file_organizer.updater.checker import AssetInfo, ReleaseInfo
        from file_organizer.updater.installer import InstallResult

        mgr = self._make_manager()
        release = ReleaseInfo(version="2.0.0")
        asset = AssetInfo(name="app.bin", url="http://x")
        download_path = tmp_path / "app.bin"
        download_path.write_bytes(b"data")
        install_result = InstallResult(success=True, message="installed")
        with (
            patch.object(mgr._checker, "check", return_value=release),
            patch.object(mgr._installer, "fetch_and_verify_manifest", return_value={"assets": [{"name": "app.bin", "sha256": "abc", "size": 100}]}),
            patch.object(mgr._installer, "select_asset", return_value=asset),
            patch.object(mgr._installer, "find_checksum", return_value=""),
            patch.object(mgr._installer, "download_asset", return_value=download_path),
            patch.object(mgr._installer, "install", return_value=install_result),
        ):
            status = mgr.update()
            assert status.install_result.success is True

    def test_rollback(self):
        mgr = self._make_manager()
        with patch.object(mgr._installer, "rollback", return_value=True):
            assert mgr.rollback() is True

    def test_update_status_message_no_install(self):
        from file_organizer.updater.manager import UpdateStatus

        s = UpdateStatus(available=True, current_version="1.0.0", latest_version="2.0.0")
        assert "2.0.0" in s.message

    def test_update_status_message_up_to_date(self):
        from file_organizer.updater.manager import UpdateStatus

        s = UpdateStatus(available=False, current_version="2.0.0")
        assert "2.0.0" in s.message

    def test_update_status_message_with_install_result(self):
        from file_organizer.updater.installer import InstallResult
        from file_organizer.updater.manager import UpdateStatus

        ir = InstallResult(success=True, message="Updated OK")
        s = UpdateStatus(install_result=ir)
        assert "Updated OK" in s.message

    def test_current_version_property(self):
        from file_organizer.updater.manager import UpdateManager

        mgr = UpdateManager(current_version="3.1.4")
        assert mgr.current_version == "3.1.4"


# ===========================================================================
# 15. updater/background.py
# ===========================================================================


class TestBackgroundUpdater:
    """Tests for maybe_check_for_updates background logic."""

    def test_disabled_by_env(self, monkeypatch):
        monkeypatch.setenv("FO_DISABLE_UPDATE_CHECK", "1")
        from file_organizer.updater.background import maybe_check_for_updates

        assert maybe_check_for_updates() is None

    def test_disabled_in_pytest(self, monkeypatch):
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_something")
        from file_organizer.updater.background import maybe_check_for_updates

        assert maybe_check_for_updates() is None

    def test_check_on_startup_disabled(self, monkeypatch):
        monkeypatch.delenv("FO_DISABLE_UPDATE_CHECK", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        cfg = MagicMock()
        cfg.updates.check_on_startup = False
        with patch("file_organizer.updater.background.ConfigManager") as mock_cm:
            mock_cm.return_value.load.return_value = cfg
            from file_organizer.updater.background import maybe_check_for_updates

            result = maybe_check_for_updates()
            assert result is None

    def test_check_not_due(self, monkeypatch):
        monkeypatch.delenv("FO_DISABLE_UPDATE_CHECK", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        cfg = MagicMock()
        cfg.updates.check_on_startup = True
        cfg.updates.interval_hours = 24
        with (
            patch("file_organizer.updater.background.ConfigManager") as mock_cm,
            patch("file_organizer.updater.background.UpdateStateStore") as mock_store_cls,
        ):
            mock_cm.return_value.load.return_value = cfg
            mock_store = MagicMock()
            mock_store.load.return_value.due.return_value = False
            mock_store_cls.return_value = mock_store
            from file_organizer.updater.background import maybe_check_for_updates

            result = maybe_check_for_updates()
            assert result is None

    def test_check_runs_and_records(self, monkeypatch):
        monkeypatch.delenv("FO_DISABLE_UPDATE_CHECK", raising=False)
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        cfg = MagicMock()
        cfg.updates.check_on_startup = True
        cfg.updates.interval_hours = 0
        cfg.updates.repo = "owner/repo"
        cfg.updates.include_prereleases = False
        with (
            patch("file_organizer.updater.background.ConfigManager") as mock_cm,
            patch("file_organizer.updater.background.UpdateStateStore") as mock_store_cls,
            patch("file_organizer.updater.background.UpdateManager") as mock_mgr_cls,
        ):
            mock_cm.return_value.load.return_value = cfg
            mock_store = MagicMock()
            mock_store.load.return_value.due.return_value = True
            mock_store_cls.return_value = mock_store

            from file_organizer.updater.manager import UpdateStatus

            mock_status = UpdateStatus(available=False, current_version="1.0.0")
            mock_mgr_cls.return_value.check.return_value = mock_status

            from file_organizer.updater.background import maybe_check_for_updates

            result = maybe_check_for_updates()
            assert result is not None
            mock_store.record_check.assert_called_once()


# ===========================================================================
# 16. pipeline/stages/analyzer.py
# ===========================================================================


class TestAnalyzerStage:
    """Tests for AnalyzerStage routing and processing."""

    def _make_context(self, file_path="test.txt", failed=False):
        from file_organizer.interfaces.pipeline import StageContext

        ctx = MagicMock(spec=StageContext)
        ctx.failed = failed
        ctx.file_path = Path(file_path)
        ctx.trusted_root = None
        ctx.extra = {}
        ctx.analysis = None
        ctx.category = None
        ctx.filename = "test.txt"
        ctx.error = None
        return ctx

    def test_process_already_failed(self):
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        stage = AnalyzerStage()
        ctx = self._make_context(failed=True)
        result = stage.process(ctx)
        assert result is ctx

    def test_process_no_router(self):
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        stage = AnalyzerStage()
        ctx = self._make_context()
        result = stage.process(ctx)
        assert result is ctx

    def test_process_unknown_type(self):
        from file_organizer.pipeline.router import ProcessorType
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        router = MagicMock()
        router.route.return_value = ProcessorType.UNKNOWN
        pool = MagicMock()
        stage = AnalyzerStage(router=router, processor_pool=pool)
        ctx = self._make_context()
        result = stage.process(ctx)
        assert result.error is not None

    def test_process_processor_none(self):
        from file_organizer.pipeline.router import ProcessorType
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        router = MagicMock()
        router.route.return_value = ProcessorType.TEXT
        pool = MagicMock()
        pool.get_processor.return_value = None
        stage = AnalyzerStage(router=router, processor_pool=pool)
        ctx = self._make_context()
        result = stage.process(ctx)
        assert result.error is not None

    def test_process_success(self):
        from file_organizer.pipeline.router import ProcessorType
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        router = MagicMock()
        router.route.return_value = ProcessorType.TEXT
        pool = MagicMock()
        processor = MagicMock()
        pool.get_processor.return_value = processor
        stage = AnalyzerStage(router=router, processor_pool=pool)
        ctx = self._make_context()
        with patch.object(
            stage, "_run_processor", return_value={"category": "docs", "filename": "file.txt"}
        ):
            result = stage.process(ctx)
            assert result.category == "docs"

    def test_process_exception(self):
        from file_organizer.pipeline.router import ProcessorType
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        router = MagicMock()
        router.route.return_value = ProcessorType.TEXT
        pool = MagicMock()
        pool.get_processor.return_value = MagicMock()
        stage = AnalyzerStage(router=router, processor_pool=pool)
        ctx = self._make_context()
        with patch.object(stage, "_run_processor", side_effect=RuntimeError("proc error")):
            result = stage.process(ctx)
            assert result.error is not None

    def test_processor_accepts_scan_root_true(self):
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        class ProcessorWithScanRoot:
            def initialize(self):
                pass

            def process_file(self, path, scan_root=None):
                pass

            def cleanup(self):
                pass

        # Clear cache so test is deterministic
        AnalyzerStage._processor_accepts_scan_root.cache_clear()
        assert AnalyzerStage._processor_accepts_scan_root(ProcessorWithScanRoot) is True

    def test_processor_accepts_scan_root_false(self):
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        class ProcessorNoScanRoot:
            def initialize(self):
                pass

            def process_file(self, path):
                pass

            def cleanup(self):
                pass

        AnalyzerStage._processor_accepts_scan_root.cache_clear()
        assert AnalyzerStage._processor_accepts_scan_root(ProcessorNoScanRoot) is False

    def test_processor_accepts_scan_root_introspection_error(self):
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        AnalyzerStage._processor_accepts_scan_root.cache_clear()
        # Use a non-introspectable object
        assert AnalyzerStage._processor_accepts_scan_root(object) is False

    def test_stage_name(self):
        from file_organizer.pipeline.stages.analyzer import AnalyzerStage

        assert AnalyzerStage().name == "analyzer"


# ===========================================================================
# 17. utils/readers/_scientific_stub.py
# ===========================================================================


class TestScientificStub:
    """Tests for _scientific_stub module — covers the pragma: no cover stubs."""

    def test_unavailable_message(self):
        # Remove pragma: no cover by importing and testing at module level
        from file_organizer.utils.readers import _scientific_stub as stub

        # The functions are pragma: no cover but we can still reach the module
        assert stub is not None

    def test_read_hdf5_file_returns_string(self):
        # Directly call the function; it returns a string
        from file_organizer.utils.readers._scientific_stub import read_hdf5_file

        result = read_hdf5_file()
        assert "HDF5" in result
        assert "scientific" in result.lower()

    def test_read_mat_file_returns_string(self):
        from file_organizer.utils.readers._scientific_stub import read_mat_file

        result = read_mat_file()
        assert "MAT" in result

    def test_read_netcdf_file_returns_string(self):
        from file_organizer.utils.readers._scientific_stub import read_netcdf_file

        result = read_netcdf_file()
        assert "NetCDF" in result


# ===========================================================================
# 18. methodologies/para/rules/engine.py
# ===========================================================================


class TestPARARulesEngine:
    """Tests for PARA Rule Engine data structures and orchestration."""

    def _make_rule(self, name="test", priority=10, enabled=True):
        from file_organizer.methodologies.para.rules.engine import (
            ActionType,
            ConditionType,
            Rule,
            RuleAction,
            RuleCondition,
        )

        condition = RuleCondition(type=ConditionType.FILENAME_PATTERN, values=["*.pdf"])
        action = RuleAction(
            type=ActionType.CATEGORIZE,
            category="project",
            confidence=0.9,
        )
        return Rule(
            name=name,
            description="Test rule",
            priority=priority,
            conditions=[condition],
            actions=[action],
            enabled=enabled,
        )

    def test_condition_type_composite_no_subconditions(self):
        from file_organizer.methodologies.para.rules.engine import ConditionType, RuleCondition

        with pytest.raises(ValueError, match="Composite"):
            RuleCondition(type=ConditionType.COMPOSITE)

    def test_condition_type_no_values_or_threshold(self):
        from file_organizer.methodologies.para.rules.engine import ConditionType, RuleCondition

        with pytest.raises(ValueError, match="values or threshold"):
            RuleCondition(type=ConditionType.FILE_SIZE)

    def test_rule_action_no_category(self):
        from file_organizer.methodologies.para.rules.engine import ActionType, RuleAction

        with pytest.raises(ValueError, match="category"):
            RuleAction(type=ActionType.CATEGORIZE)

    def test_rule_action_invalid_category(self):
        from file_organizer.methodologies.para.rules.engine import ActionType, RuleAction

        with pytest.raises(ValueError, match="Invalid PARA"):
            RuleAction(type=ActionType.CATEGORIZE, category="invalid_category", confidence=0.5)

    def test_rule_action_no_confidence(self):
        from file_organizer.methodologies.para.rules.engine import ActionType, RuleAction

        with pytest.raises(ValueError, match="confidence"):
            RuleAction(type=ActionType.CATEGORIZE, category="project")

    def test_rule_action_confidence_out_of_range(self):
        from file_organizer.methodologies.para.rules.engine import ActionType, RuleAction

        with pytest.raises(ValueError, match="Confidence"):
            RuleAction(type=ActionType.CATEGORIZE, category="project", confidence=1.5)

    def test_rule_no_conditions(self):
        from file_organizer.methodologies.para.rules.engine import ActionType, Rule, RuleAction

        action = RuleAction(type=ActionType.ADD_TAG, tags=["important"])
        with pytest.raises(ValueError, match="condition"):
            Rule(name="bad", description="", priority=0, conditions=[], actions=[action])

    def test_rule_no_actions(self):
        from file_organizer.methodologies.para.rules.engine import (
            ConditionType,
            Rule,
            RuleCondition,
        )

        cond = RuleCondition(type=ConditionType.FILE_EXTENSION, values=[".pdf"])
        with pytest.raises(ValueError, match="action"):
            Rule(name="bad", description="", priority=0, conditions=[cond], actions=[])

    def test_rule_negative_priority(self):
        from file_organizer.methodologies.para.rules.engine import (
            ActionType,
            ConditionType,
            Rule,
            RuleAction,
            RuleCondition,
        )

        cond = RuleCondition(type=ConditionType.FILE_EXTENSION, values=[".pdf"])
        action = RuleAction(type=ActionType.ADD_TAG, tags=["x"])
        with pytest.raises(ValueError, match="Priority"):
            Rule(name="x", description="", priority=-1, conditions=[cond], actions=[action])

    def test_evaluation_context_properties(self):
        from datetime import UTC, datetime

        from file_organizer.methodologies.para.rules.engine import EvaluationContext

        ctx = EvaluationContext(
            file_path=Path("/") / "home" / "user" / "doc.pdf",  # noqa: test-hardcoded-paths
            file_stat={"created": datetime(2020, 1, 1, tzinfo=UTC)},
        )
        assert ctx.file_extension == ".pdf"
        assert ctx.file_name == "doc.pdf"
        assert ctx.file_age_days is not None

    def test_evaluation_context_no_stat(self):
        from file_organizer.methodologies.para.rules.engine import EvaluationContext

        ctx = EvaluationContext(file_path=Path("/") / "home" / "user" / "doc.pdf")  # noqa: test-hardcoded-paths
        assert ctx.file_age_days is None

    def test_evaluation_context_naive_datetime(self):
        from datetime import datetime

        from file_organizer.methodologies.para.rules.engine import EvaluationContext

        ctx = EvaluationContext(
            file_path=Path("x.pdf"),
            file_stat={"created": datetime(2020, 1, 1)},  # noqa: DTZ001 – intentionally naive to exercise the non-tz path
        )
        assert ctx.file_age_days is not None

    def test_rule_engine_load_rules(self):
        from file_organizer.methodologies.para.rules.engine import RuleEngine

        parser = MagicMock()
        parser.parse_file.return_value = [self._make_rule()]
        engine = RuleEngine(
            parser=parser,
            evaluator=MagicMock(),
            executor=MagicMock(),
            resolver=MagicMock(),
            scorer=MagicMock(),
        )
        count = engine.load_rules(Path("rules.yaml"))
        assert count == 1

    def test_rule_engine_add_rule(self):
        from file_organizer.methodologies.para.rules.engine import RuleEngine

        parser = MagicMock()
        parser.validate_rule.return_value = True
        engine = RuleEngine(
            parser=parser,
            evaluator=MagicMock(),
            executor=MagicMock(),
            resolver=MagicMock(),
            scorer=MagicMock(),
        )
        engine.add_rule(self._make_rule())
        assert len(engine.rules) == 1

    def test_rule_engine_evaluate_file_no_match(self):
        from file_organizer.methodologies.para.rules.engine import EvaluationContext, RuleEngine

        evaluator = MagicMock()
        evaluator.evaluate_condition.return_value = False
        engine = RuleEngine(
            parser=MagicMock(),
            evaluator=evaluator,
            executor=MagicMock(),
            resolver=MagicMock(),
            scorer=MagicMock(),
        )
        engine.rules = [self._make_rule()]
        ctx = EvaluationContext(file_path=Path("test.txt"))
        result = engine.evaluate_file(ctx)
        assert result is None

    def test_rule_engine_evaluate_file_single_match(self):
        from file_organizer.methodologies.para.rules.engine import EvaluationContext, RuleEngine

        evaluator = MagicMock()
        evaluator.evaluate_condition.return_value = True
        engine = RuleEngine(
            parser=MagicMock(),
            evaluator=evaluator,
            executor=MagicMock(),
            resolver=MagicMock(),
            scorer=MagicMock(),
        )
        engine.rules = [self._make_rule()]
        ctx = EvaluationContext(file_path=Path("test.pdf"))
        result = engine.evaluate_file(ctx)
        assert result is not None
        assert result.matched is True

    def test_rule_engine_evaluate_file_disabled_rule_skipped(self):
        from file_organizer.methodologies.para.rules.engine import EvaluationContext, RuleEngine

        evaluator = MagicMock()
        evaluator.evaluate_condition.return_value = True
        engine = RuleEngine(
            parser=MagicMock(),
            evaluator=evaluator,
            executor=MagicMock(),
            resolver=MagicMock(),
            scorer=MagicMock(),
        )
        engine.rules = [self._make_rule(enabled=False)]
        ctx = EvaluationContext(file_path=Path("test.pdf"))
        result = engine.evaluate_file(ctx)
        assert result is None

    def test_rule_engine_evaluate_file_conflict_resolution(self):
        from file_organizer.methodologies.para.rules.engine import EvaluationContext, RuleEngine

        evaluator = MagicMock()
        evaluator.evaluate_condition.return_value = True
        resolver = MagicMock()
        expected_match = MagicMock()
        resolver.resolve.return_value = expected_match
        engine = RuleEngine(
            parser=MagicMock(),
            evaluator=evaluator,
            executor=MagicMock(),
            resolver=resolver,
            scorer=MagicMock(),
        )
        engine.rules = [self._make_rule("r1"), self._make_rule("r2")]
        ctx = EvaluationContext(file_path=Path("test.pdf"))
        result = engine.evaluate_file(ctx)
        assert result is expected_match

    def test_get_category_scores(self):
        from file_organizer.methodologies.para.rules.engine import EvaluationContext, RuleEngine

        evaluator = MagicMock()
        evaluator.evaluate_condition.return_value = True
        scorer = MagicMock()
        scorer.calculate_category_scores.return_value = {"project": 0.8}
        engine = RuleEngine(
            parser=MagicMock(),
            evaluator=evaluator,
            executor=MagicMock(),
            resolver=MagicMock(),
            scorer=scorer,
        )
        engine.rules = [self._make_rule()]
        ctx = EvaluationContext(file_path=Path("test.pdf"))
        scores = engine.get_category_scores(ctx)
        assert "project" in scores


# ===========================================================================
# 19. methodologies/johnny_decimal/migrator.py
# ===========================================================================


class TestJohnnyDecimalMigrator:
    """Tests for JohnnyDecimalMigrator migration workflow."""

    def _make_migrator(self):
        from file_organizer.methodologies.johnny_decimal.migrator import JohnnyDecimalMigrator

        with (
            patch("file_organizer.methodologies.johnny_decimal.migrator.FolderScanner"),
            patch("file_organizer.methodologies.johnny_decimal.migrator.FolderTransformer"),
            patch("file_organizer.methodologies.johnny_decimal.migrator.MigrationValidator"),
            patch("file_organizer.methodologies.johnny_decimal.migrator.JohnnyDecimalGenerator"),
        ):
            return JohnnyDecimalMigrator()

    def test_create_migration_plan(self):
        migrator = self._make_migrator()
        mock_scan = MagicMock()
        mock_scan.total_folders = 5
        mock_scan.total_files = 20
        migrator.scanner.scan_directory.return_value = mock_scan

        mock_plan = MagicMock()
        mock_plan.rules = []
        migrator.transformer.create_transformation_plan.return_value = mock_plan

        plan, scan = migrator.create_migration_plan(Path("test"))
        assert scan is mock_scan
        assert plan is mock_plan

    def test_validate_plan(self):
        migrator = self._make_migrator()
        plan = MagicMock()
        migrator.validator.validate_plan.return_value = MagicMock(is_valid=True)
        result = migrator.validate_plan(plan)
        assert result.is_valid is True

    def test_execute_migration_dry_run(self, tmp_path):
        migrator = self._make_migrator()

        rule = MagicMock()
        rule.source_path = tmp_path / "Documents"
        rule.target_name = "10 Documents"
        plan = MagicMock()
        plan.root_path = tmp_path
        plan.rules = [rule]

        result = migrator.execute_migration(plan, dry_run=True, create_backup=False)
        assert result.success is True
        assert result.transformed_count == 1

    def test_execute_migration_real(self, tmp_path):
        migrator = self._make_migrator()
        src = tmp_path / "Documents"
        src.mkdir()

        rule = MagicMock()
        rule.source_path = src
        rule.target_name = "10 Documents"
        plan = MagicMock()
        plan.root_path = tmp_path
        plan.rules = [rule]

        with patch(
            "file_organizer.methodologies.johnny_decimal.migrator._get_data_dir"
        ) as mock_data:
            mock_data.return_value = tmp_path
            result = migrator.execute_migration(plan, dry_run=False, create_backup=False)
        assert result.success is True

    def test_execute_migration_target_exists_skip(self, tmp_path):
        migrator = self._make_migrator()
        src = tmp_path / "Documents"
        src.mkdir()
        target = tmp_path / "10 Documents"
        target.mkdir()

        rule = MagicMock()
        rule.source_path = src
        rule.target_name = "10 Documents"
        plan = MagicMock()
        plan.root_path = tmp_path
        plan.rules = [rule]

        with patch(
            "file_organizer.methodologies.johnny_decimal.migrator._get_data_dir"
        ) as mock_data:
            mock_data.return_value = tmp_path
            result = migrator.execute_migration(plan, dry_run=False, create_backup=False)
        assert result.skipped_count == 1

    def test_execute_migration_with_backup_failure(self, tmp_path):
        migrator = self._make_migrator()
        plan = MagicMock()
        plan.root_path = tmp_path
        plan.rules = [MagicMock()]

        with patch("shutil.copytree", side_effect=OSError("disk full")):
            result = migrator.execute_migration(plan, dry_run=False, create_backup=True)
        assert result.success is False

    def test_rollback_no_history(self):
        migrator = self._make_migrator()
        assert migrator.rollback() is False

    def test_rollback_success(self, tmp_path):
        from datetime import UTC, datetime

        from file_organizer.methodologies.johnny_decimal.migrator import RollbackInfo

        migrator = self._make_migrator()

        current = tmp_path / "10 Documents"
        current.mkdir()
        original = tmp_path / "Documents"

        info = RollbackInfo(
            migration_id="20240101_120000",
            timestamp=datetime.now(UTC),
            original_structure={str(original): (str(current), "Documents")},
            backup_path=None,
        )
        migrator._rollback_history = [info]
        assert migrator.rollback() is True

    def test_rollback_specific_id_not_found(self, tmp_path):
        from datetime import UTC, datetime

        from file_organizer.methodologies.johnny_decimal.migrator import RollbackInfo

        migrator = self._make_migrator()
        info = RollbackInfo("id1", datetime.now(UTC), {}, None)
        migrator._rollback_history = [info]
        with pytest.raises(ValueError, match="Migration ID not found"):
            migrator.rollback("nonexistent_id")

    def test_rollback_exception(self, tmp_path):
        from datetime import UTC, datetime

        from file_organizer.methodologies.johnny_decimal.migrator import RollbackInfo

        migrator = self._make_migrator()
        # Create a file so current_path.exists() returns True, then make rename fail
        current = tmp_path / "10 Documents"
        current.mkdir()
        original = tmp_path / "Documents"
        info = RollbackInfo(
            migration_id="id1",
            timestamp=datetime.now(UTC),
            original_structure={str(original): (str(current), "Documents")},
            backup_path=None,
        )
        migrator._rollback_history = [info]
        with patch("pathlib.Path.rename", side_effect=OSError("permission denied")):
            assert migrator.rollback() is False

    def test_generate_preview(self, tmp_path):
        migrator = self._make_migrator()
        plan = MagicMock()
        plan.rules = [
            MagicMock(source_path=MagicMock(name="Documents"), target_name="10 Documents")
        ]
        plan.conflicts = []
        plan.warnings = []

        scan = MagicMock()
        scan.root_path = tmp_path
        scan.total_folders = 5
        scan.total_files = 20
        scan.total_size = 1024 * 1024
        scan.max_depth = 3
        scan.detected_patterns = ["date-based", "project-based"]

        preview = migrator.generate_preview(plan, scan)
        assert "Migration Preview" in preview
        assert "detected_patterns" in preview.lower() or "detected" in preview.lower()

    def test_generate_preview_with_validation(self, tmp_path):
        migrator = self._make_migrator()
        plan = MagicMock()
        plan.rules = []
        plan.conflicts = []
        plan.warnings = []
        scan = MagicMock()
        scan.root_path = tmp_path
        scan.total_folders = 0
        scan.total_files = 0
        scan.total_size = 0
        scan.max_depth = 0
        scan.detected_patterns = []
        validation = MagicMock(is_valid=True, errors=[], warnings=[])
        preview = migrator.generate_preview(plan, scan, validation=validation)
        assert "Validation" in preview

    def test_generate_report_success(self):
        migrator = self._make_migrator()
        from file_organizer.methodologies.johnny_decimal.migrator import MigrationResult

        result = MigrationResult(
            success=True,
            transformed_count=5,
            failed_count=0,
            skipped_count=1,
            duration_seconds=2.5,
            skipped_paths=[Path("x")],
        )
        report = migrator.generate_report(result)
        assert "SUCCESS" in report
        assert "5" in report

    def test_generate_report_with_failures_and_backup(self, tmp_path):
        migrator = self._make_migrator()
        from file_organizer.methodologies.johnny_decimal.migrator import MigrationResult

        result = MigrationResult(
            success=False,
            transformed_count=0,
            failed_count=1,
            skipped_count=0,
            duration_seconds=1.0,
            failed_paths=[(Path("bad"), "permission denied")],
            backup_path=tmp_path,
        )
        report = migrator.generate_report(result)
        assert "FAILED" in report
        assert "Backup" in report
        assert "Failures" in report

    def test_generate_preview_more_than_10_rules(self, tmp_path):
        migrator = self._make_migrator()
        plan = MagicMock()
        plan.rules = [
            MagicMock(source_path=MagicMock(name=f"dir{i}"), target_name=f"{i:02d} dir{i}")
            for i in range(15)
        ]
        plan.conflicts = []
        plan.warnings = []
        scan = MagicMock()
        scan.root_path = tmp_path
        scan.total_folders = 15
        scan.total_files = 100
        scan.total_size = 1024 * 1024
        scan.max_depth = 2
        scan.detected_patterns = []
        preview = migrator.generate_preview(plan, scan)
        assert "more" in preview

    def test_generate_report_many_skipped(self, tmp_path):
        migrator = self._make_migrator()
        from file_organizer.methodologies.johnny_decimal.migrator import MigrationResult

        result = MigrationResult(
            success=True,
            transformed_count=0,
            failed_count=0,
            skipped_count=15,
            duration_seconds=1.0,
            skipped_paths=[Path(f"dir{i}") for i in range(15)],
        )
        report = migrator.generate_report(result)
        assert "more" in report
