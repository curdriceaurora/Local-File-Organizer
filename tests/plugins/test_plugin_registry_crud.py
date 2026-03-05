"""Tests for PluginRegistry: call_all, unload_all, enable/disable, register/unregister."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.plugins.errors import PluginLoadError, PluginNotLoadedError
from file_organizer.plugins.registry import PluginRecord, PluginRegistry
from file_organizer.plugins.security import PluginSecurityPolicy

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_manifest(plugin_dir: Path, **overrides: object) -> Path:
    """Write a minimal valid plugin.json into plugin_dir and return the dir."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": overrides.pop("name", "test-plugin"),
        "version": overrides.pop("version", "1.0.0"),
        "author": "Tester",
        "description": "A test plugin",
        "entry_point": overrides.pop("entry_point", "main.py"),
    }
    manifest.update(overrides)
    (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
    # Create the entry point file
    (plugin_dir / manifest["entry_point"]).write_text("# plugin stub")
    return plugin_dir


def _make_record(name: str = "test-plugin") -> PluginRecord:
    """Create a mock PluginRecord for direct registry testing."""
    return PluginRecord(
        name=name,
        version="1.0.0",
        plugin_dir=Path("fake"),
        policy=PluginSecurityPolicy.unrestricted(),
        manifest={"name": name},
        executor=MagicMock(),
    )


# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------


class TestRegistryBasics:
    """Tests for basic PluginRegistry operations."""

    def test_empty_registry(self) -> None:
        reg = PluginRegistry()
        assert reg.list_plugins() == []

    def test_get_plugin_not_loaded_raises(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(PluginNotLoadedError, match="not loaded"):
            reg.get_plugin("nonexistent")


# ---------------------------------------------------------------------------
# Register / Unregister (via internal _records)
# ---------------------------------------------------------------------------


class TestRegisterUnregister:
    """Test internal registration by inserting/removing records directly."""

    def test_register_and_retrieve(self) -> None:
        reg = PluginRegistry()
        record = _make_record("alpha")
        reg._records["alpha"] = record
        assert reg.get_plugin("alpha") is record
        assert reg.list_plugins() == ["alpha"]

    def test_unregister(self) -> None:
        reg = PluginRegistry()
        record = _make_record("alpha")
        reg._records["alpha"] = record
        del reg._records["alpha"]
        with pytest.raises(PluginNotLoadedError):
            reg.get_plugin("alpha")

    def test_list_plugins_sorted(self) -> None:
        reg = PluginRegistry()
        for name in ["charlie", "alpha", "bravo"]:
            reg._records[name] = _make_record(name)
        assert reg.list_plugins() == ["alpha", "bravo", "charlie"]


# ---------------------------------------------------------------------------
# enable_plugin / disable_plugin
# ---------------------------------------------------------------------------


class TestEnableDisable:
    """Tests for enable_plugin and disable_plugin on the registry."""

    def test_enable_calls_on_enable(self) -> None:
        reg = PluginRegistry()
        record = _make_record()
        reg._records[record.name] = record
        reg.enable_plugin(record.name)
        record.executor.call.assert_called_once_with("on_enable")

    def test_disable_calls_on_disable(self) -> None:
        reg = PluginRegistry()
        record = _make_record()
        reg._records[record.name] = record
        reg.disable_plugin(record.name)
        record.executor.call.assert_called_once_with("on_disable")

    def test_enable_not_loaded_raises(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(PluginNotLoadedError):
            reg.enable_plugin("ghost")

    def test_disable_not_loaded_raises(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(PluginNotLoadedError):
            reg.disable_plugin("ghost")


# ---------------------------------------------------------------------------
# call_all
# ---------------------------------------------------------------------------


class TestCallAll:
    """Tests for PluginRegistry.call_all()."""

    def test_call_all_empty_registry(self) -> None:
        reg = PluginRegistry()
        assert reg.call_all("on_enable") == {}

    def test_call_all_collects_results(self) -> None:
        reg = PluginRegistry()
        rec_a = _make_record("a")
        rec_b = _make_record("b")
        rec_a.executor.call.return_value = "result_a"
        rec_b.executor.call.return_value = "result_b"
        reg._records["a"] = rec_a
        reg._records["b"] = rec_b

        results = reg.call_all("process")
        assert results == {"a": "result_a", "b": "result_b"}

    def test_call_all_captures_exceptions(self) -> None:
        reg = PluginRegistry()
        rec_ok = _make_record("ok")
        rec_bad = _make_record("bad")
        rec_ok.executor.call.return_value = "fine"
        rec_bad.executor.call.side_effect = RuntimeError("boom")
        reg._records["ok"] = rec_ok
        reg._records["bad"] = rec_bad

        results = reg.call_all("process")
        assert results["ok"] == "fine"
        assert isinstance(results["bad"], RuntimeError)
        assert str(results["bad"]) == "boom"

    def test_call_all_passes_args_kwargs(self) -> None:
        reg = PluginRegistry()
        rec = _make_record("p")
        rec.executor.call.return_value = None
        reg._records["p"] = rec

        reg.call_all("on_file", "tmp/f.txt", mode="read")
        rec.executor.call.assert_called_once_with("on_file", "tmp/f.txt", mode="read")


# ---------------------------------------------------------------------------
# unload_plugin
# ---------------------------------------------------------------------------


class TestUnloadPlugin:
    """Tests for PluginRegistry.unload_plugin()."""

    def test_unload_not_loaded_raises(self) -> None:
        reg = PluginRegistry()
        with pytest.raises(PluginNotLoadedError, match="not loaded"):
            reg.unload_plugin("ghost")

    def test_unload_calls_on_unload_and_stop(self) -> None:
        reg = PluginRegistry()
        record = _make_record("p")
        reg._records["p"] = record

        reg.unload_plugin("p")
        record.executor.call.assert_called_once_with("on_unload")
        record.executor.stop.assert_called_once()
        assert "p" not in reg._records

    def test_unload_stops_executor_even_on_unload_error(self) -> None:
        """Executor.stop() must be called even if on_unload raises."""
        reg = PluginRegistry()
        record = _make_record("p")
        record.executor.call.side_effect = RuntimeError("unload error")
        reg._records["p"] = record

        with pytest.raises(RuntimeError, match="unload error"):
            reg.unload_plugin("p")
        record.executor.stop.assert_called_once()


# ---------------------------------------------------------------------------
# unload_all
# ---------------------------------------------------------------------------


class TestUnloadAll:
    """Tests for PluginRegistry.unload_all()."""

    def test_unload_all_empty(self) -> None:
        reg = PluginRegistry()
        reg.unload_all()  # Should not raise

    def test_unload_all_clears_registry(self) -> None:
        reg = PluginRegistry()
        for name in ["a", "b", "c"]:
            record = _make_record(name)
            reg._records[name] = record

        reg.unload_all()
        assert reg.list_plugins() == []

    def test_unload_all_continues_on_individual_failure(self) -> None:
        """One plugin failing to unload should not stop others."""
        reg = PluginRegistry()
        rec_ok = _make_record("ok")
        rec_bad = _make_record("bad")
        rec_bad.executor.call.side_effect = RuntimeError("fail")
        reg._records["ok"] = rec_ok
        reg._records["bad"] = rec_bad

        reg.unload_all()
        # Both should be removed despite bad's failure during on_unload
        assert reg.list_plugins() == []


# ---------------------------------------------------------------------------
# load_plugin (integration with tmp_path)
# ---------------------------------------------------------------------------


class TestLoadPlugin:
    """Tests for PluginRegistry.load_plugin() manifest validation."""

    def test_missing_manifest_raises(self, tmp_path: Path) -> None:
        reg = PluginRegistry()
        with pytest.raises(PluginLoadError, match="Manifest file not found"):
            reg.load_plugin(tmp_path)

    def test_duplicate_name_raises(self, tmp_path: Path) -> None:
        """Loading a plugin with a name already in the registry should raise."""
        reg = PluginRegistry()
        reg._records["test-plugin"] = _make_record("test-plugin")
        plugin_dir = _write_manifest(tmp_path / "plugin", name="test-plugin")

        with pytest.raises(PluginLoadError, match="already loaded"):
            reg.load_plugin(plugin_dir)

    def test_missing_entry_point_raises(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "ep-test",
            "version": "1.0.0",
            "author": "Tester",
            "description": "test",
            "entry_point": "nonexistent.py",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        reg = PluginRegistry()
        with pytest.raises(PluginLoadError, match="not found"):
            reg.load_plugin(plugin_dir)

    def test_path_traversal_entry_point_raises(self, tmp_path: Path) -> None:
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "traverse-test",
            "version": "1.0.0",
            "author": "Tester",
            "description": "test",
            "entry_point": "../../../etc/passwd",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        reg = PluginRegistry()
        with pytest.raises(PluginLoadError, match="escapes plugin directory"):
            reg.load_plugin(plugin_dir)


# ---------------------------------------------------------------------------
# _build_sandbox_from_manifest
# ---------------------------------------------------------------------------


class TestBuildSandbox:
    """Tests for PluginRegistry._build_sandbox_from_manifest."""

    def test_default_read_only_policy(self) -> None:
        manifest: dict[str, object] = {"name": "x"}
        policy = PluginRegistry._build_sandbox_from_manifest(manifest)
        assert "read" in policy.allowed_operations
        assert policy.allow_all_operations is False

    def test_custom_operations(self) -> None:
        manifest: dict[str, object] = {
            "name": "x",
            "allowed_operations": ["read", "write"],
        }
        policy = PluginRegistry._build_sandbox_from_manifest(manifest)
        assert "read" in policy.allowed_operations
        assert "write" in policy.allowed_operations

    def test_allow_all_operations(self) -> None:
        manifest: dict[str, object] = {
            "name": "x",
            "allow_all_operations": True,
        }
        policy = PluginRegistry._build_sandbox_from_manifest(manifest)
        assert policy.allow_all_operations is True
