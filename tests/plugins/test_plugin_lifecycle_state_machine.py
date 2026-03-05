"""Tests for plugin lifecycle state machine: state transitions, ERROR state, invalid transitions."""

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_registry() -> MagicMock:
    """Create a mock PluginRegistry."""
    return MagicMock(spec=PluginRegistry)


def _mock_record(name: str = "test-plugin") -> MagicMock:
    """Create a mock PluginRecord with a mock executor."""
    record = MagicMock(spec=PluginRecord)
    record.name = name
    record.executor = MagicMock()
    return record


# ---------------------------------------------------------------------------
# PluginState enum
# ---------------------------------------------------------------------------


class TestPluginState:
    """Tests for the PluginState enum values."""

    def test_enum_values(self) -> None:
        assert PluginState.UNLOADED == "unloaded"
        assert PluginState.LOADED == "loaded"
        assert PluginState.ENABLED == "enabled"
        assert PluginState.DISABLED == "disabled"
        assert PluginState.ERROR == "error"

    def test_is_str_enum(self) -> None:
        assert isinstance(PluginState.LOADED, str)


# ---------------------------------------------------------------------------
# Happy path: LOADED -> ENABLED -> DISABLED -> UNLOADED
# ---------------------------------------------------------------------------


class TestHappyPathTransitions:
    """Test the full lifecycle: load -> enable -> disable -> unload."""

    def test_load_sets_loaded_state(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        result = mgr.load(Path("fake/plugin"))
        assert result is record
        assert mgr.get_state(record.name) == PluginState.LOADED

    def test_enable_sets_enabled_state(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        registry.get_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake/plugin"))
        mgr.enable(record.name)
        assert mgr.get_state(record.name) == PluginState.ENABLED
        record.executor.call.assert_called_with("on_enable")

    def test_disable_sets_disabled_state(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        registry.get_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake/plugin"))
        mgr.enable(record.name)
        mgr.disable(record.name)
        assert mgr.get_state(record.name) == PluginState.DISABLED
        record.executor.call.assert_called_with("on_disable")

    def test_unload_removes_state(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        registry.get_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake/plugin"))
        mgr.unload(record.name)
        assert mgr.get_state(record.name) == PluginState.UNLOADED
        registry.unload_plugin.assert_called_once_with(record.name)


# ---------------------------------------------------------------------------
# Enable idempotency
# ---------------------------------------------------------------------------


class TestEnableIdempotency:
    """Test that enabling an already-enabled plugin is a no-op."""

    def test_enable_twice_is_noop(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        registry.get_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake/plugin"))
        mgr.enable(record.name)
        record.executor.call.reset_mock()

        mgr.enable(record.name)  # Should be no-op
        record.executor.call.assert_not_called()


# ---------------------------------------------------------------------------
# Disable guards
# ---------------------------------------------------------------------------


class TestDisableGuards:
    """Test that disabling a non-enabled plugin is a no-op."""

    def test_disable_loaded_plugin_is_noop(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        registry.get_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake/plugin"))
        mgr.disable(record.name)  # Not enabled, should be no-op
        record.executor.call.assert_not_called()


# ---------------------------------------------------------------------------
# ERROR state transitions
# ---------------------------------------------------------------------------


class TestErrorState:
    """Test that lifecycle failures transition to ERROR state."""

    def test_enable_failure_sets_error_state(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        registry.get_plugin.return_value = record
        record.executor.call.side_effect = RuntimeError("enable boom")
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake/plugin"))
        with pytest.raises(PluginLifecycleError, match="Failed to enable"):
            mgr.enable(record.name)
        assert mgr.get_state(record.name) == PluginState.ERROR

    def test_disable_failure_sets_error_state(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        registry.get_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake/plugin"))
        # First enable succeeds
        mgr.enable(record.name)
        # Now make disable fail
        record.executor.call.side_effect = RuntimeError("disable boom")
        with pytest.raises(PluginLifecycleError, match="Failed to disable"):
            mgr.disable(record.name)
        assert mgr.get_state(record.name) == PluginState.ERROR


# ---------------------------------------------------------------------------
# Unload with auto-disable
# ---------------------------------------------------------------------------


class TestUnloadAutoDisable:
    """Test that unload auto-disables an enabled plugin first."""

    def test_unload_enabled_plugin_disables_first(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        registry.get_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake/plugin"))
        mgr.enable(record.name)

        # Track calls to executor
        calls = []
        record.executor.call.side_effect = lambda m: calls.append(m)

        mgr.unload(record.name)
        assert "on_disable" in calls
        registry.unload_plugin.assert_called_once_with(record.name)

    def test_unload_failure_cleans_state(self) -> None:
        registry = _mock_registry()
        record = _mock_record()
        registry.load_plugin.return_value = record
        registry.get_plugin.return_value = record
        registry.unload_plugin.side_effect = RuntimeError("unload boom")
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake/plugin"))
        with pytest.raises(PluginLifecycleError, match="Failed to unload"):
            mgr.unload(record.name)
        # State should be cleaned up (popped)
        assert mgr.get_state(record.name) == PluginState.UNLOADED


# ---------------------------------------------------------------------------
# Not-loaded error
# ---------------------------------------------------------------------------


class TestNotLoaded:
    """Test operations on unloaded plugins."""

    def test_enable_unloaded_raises(self) -> None:
        registry = _mock_registry()
        registry.get_plugin.side_effect = PluginNotLoadedError("not loaded")
        mgr = PluginLifecycleManager(registry)

        with pytest.raises(PluginNotLoadedError, match="not loaded"):
            mgr.enable("nonexistent")

    def test_disable_unloaded_raises(self) -> None:
        registry = _mock_registry()
        registry.get_plugin.side_effect = PluginNotLoadedError("not loaded")
        mgr = PluginLifecycleManager(registry)

        with pytest.raises(PluginNotLoadedError, match="not loaded"):
            mgr.disable("nonexistent")


# ---------------------------------------------------------------------------
# get_state / list_states
# ---------------------------------------------------------------------------


class TestStateQueries:
    """Tests for get_state and list_states."""

    def test_get_state_unknown_returns_unloaded(self) -> None:
        mgr = PluginLifecycleManager(_mock_registry())
        assert mgr.get_state("unknown") == PluginState.UNLOADED

    def test_list_states_empty(self) -> None:
        mgr = PluginLifecycleManager(_mock_registry())
        assert mgr.list_states() == {}

    def test_list_states_after_load(self) -> None:
        registry = _mock_registry()
        record = _mock_record("alpha")
        registry.load_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake"))
        states = mgr.list_states()
        assert states == {"alpha": PluginState.LOADED}

    def test_list_states_returns_copy(self) -> None:
        registry = _mock_registry()
        record = _mock_record("beta")
        registry.load_plugin.return_value = record
        mgr = PluginLifecycleManager(registry)

        mgr.load(Path("fake"))
        states = mgr.list_states()
        states["beta"] = PluginState.ERROR  # Mutate copy
        assert mgr.get_state("beta") == PluginState.LOADED  # Original unchanged
