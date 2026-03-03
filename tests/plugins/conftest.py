"""Shared test fixtures for plugin system tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from file_organizer.plugins.base import PluginMetadata
from file_organizer.plugins.registry import PluginRegistry
from file_organizer.plugins.security import PluginSandbox


# ============================================================================
# Manifest Fixtures
# ============================================================================


@pytest.fixture
def valid_manifest() -> dict[str, Any]:
    """Minimal valid plugin manifest."""
    return {
        "name": "test-plugin",
        "version": "1.0.0",
        "author": "test author",
        "description": "Test plugin",
        "entry_point": "plugin.py",
    }


@pytest.fixture
def minimal_manifest() -> dict[str, Any]:
    """Bare minimum manifest with required fields only."""
    return {
        "name": "minimal-plugin",
        "version": "0.0.1",
        "author": "minimal",
        "description": "Minimal plugin",
        "entry_point": "main.py",
    }


@pytest.fixture
def extended_manifest() -> dict[str, Any]:
    """Manifest with optional fields included."""
    return {
        "name": "extended-plugin",
        "version": "2.0.0",
        "author": "extended author",
        "description": "Extended plugin with optional fields",
        "entry_point": "plugin.py",
        "license": "Apache-2.0",
        "homepage": "https://example.com",
        "dependencies": ["some-dep>=1.0"],
        "min_organizer_version": "2.1.0",
        "max_organizer_version": "3.0.0",
        "allowed_paths": ["/home/user/Documents"],
    }


# ============================================================================
# Plugin Directory Fixtures
# ============================================================================


@pytest.fixture
def plugin_dir(tmp_path: Path, valid_manifest: dict[str, Any]) -> Path:
    """Temporary plugin directory with manifest.json."""
    plugin_root = tmp_path / "test_plugin"
    plugin_root.mkdir(parents=True, exist_ok=True)

    manifest_path = plugin_root / "plugin.json"
    manifest_path.write_text(json.dumps(valid_manifest, indent=2), encoding="utf-8")

    return plugin_root


@pytest.fixture
def plugin_with_source(tmp_path: Path, valid_manifest: dict[str, Any]) -> Path:
    """Plugin directory with both manifest and plugin.py source."""
    plugin_root = tmp_path / "test_plugin_src"
    plugin_root.mkdir(parents=True, exist_ok=True)

    # Write manifest
    manifest_path = plugin_root / "plugin.json"
    manifest_path.write_text(json.dumps(valid_manifest, indent=2), encoding="utf-8")

    # Write dummy plugin.py
    plugin_src = plugin_root / "plugin.py"
    plugin_src.write_text(
        """\
from file_organizer.plugins.base import Plugin, PluginMetadata

class TestPlugin(Plugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="test-plugin",
            version="1.0.0",
            author="test",
            description="Test plugin",
        )

    def on_load(self) -> None:
        pass

    def on_enable(self) -> None:
        pass

    def on_disable(self) -> None:
        pass

    def on_unload(self) -> None:
        pass
