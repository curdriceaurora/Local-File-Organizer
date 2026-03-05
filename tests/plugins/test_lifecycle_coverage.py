"""Coverage tests for plugins.lifecycle module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.plugins.errors import (
    PluginLifecycleError,
    PluginNotLoadedError,
)
from file_organizer.plugins.lifecycle import PluginLifecycleManager, PluginState
from file_organizer.plugins.registry import PluginRecord, PluginRegistry

pytestmark = pytest.mark.unit


def _make_record(name: str = "demo") -> PluginRecord:
    executor = MagicMock()
    executor.call = MagicMock(return_value=None)
    return PluginRecord(
        name=name,
        version="1.0.0",
        plugin_dir=Path("/fake"),
        policy=MagicMock(),
        manifest={"name": name, "version": "1.0.0"},
        executor=executor,
    )


class TestPluginState:
    def test_enum_values(self):
        assert PluginState.UNLOADED == "unloaded"
        assert PluginState.LOADED == "loaded"
        assert PluginState.ENABLED == "enabled"
        assert PluginState.DISABLED == "disabled"
        assert PluginState.ERROR == "error"


class TestLifecycleLoad:
    def test_load_delegates_to_registry(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        registry.load_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        result = mgr.load(Path("/fake"), policy=None)

        assert result is record
        registry.load_plugin.assert_called_once_with(Path("/fake"), policy=None)
        assert mgr.get_state(record.name) == PluginState.LOADED

    def test_load_with_explicit_policy(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        registry.load_plugin.return_value = record
        policy = MagicMock()

        mgr = PluginLifecycleManager(registry)
        mgr.load(Path("/p"), policy=policy)
        registry.load_plugin.assert_called_once_with(Path("/p"), policy=policy)


class TestLifecycleEnable:
    def test_enable_calls_executor(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        registry.get_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        mgr._states["demo"] = PluginState.LOADED
        mgr.enable("demo")

        record.executor.call.assert_called_once_with("on_enable")
        assert mgr.get_state("demo") == PluginState.ENABLED

    def test_enable_noop_when_already_enabled(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        registry.get_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        mgr._states["demo"] = PluginState.ENABLED
        mgr.enable("demo")

        record.executor.call.assert_not_called()

    def test_enable_sets_error_on_failure(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        record.executor.call.side_effect = RuntimeError("boom")
        registry.get_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        mgr._states["demo"] = PluginState.LOADED

        with pytest.raises(PluginLifecycleError, match="Failed to enable"):
            mgr.enable("demo")

        assert mgr.get_state("demo") == PluginState.ERROR


class TestLifecycleDisable:
    def test_disable_calls_executor(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        registry.get_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        mgr._states["demo"] = PluginState.ENABLED
        mgr.disable("demo")

        record.executor.call.assert_called_once_with("on_disable")
        assert mgr.get_state("demo") == PluginState.DISABLED

    def test_disable_noop_when_not_enabled(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        registry.get_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        mgr._states["demo"] = PluginState.LOADED
        mgr.disable("demo")

        record.executor.call.assert_not_called()

    def test_disable_noop_when_state_missing(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        registry.get_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        mgr.disable("demo")
        record.executor.call.assert_not_called()

    def test_disable_sets_error_on_failure(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        record.executor.call.side_effect = RuntimeError("boom")
        registry.get_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        mgr._states["demo"] = PluginState.ENABLED

        with pytest.raises(PluginLifecycleError, match="Failed to disable"):
            mgr.disable("demo")

        assert mgr.get_state("demo") == PluginState.ERROR


class TestLifecycleUnload:
    def test_unload_disables_first_if_enabled(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        registry.get_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        mgr._states["demo"] = PluginState.ENABLED
        mgr.unload("demo")

        # Should have called on_disable then on_unload
        calls = record.executor.call.call_args_list
        assert calls[0].args == ("on_disable",)
        registry.unload_plugin.assert_called_once_with("demo")
        assert "demo" not in mgr._states

    def test_unload_skips_disable_when_loaded(self):
        registry = MagicMock(spec=PluginRegistry)
        record = _make_record()
        registry.get_plugin.return_value = record

        mgr = PluginLifecycleManager(registry)
        mgr._states["demo"] = PluginState.LOADED
        mgr.unload("demo")

        record.executor.call.assert_not_called()
        registry.unload_plugin.assert_called_once_with("demo")

    def test_unload_clears_state_on_registry_failure(self):
        registry = MagicMock(spec=PluginRegistry)
        registry.unload_plugin.side_effect = RuntimeError("fail")

        mgr = PluginLifecycleManager(registry)
        mgr._states["demo"] = PluginState.LOADED

        with pytest.raises(PluginLifecycleError, match="Failed to unload"):
            mgr.unload("demo")

        assert "demo" not in mgr._states

    def test_unload_from_untracked(self):
        registry = MagicMock(spec=PluginRegistry)

        mgr = PluginLifecycleManager(registry)
        mgr.unload("demo")

        registry.unload_plugin.assert_called_once_with("demo")


class TestLifecycleQueries:
    def test_get_state_returns_unloaded_by_default(self):
        registry = MagicMock(spec=PluginRegistry)
        mgr = PluginLifecycleManager(registry)
        assert mgr.get_state("nonexistent") == PluginState.UNLOADED

    def test_list_states(self):
        registry = MagicMock(spec=PluginRegistry)
        mgr = PluginLifecycleManager(registry)
        mgr._states["a"] = PluginState.LOADED
        mgr._states["b"] = PluginState.ENABLED

        states = mgr.list_states()
        assert states == {"a": PluginState.LOADED, "b": PluginState.ENABLED}
        # Verify returns a copy
        states["c"] = PluginState.ERROR
        assert "c" not in mgr._states

    def test_ensure_loaded_raises_when_not_found(self):
        registry = MagicMock(spec=PluginRegistry)
        registry.get_plugin.side_effect = PluginNotLoadedError("nope")

        mgr = PluginLifecycleManager(registry)

        with pytest.raises(PluginNotLoadedError, match="not loaded"):
            mgr._ensure_loaded("missing")
