"""Tests for plugin registry CRUD operations and lifecycle management."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.plugins.base import PluginLoadError
from file_organizer.plugins.errors import PluginNotLoadedError
from file_organizer.plugins.registry import PluginRegistry, PluginRecord
from file_organizer.plugins.security import PluginSecurityPolicy


# ============================================================================
# Plugin Loading Tests (CREATE)
# ============================================================================


class TestPluginLoading:
    """Test plugin loading into the registry."""

    def test_load_plugin_success(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Successfully load a plugin into the registry."""
        registry = PluginRegistry()

        record = registry.load_plugin(plugin_with_source)

        assert isinstance(record, PluginRecord)
        assert record.name == "test-plugin"
        assert record.version == "1.0.0"
        assert record.plugin_dir == plugin_with_source

    def test_load_plugin_creates_record(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Loading plugin creates a registry record."""
        registry = PluginRegistry()

        record = registry.load_plugin(plugin_with_source)

        # Record should be in registry
        retrieved = registry.get_plugin("test-plugin")
        assert retrieved == record

    def test_load_plugin_with_custom_policy(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Load plugin with custom security policy."""
        registry = PluginRegistry()
        policy = PluginSecurityPolicy.unrestricted()

        record = registry.load_plugin(plugin_with_source, policy=policy)

        assert record.policy == policy

    def test_load_plugin_duplicate_name_raises_error(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Raise error when loading plugin with duplicate name."""
        registry = PluginRegistry()

        # Load first plugin
        registry.load_plugin(plugin_with_source)

        # Try to load another with same name should fail
        with pytest.raises(PluginLoadError, match="already loaded"):
            registry.load_plugin(plugin_with_source)

    def test_load_plugin_missing_manifest(
        self, missing_manifest_dir: Path
    ) -> None:
        """Raise error when manifest is missing."""
        registry = PluginRegistry()

        with pytest.raises(PluginLoadError, match="Manifest file not found"):
            registry.load_plugin(missing_manifest_dir)

    def test_load_plugin_invalid_manifest(
        self, tmp_path: Path
    ) -> None:
        """Raise error when manifest is invalid."""
        plugin_dir = tmp_path / "invalid"
        plugin_dir.mkdir()

        invalid_manifest = {
            "name": "test",
            "version": 1.0,  # Wrong type
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(invalid_manifest))

        registry = PluginRegistry()

        with pytest.raises(PluginLoadError, match="version"):
            registry.load_plugin(plugin_dir)

    def test_load_plugin_missing_entry_point(
        self, tmp_path: Path
    ) -> None:
        """Raise error when entry point file doesn't exist."""
        plugin_dir = tmp_path / "no_entry"
        plugin_dir.mkdir()

        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "nonexistent.py",  # File doesn't exist
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

        registry = PluginRegistry()

        with pytest.raises(PluginLoadError, match="not found"):
            registry.load_plugin(plugin_dir)

    def test_load_plugin_path_traversal_protection(
        self, tmp_path: Path
    ) -> None:
        """Reject entry points that escape plugin directory."""
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()

        manifest = {
            "name": "evil-plugin",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "../../../etc/passwd",  # Escape attempt
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))

        registry = PluginRegistry()

        with pytest.raises(PluginLoadError, match="escapes"):
            registry.load_plugin(plugin_dir)


# ============================================================================
# Plugin Retrieval Tests (READ)
# ============================================================================


class TestPluginRetrieval:
    """Test retrieving plugins from the registry."""

    def test_get_plugin_success(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Successfully retrieve a loaded plugin."""
        registry = PluginRegistry()
        registry.load_plugin(plugin_with_source)

        record = registry.get_plugin("test-plugin")

        assert record.name == "test-plugin"
        assert record.version == "1.0.0"

    def test_get_plugin_not_loaded(self) -> None:
        """Raise error when getting non-existent plugin."""
        registry = PluginRegistry()

        with pytest.raises(PluginNotLoadedError, match="not loaded"):
            registry.get_plugin("nonexistent")

    def test_list_plugins_empty(self) -> None:
        """List plugins returns empty for new registry."""
        registry = PluginRegistry()

        plugins = registry.list_plugins()

        assert plugins == []

    def test_list_plugins_single(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """List plugins returns single loaded plugin."""
        registry = PluginRegistry()
        registry.load_plugin(plugin_with_source)

        plugins = registry.list_plugins()

        assert len(plugins) == 1
        assert plugins[0] == "test-plugin"

    def test_list_plugins_multiple(
        self, tmp_path: Path, mock_subprocess
    ) -> None:
        """List plugins returns all loaded plugins."""
        registry = PluginRegistry()

        # Create and load 3 plugins
        for i in range(3):
            plugin_dir = tmp_path / f"plugin_{i}"
            plugin_dir.mkdir()

            manifest = {
                "name": f"plugin-{i}",
                "version": f"1.{i}.0",
                "author": "test",
                "description": f"Test plugin {i}",
                "entry_point": "plugin.py",
            }
            (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
            (plugin_dir / "plugin.py").write_text("# dummy")

            registry.load_plugin(plugin_dir)

        plugins = registry.list_plugins()

        assert len(plugins) == 3
        assert "plugin-0" in plugins
        assert "plugin-1" in plugins
        assert "plugin-2" in plugins


# ============================================================================
# Plugin Unloading Tests (DELETE)
# ============================================================================


class TestPluginUnloading:
    """Test unloading plugins from the registry."""

    def test_unload_plugin_success(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Successfully unload a loaded plugin."""
        registry = PluginRegistry()
        registry.load_plugin(plugin_with_source)

        # Unload should not raise
        registry.unload_plugin("test-plugin")

        # Plugin should no longer be retrievable
        with pytest.raises(PluginNotLoadedError):
            registry.get_plugin("test-plugin")

    def test_unload_plugin_not_loaded(self) -> None:
        """Raise error when unloading non-existent plugin."""
        registry = PluginRegistry()

        with pytest.raises(PluginNotLoadedError, match="not loaded"):
            registry.unload_plugin("nonexistent")

    def test_unload_plugin_calls_on_unload(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Unload calls on_unload callback on executor."""
        registry = PluginRegistry()
        record = registry.load_plugin(plugin_with_source)

        # Mock the executor's call method
        record.executor.call = MagicMock()

        registry.unload_plugin("test-plugin")

        # on_unload should have been called
        record.executor.call.assert_called_with("on_unload")

    def test_unload_plugin_stops_executor(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Unload stops the plugin's executor subprocess."""
        registry = PluginRegistry()
        record = registry.load_plugin(plugin_with_source)

        # Mock the executor's stop method
        record.executor.stop = MagicMock()

        registry.unload_plugin("test-plugin")

        # Executor should have been stopped
        record.executor.stop.assert_called()


# ============================================================================
# Plugin Enabling/Disabling Tests (UPDATE)
# ============================================================================


class TestPluginEnabling:
    """Test enabling plugins through the registry."""

    def test_enable_plugin_success(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Successfully enable a loaded plugin."""
        registry = PluginRegistry()
        record = registry.load_plugin(plugin_with_source)

        # Mock the executor
        record.executor.call = MagicMock()

        registry.enable_plugin("test-plugin")

        # on_enable should have been called
        record.executor.call.assert_called_with("on_enable")

    def test_enable_plugin_not_loaded(self) -> None:
        """Raise error when enabling non-existent plugin."""
        registry = PluginRegistry()

        with pytest.raises(PluginNotLoadedError):
            registry.enable_plugin("nonexistent")

    def test_disable_plugin_success(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Successfully disable a loaded plugin."""
        registry = PluginRegistry()
        record = registry.load_plugin(plugin_with_source)

        # Mock the executor
        record.executor.call = MagicMock()

        registry.disable_plugin("test-plugin")

        # on_disable should have been called
        record.executor.call.assert_called_with("on_disable")

    def test_disable_plugin_not_loaded(self) -> None:
        """Raise error when disabling non-existent plugin."""
        registry = PluginRegistry()

        with pytest.raises(PluginNotLoadedError):
            registry.disable_plugin("nonexistent")


# ============================================================================
# Plugin Discovery and Listing Tests
# ============================================================================


class TestPluginDiscovery:
    """Test plugin discovery in the registry."""

    def test_discover_plugins_in_directory(
        self, multiple_plugin_dirs: dict[str, Path], mock_subprocess
    ) -> None:
        """Discover multiple plugins from a directory."""
        registry = PluginRegistry()

        # Load all discovered plugins
        for plugin_dir in multiple_plugin_dirs.values():
            registry.load_plugin(plugin_dir)

        plugins = registry.list_plugins()

        assert len(plugins) == 3
        assert "plugin-0" in plugins
        assert "plugin-1" in plugins
        assert "plugin-2" in plugins

    def test_plugin_metadata_preserved(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Plugin metadata is preserved after loading."""
        registry = PluginRegistry()
        record = registry.load_plugin(plugin_with_source)

        # Check manifest is preserved
        assert record.manifest["name"] == "test-plugin"
        assert record.manifest["version"] == "1.0.0"
        assert record.manifest["author"] == "test author"


# ============================================================================
# Registry State Tests
# ============================================================================


class TestRegistryState:
    """Test registry state management."""

    def test_registry_isolation(
        self, tmp_path: Path, mock_subprocess
    ) -> None:
        """Multiple registries are independent."""
        registry1 = PluginRegistry()
        registry2 = PluginRegistry()

        # Create a plugin
        plugin_dir = tmp_path / "plugin"
        plugin_dir.mkdir()
        manifest = {
            "name": "test-plugin",
            "version": "1.0.0",
            "author": "test",
            "description": "test",
            "entry_point": "plugin.py",
        }
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
        (plugin_dir / "plugin.py").write_text("# dummy")

        # Load in first registry
        registry1.load_plugin(plugin_dir)

        # Should not be in second registry
        with pytest.raises(PluginNotLoadedError):
            registry2.get_plugin("test-plugin")

    def test_load_unload_reload(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Can unload and reload a plugin."""
        registry = PluginRegistry()

        # Load
        record1 = registry.load_plugin(plugin_with_source)
        assert registry.list_plugins() == ["test-plugin"]

        # Unload
        registry.unload_plugin("test-plugin")
        assert registry.list_plugins() == []

        # Reload
        record2 = registry.load_plugin(plugin_with_source)
        assert registry.list_plugins() == ["test-plugin"]


# ============================================================================
# Error Handling and Edge Cases
# ============================================================================


class TestRegistryErrorHandling:
    """Test error handling in registry operations."""

    def test_load_plugin_executor_start_fails(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Handle failure when executor fails to start."""
        # Make executor.start() raise an error
        mock_subprocess.side_effect = RuntimeError("Start failed")

        registry = PluginRegistry()

        with pytest.raises(RuntimeError, match="Start failed"):
            registry.load_plugin(plugin_with_source)

    def test_unload_plugin_on_unload_error_still_stops(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Unload still stops executor even if on_unload raises."""
        registry = PluginRegistry()
        record = registry.load_plugin(plugin_with_source)

        # Mock on_unload to raise
        record.executor.call = MagicMock(side_effect=RuntimeError("on_unload failed"))
        record.executor.stop = MagicMock()

        # Unload should raise the error but still call stop
        with pytest.raises(RuntimeError):
            registry.unload_plugin("test-plugin")

        # But stop should still have been called
        record.executor.stop.assert_called()

    def test_enable_plugin_error_propagates(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Errors during enable are propagated."""
        registry = PluginRegistry()
        record = registry.load_plugin(plugin_with_source)

        # Mock on_enable to raise
        record.executor.call = MagicMock(side_effect=RuntimeError("enable failed"))

        with pytest.raises(RuntimeError, match="enable failed"):
            registry.enable_plugin("test-plugin")


# ============================================================================
# Integration Tests
# ============================================================================


class TestRegistryIntegration:
    """Integration tests for registry operations."""

    def test_complete_lifecycle(
        self, plugin_with_source: Path, mock_subprocess
    ) -> None:
        """Test complete plugin lifecycle through registry."""
        registry = PluginRegistry()

        # Load
        record = registry.load_plugin(plugin_with_source)
        assert record.name == "test-plugin"

        # List
        plugins = registry.list_plugins()
        assert len(plugins) == 1

        # Get
        retrieved = registry.get_plugin("test-plugin")
        assert retrieved == record

        # Enable/Disable (with mocks)
        record.executor.call = MagicMock()
        registry.enable_plugin("test-plugin")
        record.executor.call.assert_called_with("on_enable")

        record.executor.call.reset_mock()
        registry.disable_plugin("test-plugin")
        record.executor.call.assert_called_with("on_disable")

        # Unload
        record.executor.call = MagicMock()
        record.executor.stop = MagicMock()
        registry.unload_plugin("test-plugin")

        # List should be empty
        plugins = registry.list_plugins()
        assert len(plugins) == 0

    def test_multiple_plugins_lifecycle(
        self, tmp_path: Path, mock_subprocess
    ) -> None:
        """Test managing multiple plugins through registry."""
        registry = PluginRegistry()

        # Create and load 3 plugins
        plugin_dirs = []
        for i in range(3):
            plugin_dir = tmp_path / f"plugin_{i}"
            plugin_dir.mkdir()

            manifest = {
                "name": f"plugin-{i}",
                "version": f"1.{i}.0",
                "author": "test",
                "description": f"Test plugin {i}",
                "entry_point": "plugin.py",
            }
            (plugin_dir / "plugin.json").write_text(json.dumps(manifest))
            (plugin_dir / "plugin.py").write_text("# dummy")

            record = registry.load_plugin(plugin_dir)
            plugin_dirs.append((plugin_dir, record))

        # Verify all loaded
        assert len(registry.list_plugins()) == 3

        # Unload middle one
        registry.unload_plugin("plugin-1")
        assert len(registry.list_plugins()) == 2

        # Verify correct ones remain
        plugins = registry.list_plugins()
        assert "plugin-0" in plugins
        assert "plugin-2" in plugins
        assert "plugin-1" not in plugins
