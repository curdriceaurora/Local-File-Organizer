"""Coverage tests for plugins.registry module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.plugins.base import PluginLoadError
from file_organizer.plugins.errors import PluginNotLoadedError
from file_organizer.plugins.registry import PluginRecord, PluginRegistry
from file_organizer.plugins.security import PluginSecurityPolicy

pytestmark = pytest.mark.unit


def _make_manifest_dir(tmp_path: Path, manifest: dict | None = None) -> Path:
    plugin_dir = tmp_path / "my-plugin"
    plugin_dir.mkdir()
    m = manifest or {
        "name": "test-plugin",
        "version": "1.0.0",
        "author": "tester",
        "description": "A test plugin",
        "entry_point": "plugin.py",
    }
    (plugin_dir / "plugin.json").write_text(json.dumps(m))
    (plugin_dir / "plugin.py").write_text("# empty plugin\n")
    return plugin_dir


class TestRegistryLoadPlugin:
    @patch("file_organizer.plugins.registry.PluginExecutor")
    def test_load_plugin_success(self, mock_executor_cls, tmp_path):
        mock_executor = MagicMock()
        mock_executor_cls.return_value = mock_executor

        plugin_dir = _make_manifest_dir(tmp_path)
        registry = PluginRegistry()
        record = registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())

        assert record.name == "test-plugin"
        assert record.version == "1.0.0"
        mock_executor.start.assert_called_once()
        mock_executor.call.assert_called_once_with("on_load")

    @patch("file_organizer.plugins.registry.PluginExecutor")
    def test_load_duplicate_raises(self, mock_executor_cls, tmp_path):
        mock_executor_cls.return_value = MagicMock()

        plugin_dir = _make_manifest_dir(tmp_path)
        registry = PluginRegistry()
        registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())

        with pytest.raises(PluginLoadError, match="already loaded"):
            registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())

    def test_load_path_traversal_raises(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "evil",
            "version": "1.0.0",
            "author": "bad",
            "description": "bad",
            "entry_point": "../../../etc/passwd",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

        registry = PluginRegistry()
        with pytest.raises(PluginLoadError, match="escapes plugin directory"):
            registry.load_plugin(plugin_dir)

    def test_load_missing_entry_point_raises(self, tmp_path):
        plugin_dir = tmp_path / "my-plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "test",
            "version": "1.0.0",
            "author": "x",
            "description": "x",
            "entry_point": "nonexistent.py",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

        registry = PluginRegistry()
        with pytest.raises(PluginLoadError, match="not found"):
            registry.load_plugin(plugin_dir)

    @patch("file_organizer.plugins.registry.PluginExecutor")
    def test_load_stops_executor_on_call_failure(self, mock_executor_cls, tmp_path):
        mock_executor = MagicMock()
        mock_executor.call.side_effect = RuntimeError("on_load failed")
        mock_executor_cls.return_value = mock_executor

        plugin_dir = _make_manifest_dir(tmp_path)
        registry = PluginRegistry()

        with pytest.raises(RuntimeError, match="on_load failed"):
            registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())

        mock_executor.stop.assert_called_once()

    @patch("file_organizer.plugins.registry.PluginExecutor")
    def test_load_without_policy_builds_from_manifest(self, mock_executor_cls, tmp_path):
        mock_executor_cls.return_value = MagicMock()

        plugin_dir = _make_manifest_dir(tmp_path)
        registry = PluginRegistry()
        record = registry.load_plugin(plugin_dir)

        # Should use a policy built from manifest defaults
        assert record.policy is not None


class TestRegistryUnloadPlugin:
    def test_unload_not_loaded_raises(self):
        registry = PluginRegistry()
        with pytest.raises(PluginNotLoadedError):
            registry.unload_plugin("nonexistent")

    def test_unload_calls_on_unload_and_stops(self):
        registry = PluginRegistry()
        executor = MagicMock()
        record = PluginRecord(
            name="demo",
            version="1.0",
            plugin_dir=Path("/fake"),
            policy=MagicMock(),
            manifest={},
            executor=executor,
        )
        registry._records["demo"] = record

        registry.unload_plugin("demo")

        executor.call.assert_called_once_with("on_unload")
        executor.stop.assert_called_once()
        assert "demo" not in registry._records

    def test_unload_stops_even_if_on_unload_fails(self):
        registry = PluginRegistry()
        executor = MagicMock()
        executor.call.side_effect = RuntimeError("unload failed")
        record = PluginRecord(
            name="demo",
            version="1.0",
            plugin_dir=Path("/fake"),
            policy=MagicMock(),
            manifest={},
            executor=executor,
        )
        registry._records["demo"] = record

        with pytest.raises(RuntimeError, match="unload failed"):
            registry.unload_plugin("demo")

        executor.stop.assert_called_once()


class TestRegistryEnableDisable:
    def test_enable_calls_executor(self):
        registry = PluginRegistry()
        executor = MagicMock()
        record = PluginRecord(
            name="demo",
            version="1.0",
            plugin_dir=Path("/fake"),
            policy=MagicMock(),
            manifest={},
            executor=executor,
        )
        registry._records["demo"] = record

        registry.enable_plugin("demo")
        executor.call.assert_called_once_with("on_enable")

    def test_disable_calls_executor(self):
        registry = PluginRegistry()
        executor = MagicMock()
        record = PluginRecord(
            name="demo",
            version="1.0",
            plugin_dir=Path("/fake"),
            policy=MagicMock(),
            manifest={},
            executor=executor,
        )
        registry._records["demo"] = record

        registry.disable_plugin("demo")
        executor.call.assert_called_once_with("on_disable")

    def test_enable_not_loaded_raises(self):
        registry = PluginRegistry()
        with pytest.raises(PluginNotLoadedError):
            registry.enable_plugin("missing")


class TestRegistryQueries:
    def test_get_plugin_raises_when_missing(self):
        registry = PluginRegistry()
        with pytest.raises(PluginNotLoadedError):
            registry.get_plugin("nope")

    def test_list_plugins_sorted(self):
        registry = PluginRegistry()
        registry._records["beta"] = MagicMock()
        registry._records["alpha"] = MagicMock()

        assert registry.list_plugins() == ["alpha", "beta"]

    def test_call_all_collects_results(self):
        registry = PluginRegistry()
        executor_a = MagicMock()
        executor_a.call.return_value = "ok_a"
        executor_b = MagicMock()
        executor_b.call.side_effect = RuntimeError("fail_b")

        registry._records["a"] = PluginRecord(
            name="a",
            version="1",
            plugin_dir=Path("/"),
            policy=MagicMock(),
            manifest={},
            executor=executor_a,
        )
        registry._records["b"] = PluginRecord(
            name="b",
            version="1",
            plugin_dir=Path("/"),
            policy=MagicMock(),
            manifest={},
            executor=executor_b,
        )

        results = registry.call_all("on_event", "arg1")
        assert results["a"] == "ok_a"
        assert isinstance(results["b"], RuntimeError)

    def test_unload_all_ignores_errors(self):
        registry = PluginRegistry()
        executor_a = MagicMock()
        executor_a.call.side_effect = RuntimeError("fail")
        executor_b = MagicMock()

        registry._records["a"] = PluginRecord(
            name="a",
            version="1",
            plugin_dir=Path("/"),
            policy=MagicMock(),
            manifest={},
            executor=executor_a,
        )
        registry._records["b"] = PluginRecord(
            name="b",
            version="1",
            plugin_dir=Path("/"),
            policy=MagicMock(),
            manifest={},
            executor=executor_b,
        )

        # Should not raise
        registry.unload_all()


class TestBuildSandboxFromManifest:
    def test_defaults_to_read_only(self):
        policy = PluginRegistry._build_sandbox_from_manifest({"allowed_paths": ["/data"]})
        assert "read" in policy.allowed_operations

    def test_explicit_operations(self):
        policy = PluginRegistry._build_sandbox_from_manifest(
            {"allowed_operations": ["read", "write"]}
        )
        assert "write" in policy.allowed_operations

    def test_allow_all_operations(self):
        policy = PluginRegistry._build_sandbox_from_manifest({"allow_all_operations": True})
        assert policy.allow_all_operations is True