""",
        encoding="utf-8",
    )

    return plugin_root


@pytest.fixture
def multiple_plugin_dirs(tmp_path: Path) -> dict[str, Path]:
    """Create multiple test plugin directories."""
    plugins = {}

    for i in range(3):
        plugin_root = tmp_path / f"plugin_{i}"
        plugin_root.mkdir(parents=True, exist_ok=True)

        manifest = {
            "name": f"plugin-{i}",
            "version": f"1.{i}.0",
            "author": f"author-{i}",
            "description": f"Test plugin {i}",
            "entry_point": "plugin.py",
        }

        manifest_path = plugin_root / "plugin.json"
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Create the entry point file
        plugin_src = plugin_root / "plugin.py"
        plugin_src.write_text("# dummy plugin")

        plugins[f"plugin_{i}"] = plugin_root

    return plugins


# ============================================================================
# Plugin Metadata Fixtures
# ============================================================================


@pytest.fixture
def plugin_metadata() -> PluginMetadata:
    """Basic plugin metadata."""
    return PluginMetadata(
        name="test-plugin",
        version="1.0.0",
        author="test author",
        description="Test plugin",
    )


@pytest.fixture
def plugin_metadata_with_deps() -> PluginMetadata:
    """Plugin metadata with dependencies."""
    return PluginMetadata(
        name="dependent-plugin",
        version="1.0.0",
        author="test author",
        description="Plugin with dependencies",
        dependencies=("dep1", "dep2>=1.0"),
        min_organizer_version="2.0.0",
        max_organizer_version="3.0.0",
    )


# ============================================================================
# Sandbox Fixtures
# ============================================================================


@pytest.fixture
def plugin_sandbox() -> PluginSandbox:
    """Plugin sandbox for isolation testing."""
    return PluginSandbox(plugin_name="test-plugin")


@pytest.fixture
def restricted_sandbox() -> PluginSandbox:
    """Sandbox with restricted permissions."""
    sandbox = PluginSandbox(plugin_name="restricted-plugin")
    sandbox.allowed_paths = ["/tmp"]  # Very restrictive
    return sandbox


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_subprocess() -> Any:
    """Mock subprocess.Popen for plugin executor testing."""
    # Patch at the location where PluginExecutor imports it
    with patch("file_organizer.plugins.executor.subprocess.Popen") as mock_popen, \
         patch("file_organizer.plugins.executor.select.select") as mock_select:
        # Configure mock subprocess behavior
        mock_process = MagicMock()
        mock_process.pid = 12345
        mock_process.poll.return_value = None  # Process still running
        mock_process.wait.return_value = 0  # Success exit code
        mock_process.communicate.return_value = (b"", b"")
        mock_process.stdin = MagicMock()
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()

        # Return a valid PluginResult response: {"success": true, "return_value": null, "error": null}\n
        # This is what the executor expects when calling executor.call()
        success_response = b'{"success":true,"return_value":null,"error":null}\n'
        mock_process.stdout.readline.return_value = success_response
        mock_process.stderr.read.return_value = b""

        # Mock select.select to return the stdout as ready (for Unix systems)
        mock_select.return_value = ([mock_process.stdout], [], [])

        mock_popen.return_value = mock_process
        yield mock_popen


@pytest.fixture
def mock_ipc_channel() -> Any:
    """Mock IPC channel for subprocess communication."""
    mock_channel = MagicMock()
    mock_channel.send = MagicMock()
    mock_channel.recv = MagicMock(return_value={"status": "success"})
    return mock_channel


@pytest.fixture
def mock_lifecycle_callbacks() -> dict[str, MagicMock]:
    """Mock lifecycle callback handlers."""
    return {
        "on_load": MagicMock(),
        "on_unload": MagicMock(),
        "on_enable": MagicMock(),
        "on_disable": MagicMock(),
    }


@pytest.fixture
def registry() -> PluginRegistry:
    """Fresh plugin registry for testing."""
    return PluginRegistry()


# ============================================================================
# Error Scenario Fixtures
# ============================================================================


@pytest.fixture
def invalid_manifest_missing_field() -> dict[str, Any]:
    """Manifest missing required field."""
    return {
        "name": "incomplete",
        "version": "1.0.0",
        # Missing "author", "description", "entry_point"
    }


@pytest.fixture
def invalid_manifest_wrong_type() -> dict[str, Any]:
    """Manifest with wrongly-typed field."""
    return {
        "name": "wrong-type",
        "version": 1.0,  # Should be string
        "author": "test",
        "description": "Test",
        "entry_point": "plugin.py",
    }


@pytest.fixture
def invalid_manifest_malformed_json(tmp_path: Path) -> Path:
    """Directory with malformed JSON manifest."""
    plugin_root = tmp_path / "malformed_json"
    plugin_root.mkdir(parents=True, exist_ok=True)

    manifest_path = plugin_root / "plugin.json"
    manifest_path.write_text("{invalid json content}", encoding="utf-8")

    return plugin_root


@pytest.fixture
def missing_manifest_dir(tmp_path: Path) -> Path:
    """Plugin directory without manifest.json."""
    plugin_root = tmp_path / "no_manifest"
    plugin_root.mkdir(parents=True, exist_ok=True)
    return plugin_root


# ============================================================================
# Hook and Event Fixtures
# ============================================================================


@pytest.fixture
def sample_hook_event() -> dict[str, Any]:
    """Sample hook event for testing."""
    return {
        "event_type": "on_file_organized",
        "timestamp": "2024-01-15T10:30:00Z",
        "data": {
            "file_path": "/home/user/file.txt",
            "destination": "/home/user/Documents",
        },
    }


@pytest.fixture
def sample_hook_payload() -> dict[str, Any]:
    """Sample hook event payload."""
    return {
        "file_path": "/home/user/Documents/report.pdf",
        "file_size": 1024,
        "file_type": "pdf",
        "organization_action": "move",
    }


# ============================================================================
# API Request/Response Fixtures
# ============================================================================


@pytest.fixture
def sample_plugin_request() -> dict[str, Any]:
    """Sample plugin API request."""
    return {
        "plugin_id": "test-plugin",
        "action": "execute",
        "payload": {
            "file_path": "/home/user/file.txt",
        },
    }


@pytest.fixture
def sample_plugin_response() -> dict[str, Any]:
    """Sample plugin API response."""
    return {
        "status": "success",
        "plugin_id": "test-plugin",
        "result": {
            "processed": True,
            "destination": "/home/user/Documents",
        },
    }


# ============================================================================
# Validation Fixtures
# ============================================================================


@pytest.fixture
def validator() -> Any:
    """Mock validator for testing."""
    from file_organizer.plugins.base import validate_manifest
    return validate_manifest


@pytest.fixture
def error_tracker() -> dict[str, list[Any]]:
    """Track errors during tests."""
    return {
        "errors": [],
        "warnings": [],
    }
