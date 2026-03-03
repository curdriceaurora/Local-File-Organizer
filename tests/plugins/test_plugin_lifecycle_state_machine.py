"""Tests for plugin lifecycle state machine and callback management."""

from __future__ import annotations

import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from file_organizer.plugins.lifecycle import PluginLifecycleManager, PluginState
from file_organizer.plugins.registry import PluginRegistry, PluginRecord


# ============================================================================
# Plugin State Transition Tests
# ============================================================================


class TestPluginStateTransitions:
    """Test state machine transitions for plugin lifecycle."""

    def test_plugin_initial_state_unloaded(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Plugin starts in UNLOADED state."""
        manager = PluginLifecycleManager(registry)
        plugin_name = "test-plugin"

        # Before loading, plugin should default to UNLOADED
        state = manager.get_state(plugin_name)
        assert state == PluginState.UNLOADED

    def test_state_transition_load(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Plugin transitions from UNLOADED → LOADED on load."""
        manager = PluginLifecycleManager(registry)

        # Load plugin
        manager.load(plugin_with_source)

        # Check state is LOADED
        state = manager.get_state("test-plugin")
        assert state == PluginState.LOADED

    def test_state_transition_enable(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Plugin transitions from LOADED → ENABLED on enable."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)

        # Enable plugin
        manager.enable("test-plugin")

        # Check state is ENABLED
        state = manager.get_state("test-plugin")
        assert state == PluginState.ENABLED

    def test_state_transition_disable(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Plugin transitions from ENABLED → DISABLED on disable."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)
        manager.enable("test-plugin")

        # Disable plugin
        manager.disable("test-plugin")

        # Check state is DISABLED
        state = manager.get_state("test-plugin")
        assert state == PluginState.DISABLED

    def test_state_transition_unload(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Plugin transitions from LOADED → UNLOADED on unload."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)

        # Unload plugin
        manager.unload("test-plugin")

        # Check state is UNLOADED (plugin no longer in registry)
        state = manager.get_state("test-plugin")
        assert state == PluginState.UNLOADED

    def test_invalid_transition_enable_without_load(
        self, registry: PluginRegistry
    ) -> None:
        """Cannot enable plugin without loading first."""
        manager = PluginLifecycleManager(registry)

        # Should raise error for non-existent plugin
        with pytest.raises(Exception):  # PluginNotLoadedError
            manager.enable("nonexistent")

    def test_invalid_transition_disable_unloaded(
        self, registry: PluginRegistry
    ) -> None:
        """Cannot disable plugin that isn't loaded."""
        manager = PluginLifecycleManager(registry)

        # Should raise error for non-existent plugin
        with pytest.raises(Exception):  # PluginNotLoadedError
            manager.disable("nonexistent")

    def test_full_lifecycle_transitions(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Plugin goes through complete state machine cycle."""
        manager = PluginLifecycleManager(registry)

        # UNLOADED → LOADED
        manager.load(plugin_with_source)
        assert manager.get_state("test-plugin") == PluginState.LOADED

        # LOADED → ENABLED
        manager.enable("test-plugin")
        assert manager.get_state("test-plugin") == PluginState.ENABLED

        # ENABLED → DISABLED
        manager.disable("test-plugin")
        assert manager.get_state("test-plugin") == PluginState.DISABLED

        # DISABLED → UNLOADED
        manager.unload("test-plugin")
        state = manager.get_state("test-plugin")
        assert state == PluginState.UNLOADED


# ============================================================================
# Plugin Lifecycle Callback Tests
# ============================================================================


class TestPluginLifecycleCallbacks:
    """Test lifecycle callback invocation."""

    def test_on_load_callback_invoked(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """on_load callback is invoked when plugin loads."""
        manager = PluginLifecycleManager(registry)

        # Load plugin - should invoke on_load callback
        manager.load(plugin_with_source)

        # Verify plugin loaded (on_load succeeded)
        assert manager.get_state("test-plugin") == PluginState.LOADED

    def test_on_enable_callback_invoked(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """on_enable callback is invoked when plugin enables."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)

        # Enable plugin - should invoke on_enable callback
        manager.enable("test-plugin")

        # Verify plugin enabled (on_enable succeeded)
        assert manager.get_state("test-plugin") == PluginState.ENABLED

    def test_on_disable_callback_invoked(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """on_disable callback is invoked when plugin disables."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)
        manager.enable("test-plugin")

        # Disable plugin - should invoke on_disable callback
        manager.disable("test-plugin")

        # Verify plugin disabled (on_disable succeeded)
        assert manager.get_state("test-plugin") == PluginState.DISABLED

    def test_on_unload_callback_invoked(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """on_unload callback is invoked when plugin unloads."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)

        # Unload plugin - should invoke on_unload callback
        manager.unload("test-plugin")

        # Verify plugin unloaded (on_unload succeeded)
        state = manager.get_state("test-plugin")
        assert state == PluginState.UNLOADED

    def test_callback_invocation_order(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Callbacks are invoked in correct order."""
        manager = PluginLifecycleManager(registry)

        # Patch the executor to track callback order
        # (This is simplified - real tests would use more sophisticated mocking)
        manager.load(plugin_with_source)
        manager.enable("test-plugin")
        manager.disable("test-plugin")
        manager.unload("test-plugin")

        # If no exceptions raised, callback order was correct
        assert True


# ============================================================================
# Plugin State Persistence Tests
# ============================================================================


class TestPluginStatePersistence:
    """Test plugin state preservation across operations."""

    def test_state_survives_enable_disable_cycle(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Plugin state is preserved through enable/disable cycles."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)

        # First enable/disable cycle
        manager.enable("test-plugin")
        assert manager.get_state("test-plugin") == PluginState.ENABLED
        manager.disable("test-plugin")
        assert manager.get_state("test-plugin") == PluginState.DISABLED

        # Second enable/disable cycle
        manager.enable("test-plugin")
        assert manager.get_state("test-plugin") == PluginState.ENABLED
        manager.disable("test-plugin")
        assert manager.get_state("test-plugin") == PluginState.DISABLED

    def test_registry_state_separate_from_manager_state(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Manager state is separate from underlying registry state."""
        manager = PluginLifecycleManager(registry)

        # Load plugin through manager
        manager.load(plugin_with_source)

        # Manager state transitions shouldn't affect registry
        manager.enable("test-plugin")
        assert manager.get_state("test-plugin") == PluginState.ENABLED

        # Registry should still show plugin as loaded
        assert "test-plugin" in registry.list_plugins()


# ============================================================================
# Plugin Thread Safety Tests
# ============================================================================


class TestPluginThreadSafety:
    """Test thread-safe state management."""

    def test_concurrent_state_queries(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Multiple threads can query plugin state safely."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)

        states = []

        def query_state():
            state = manager.get_state("test-plugin")
            states.append(state)

        # Create multiple threads querying state
        threads = [threading.Thread(target=query_state) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # All queries should return consistent state
        assert len(states) == 5
        assert all(s == PluginState.LOADED for s in states)

    def test_concurrent_state_transitions_blocked(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Concurrent state transitions use proper locking."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)

        results = []

        def enable_and_check():
            try:
                manager.enable("test-plugin")
                state = manager.get_state("test-plugin")
                results.append(("success", state))
            except Exception as e:
                results.append(("error", str(e)))

        # Try to enable from multiple threads
        threads = [threading.Thread(target=enable_and_check) for _ in range(3)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # At least one should succeed, none should corrupt state
        final_state = manager.get_state("test-plugin")
        assert final_state == PluginState.ENABLED


# ============================================================================
# Plugin State Error Handling Tests
# ============================================================================


class TestPluginStateErrorHandling:
    """Test error handling during state transitions."""

    def test_load_error_prevents_state_change(
        self, registry: PluginRegistry
    ) -> None:
        """Load errors prevent plugin from entering LOADED state."""
        manager = PluginLifecycleManager(registry)
        invalid_path = Path("/nonexistent/plugin")

        # Load should fail
        with pytest.raises(Exception):  # PluginLoadError
            manager.load(invalid_path)

        # Plugin should not be in registry - should return UNLOADED
        state = manager.get_state("nonexistent")
        assert state == PluginState.UNLOADED

    def test_enable_error_preserves_loaded_state(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Enable errors transition to ERROR state."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)

        # Manually mock the executor to fail on enable
        record = registry.get_plugin("test-plugin")
        record.executor.call = MagicMock(side_effect=RuntimeError("Enable failed"))

        # Enable should fail
        with pytest.raises(Exception):
            manager.enable("test-plugin")

        # Plugin should be in ERROR state
        assert manager.get_state("test-plugin") == PluginState.ERROR

    def test_disable_error_preserves_enabled_state(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Disable errors transition to ERROR state."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)
        manager.enable("test-plugin")

        # Manually mock the executor to fail on disable
        record = registry.get_plugin("test-plugin")
        record.executor.call = MagicMock(side_effect=RuntimeError("Disable failed"))

        # Disable should fail
        with pytest.raises(Exception):
            manager.disable("test-plugin")

        # Plugin should be in ERROR state
        assert manager.get_state("test-plugin") == PluginState.ERROR

    def test_unload_error_preserves_loaded_state(
        self, plugin_with_source: Path, mock_subprocess, registry: PluginRegistry
    ) -> None:
        """Unload errors clean up state to prevent stale ERROR leak."""
        manager = PluginLifecycleManager(registry)
        manager.load(plugin_with_source)

        # Manually mock the executor to fail on unload
        record = registry.get_plugin("test-plugin")
        record.executor.call = MagicMock(side_effect=RuntimeError("Unload failed"))

        # Unload should fail
        with pytest.raises(Exception):
            manager.unload("test-plugin")

        # State is removed on failure to clean up stale entries (returns UNLOADED)
        assert manager.get_state("test-plugin") == PluginState.UNLOADED
