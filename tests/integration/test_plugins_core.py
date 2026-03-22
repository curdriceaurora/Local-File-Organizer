"""Integration tests for plugins/base.py, plugins/security.py, plugins/hooks.py,
plugins/registry.py, plugins/lifecycle.py, and plugins/config.py."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_MANIFEST = {
    "name": "test-plugin",
    "version": "1.0.0",
    "author": "Test Author",
    "description": "A test plugin",
    "entry_point": "plugin.py",
}


def _make_plugin_dir(tmp_path: Path, manifest: dict | None = None) -> Path:
    """Write plugin.json and plugin.py into a fresh tmp directory."""
    plugin_dir = tmp_path / "test-plugin"
    plugin_dir.mkdir()
    data = manifest if manifest is not None else _MINIMAL_MANIFEST
    (plugin_dir / "plugin.json").write_text(json.dumps(data), encoding="utf-8")
    (plugin_dir / "plugin.py").write_text("# minimal plugin entry point\n", encoding="utf-8")
    return plugin_dir


# ---------------------------------------------------------------------------
# plugins/base.py — load_manifest / validate_manifest / PluginMetadata / Plugin
# ---------------------------------------------------------------------------


class TestLoadManifest:
    def test_returns_dict_with_all_required_fields(self, tmp_path: Path) -> None:
        plugin_dir = _make_plugin_dir(tmp_path)
        from file_organizer.plugins.base import load_manifest

        manifest = load_manifest(plugin_dir)

        assert manifest["name"] == "test-plugin"
        assert manifest["version"] == "1.0.0"
        assert manifest["author"] == "Test Author"
        assert manifest["description"] == "A test plugin"
        assert manifest["entry_point"] == "plugin.py"

    def test_applies_defaults_for_optional_fields(self, tmp_path: Path) -> None:
        plugin_dir = _make_plugin_dir(tmp_path)
        from file_organizer.plugins.base import load_manifest

        manifest = load_manifest(plugin_dir)

        assert manifest["license"] == "MIT"
        assert manifest["dependencies"] == []
        assert manifest["min_organizer_version"] == "2.0.0"

    def test_raises_when_manifest_missing(self, tmp_path: Path) -> None:
        from file_organizer.plugins.base import load_manifest
        from file_organizer.plugins.errors import PluginLoadError

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()

        with pytest.raises(PluginLoadError, match="Manifest file not found"):
            load_manifest(empty_dir)

    def test_raises_on_invalid_json(self, tmp_path: Path) -> None:
        from file_organizer.plugins.base import load_manifest
        from file_organizer.plugins.errors import PluginLoadError

        plugin_dir = tmp_path / "bad-json"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text("{not valid json", encoding="utf-8")

        with pytest.raises(PluginLoadError, match="Invalid JSON"):
            load_manifest(plugin_dir)

    def test_raises_when_manifest_is_not_object(self, tmp_path: Path) -> None:
        from file_organizer.plugins.base import load_manifest
        from file_organizer.plugins.errors import PluginLoadError

        plugin_dir = tmp_path / "array-manifest"
        plugin_dir.mkdir()
        (plugin_dir / "plugin.json").write_text('["not", "an", "object"]', encoding="utf-8")

        with pytest.raises(PluginLoadError, match="Manifest must be a JSON object"):
            load_manifest(plugin_dir)


class TestValidateManifest:
    def test_passes_for_valid_manifest(self) -> None:
        from file_organizer.plugins.base import validate_manifest

        # Should not raise
        validate_manifest(dict(_MINIMAL_MANIFEST), source="<test>")

    def test_raises_on_missing_required_field(self) -> None:
        from file_organizer.plugins.base import validate_manifest
        from file_organizer.plugins.errors import PluginLoadError

        manifest = {k: v for k, v in _MINIMAL_MANIFEST.items() if k != "author"}

        with pytest.raises(PluginLoadError, match="missing required field 'author'"):
            validate_manifest(manifest, source="test.json")

    def test_raises_on_wrong_type_for_required_field(self) -> None:
        from file_organizer.plugins.base import validate_manifest
        from file_organizer.plugins.errors import PluginLoadError

        manifest = dict(_MINIMAL_MANIFEST)
        manifest["version"] = 123  # must be str

        with pytest.raises(PluginLoadError, match="'version' must be str"):
            validate_manifest(manifest, source="test.json")

    def test_raises_when_optional_field_null_but_not_nullable(self) -> None:
        from file_organizer.plugins.base import validate_manifest
        from file_organizer.plugins.errors import PluginLoadError

        manifest = dict(_MINIMAL_MANIFEST)
        manifest["dependencies"] = None  # nullable only when default is None

        with pytest.raises(PluginLoadError, match="must not be null"):
            validate_manifest(manifest, source="test.json")

    def test_allows_null_for_explicitly_nullable_optional_fields(self) -> None:
        from file_organizer.plugins.base import validate_manifest

        manifest = dict(_MINIMAL_MANIFEST)
        manifest["homepage"] = None  # nullable (default is None)

        # Should not raise
        validate_manifest(manifest, source="test.json")


class TestPluginMetadata:
    def test_frozen_dataclass_fields(self) -> None:
        from file_organizer.plugins.base import PluginMetadata

        meta = PluginMetadata(
            name="my-plugin",
            version="2.1.0",
            author="Alice",
            description="Does things",
        )

        assert meta.name == "my-plugin"
        assert meta.version == "2.1.0"
        assert meta.author == "Alice"
        assert meta.description == "Does things"
        assert meta.license == "MIT"
        assert meta.homepage is None

    def test_frozen_prevents_mutation(self) -> None:
        from file_organizer.plugins.base import PluginMetadata

        meta = PluginMetadata(name="x", version="1.0", author="a", description="b")

        with pytest.raises((AttributeError, TypeError)):
            meta.name = "y"  # type: ignore[misc]


class TestPluginBaseClass:
    def test_concrete_plugin_exposes_enabled_property(self) -> None:
        from file_organizer.plugins.base import Plugin, PluginMetadata

        class _DummyPlugin(Plugin):
            def get_metadata(self) -> PluginMetadata:
                return PluginMetadata(name="dummy", version="0.1", author="x", description="y")

            def on_load(self) -> None:
                pass

            def on_enable(self) -> None:
                self.set_enabled(True)

            def on_disable(self) -> None:
                self.set_enabled(False)

            def on_unload(self) -> None:
                pass

        plugin = _DummyPlugin()
        assert plugin.enabled is False

        plugin.on_enable()
        assert plugin.enabled is True

        plugin.on_disable()
        assert plugin.enabled is False

    def test_plugin_stores_config(self) -> None:
        from file_organizer.plugins.base import Plugin, PluginMetadata

        class _DummyPlugin(Plugin):
            def get_metadata(self) -> PluginMetadata:
                return PluginMetadata(name="dummy", version="0.1", author="x", description="y")

            def on_load(self) -> None:
                pass

            def on_enable(self) -> None:
                pass

            def on_disable(self) -> None:
                pass

            def on_unload(self) -> None:
                pass

        plugin = _DummyPlugin(config={"key": "value"})
        assert plugin.config == {"key": "value"}


# ---------------------------------------------------------------------------
# plugins/security.py — PluginSecurityPolicy / PluginSandbox
# ---------------------------------------------------------------------------


class TestPluginSecurityPolicy:
    def test_unrestricted_allows_everything(self) -> None:
        from file_organizer.plugins.security import PluginSecurityPolicy

        policy = PluginSecurityPolicy.unrestricted()

        assert policy.allow_all_paths is True
        assert policy.allow_all_operations is True

    def test_from_permissions_normalizes_paths(self, tmp_path: Path) -> None:
        from file_organizer.plugins.security import PluginSecurityPolicy

        policy = PluginSecurityPolicy.from_permissions(allowed_paths=[str(tmp_path)])

        resolved = tmp_path.resolve()
        assert resolved in policy.allowed_paths

    def test_from_permissions_normalizes_operations_to_lowercase(self) -> None:
        from file_organizer.plugins.security import PluginSecurityPolicy

        policy = PluginSecurityPolicy.from_permissions(allowed_operations=["READ", "Write"])

        assert "read" in policy.allowed_operations
        assert "write" in policy.allowed_operations

    def test_default_policy_restricts_everything(self) -> None:
        from file_organizer.plugins.security import PluginSecurityPolicy

        policy = PluginSecurityPolicy()

        assert policy.allow_all_paths is False
        assert policy.allow_all_operations is False
        assert len(policy.allowed_paths) == 0
        assert len(policy.allowed_operations) == 0


class TestPluginSandbox:
    def test_unrestricted_policy_allows_any_path(self, tmp_path: Path) -> None:
        from file_organizer.plugins.security import PluginSandbox

        sandbox = PluginSandbox(plugin_name="test", policy=None)  # defaults to unrestricted

        assert sandbox.validate_file_access(tmp_path) is True
        assert sandbox.validate_file_access("/etc/passwd") is True

    def test_restricted_policy_denies_path_outside_allowed(self, tmp_path: Path) -> None:
        from file_organizer.plugins.security import PluginSandbox, PluginSecurityPolicy

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        policy = PluginSecurityPolicy.from_permissions(allowed_paths=[allowed])
        sandbox = PluginSandbox(plugin_name="test", policy=policy)

        outside = tmp_path / "other"
        assert sandbox.validate_file_access(outside) is False

    def test_restricted_policy_allows_path_inside_allowed(self, tmp_path: Path) -> None:
        from file_organizer.plugins.security import PluginSandbox, PluginSecurityPolicy

        allowed = tmp_path / "allowed"
        allowed.mkdir()
        policy = PluginSecurityPolicy.from_permissions(allowed_paths=[allowed])
        sandbox = PluginSandbox(plugin_name="test", policy=policy)

        inside = allowed / "subdir" / "file.txt"
        assert sandbox.validate_file_access(inside) is True

    def test_require_file_access_raises_on_denied_path(self, tmp_path: Path) -> None:
        from file_organizer.plugins.errors import PluginPermissionError
        from file_organizer.plugins.security import PluginSandbox, PluginSecurityPolicy

        policy = PluginSecurityPolicy.from_permissions(allowed_paths=[tmp_path / "allowed"])
        sandbox = PluginSandbox(plugin_name="my-plugin", policy=policy)

        with pytest.raises(PluginPermissionError, match="my-plugin"):
            sandbox.require_file_access("/etc/passwd")

    def test_validate_operation_returns_false_for_denied_op(self) -> None:
        from file_organizer.plugins.security import PluginSandbox, PluginSecurityPolicy

        policy = PluginSecurityPolicy.from_permissions(allowed_operations=["read"])
        sandbox = PluginSandbox(plugin_name="test", policy=policy)

        assert sandbox.validate_operation("write") is False
        assert sandbox.validate_operation("read") is True

    def test_require_operation_raises_for_denied_op(self) -> None:
        from file_organizer.plugins.errors import PluginPermissionError
        from file_organizer.plugins.security import PluginSandbox, PluginSecurityPolicy

        policy = PluginSecurityPolicy.from_permissions(allowed_operations=["read"])
        sandbox = PluginSandbox(plugin_name="restricted-plugin", policy=policy)

        with pytest.raises(PluginPermissionError, match="restricted-plugin"):
            sandbox.require_operation("delete")

    def test_empty_allowed_paths_denies_all(self, tmp_path: Path) -> None:
        from file_organizer.plugins.security import PluginSandbox, PluginSecurityPolicy

        policy = PluginSecurityPolicy(allow_all_paths=False)
        sandbox = PluginSandbox(plugin_name="test", policy=policy)

        assert sandbox.validate_file_access(tmp_path) is False


# ---------------------------------------------------------------------------
# plugins/hooks.py — HookRegistry / HookExecutionResult
# ---------------------------------------------------------------------------


class TestHookExecutionResult:
    def test_succeeded_true_when_no_error(self) -> None:
        from file_organizer.plugins.hooks import HookExecutionResult

        result = HookExecutionResult(callback_name="my_cb", value=42)

        assert result.succeeded is True
        assert result.value == 42
        assert result.error is None

    def test_succeeded_false_when_error_set(self) -> None:
        from file_organizer.plugins.hooks import HookExecutionResult

        err = RuntimeError("boom")
        result = HookExecutionResult(callback_name="my_cb", error=err)

        assert result.succeeded is False
        assert result.error is err


class TestHookRegistry:
    def test_trigger_returns_result_per_callback(self) -> None:
        from file_organizer.plugins.hooks import HookRegistry

        registry = HookRegistry()
        test_path = "test.txt"
        registry.register_hook("on_file", lambda path: f"processed:{path}")

        results = registry.trigger_hook("on_file", test_path)

        assert len(results) == 1
        assert results[0].succeeded is True
        assert results[0].value == f"processed:{test_path}"

    def test_trigger_collects_errors_without_stop(self) -> None:
        from file_organizer.plugins.hooks import HookRegistry

        registry = HookRegistry()

        def bad_callback() -> None:
            raise ValueError("intentional failure")

        registry.register_hook("on_event", bad_callback)

        results = registry.trigger_hook("on_event", stop_on_error=False)

        assert len(results) == 1
        assert results[0].succeeded is False
        assert isinstance(results[0].error, ValueError)

    def test_trigger_raises_on_stop_on_error(self) -> None:
        from file_organizer.plugins.errors import HookExecutionError
        from file_organizer.plugins.hooks import HookRegistry

        registry = HookRegistry()

        def bad_callback() -> None:
            raise RuntimeError("fail fast")

        registry.register_hook("on_event", bad_callback)

        with pytest.raises(HookExecutionError):
            registry.trigger_hook("on_event", stop_on_error=True)

    def test_trigger_returns_empty_list_for_unknown_hook(self) -> None:
        from file_organizer.plugins.hooks import HookRegistry

        registry = HookRegistry()
        results = registry.trigger_hook("nonexistent_hook")

        assert results == []

    def test_unregister_removes_callback(self) -> None:
        from file_organizer.plugins.hooks import HookRegistry

        registry = HookRegistry()
        cb = MagicMock(return_value="done")
        registry.register_hook("on_run", cb)
        registry.unregister_hook("on_run", cb)

        results = registry.trigger_hook("on_run")

        assert results == []
        cb.assert_not_called()

    def test_duplicate_registration_is_idempotent(self) -> None:
        from file_organizer.plugins.hooks import HookRegistry

        registry = HookRegistry()
        cb = MagicMock(return_value=None)
        registry.register_hook("on_run", cb)
        registry.register_hook("on_run", cb)  # duplicate

        registry.trigger_hook("on_run")

        cb.assert_called_once_with()

    def test_list_hooks_returns_callback_counts(self) -> None:
        from file_organizer.plugins.hooks import HookRegistry

        registry = HookRegistry()
        registry.register_hook("on_load", lambda: None)
        registry.register_hook("on_load", lambda: None)
        registry.register_hook("on_unload", lambda: None)

        counts = registry.list_hooks()

        assert counts["on_load"] == 2
        assert counts["on_unload"] == 1

    def test_multiple_callbacks_all_called_in_order(self) -> None:
        from file_organizer.plugins.hooks import HookRegistry

        registry = HookRegistry()
        calls: list[int] = []
        registry.register_hook("on_event", lambda: calls.append(1))
        registry.register_hook("on_event", lambda: calls.append(2))

        registry.trigger_hook("on_event")

        assert calls == [1, 2]


# ---------------------------------------------------------------------------
# plugins/registry.py — PluginRegistry (with mocked PluginExecutor)
# ---------------------------------------------------------------------------


class TestPluginRegistry:
    def test_load_plugin_stores_record(self, tmp_path: Path) -> None:
        from file_organizer.plugins.registry import PluginRegistry
        from file_organizer.plugins.security import PluginSecurityPolicy

        plugin_dir = _make_plugin_dir(tmp_path)
        mock_executor = MagicMock()

        with patch("file_organizer.plugins.registry.PluginExecutor", return_value=mock_executor):
            registry = PluginRegistry()
            record = registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())

        assert record.name == "test-plugin"
        assert record.version == "1.0.0"
        mock_executor.start.assert_called_once_with()
        mock_executor.call.assert_called_once_with("on_load")

    def test_load_plugin_raises_on_duplicate(self, tmp_path: Path) -> None:
        from file_organizer.plugins.base import PluginLoadError
        from file_organizer.plugins.registry import PluginRegistry
        from file_organizer.plugins.security import PluginSecurityPolicy

        plugin_dir = _make_plugin_dir(tmp_path)
        mock_executor = MagicMock()

        with patch("file_organizer.plugins.registry.PluginExecutor", return_value=mock_executor):
            registry = PluginRegistry()
            registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())

            with pytest.raises(PluginLoadError, match="already loaded"):
                registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())

    def test_unload_plugin_calls_on_unload_and_stop(self, tmp_path: Path) -> None:
        from file_organizer.plugins.registry import PluginRegistry
        from file_organizer.plugins.security import PluginSecurityPolicy

        plugin_dir = _make_plugin_dir(tmp_path)
        mock_executor = MagicMock()

        with patch("file_organizer.plugins.registry.PluginExecutor", return_value=mock_executor):
            registry = PluginRegistry()
            registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())
            mock_executor.reset_mock()

            registry.unload_plugin("test-plugin")

        mock_executor.call.assert_called_once_with("on_unload")
        mock_executor.stop.assert_called_once_with()
        assert registry.list_plugins() == []

    def test_unload_plugin_raises_for_unknown_name(self) -> None:
        from file_organizer.plugins.errors import PluginNotLoadedError
        from file_organizer.plugins.registry import PluginRegistry

        registry = PluginRegistry()

        with pytest.raises(PluginNotLoadedError, match="not loaded"):
            registry.unload_plugin("ghost-plugin")

    def test_enable_plugin_calls_on_enable(self, tmp_path: Path) -> None:
        from file_organizer.plugins.registry import PluginRegistry
        from file_organizer.plugins.security import PluginSecurityPolicy

        plugin_dir = _make_plugin_dir(tmp_path)
        mock_executor = MagicMock()

        with patch("file_organizer.plugins.registry.PluginExecutor", return_value=mock_executor):
            registry = PluginRegistry()
            registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())
            mock_executor.reset_mock()

            registry.enable_plugin("test-plugin")

        mock_executor.call.assert_called_once_with("on_enable")

    def test_list_plugins_returns_sorted_names(self, tmp_path: Path) -> None:
        from file_organizer.plugins.registry import PluginRegistry
        from file_organizer.plugins.security import PluginSecurityPolicy

        dir_a = tmp_path / "beta-plugin"
        dir_a.mkdir()
        manifest_a = dict(_MINIMAL_MANIFEST, name="beta-plugin")
        (dir_a / "plugin.json").write_text(json.dumps(manifest_a), encoding="utf-8")
        (dir_a / "plugin.py").write_text("", encoding="utf-8")

        dir_b = tmp_path / "alpha-plugin"
        dir_b.mkdir()
        manifest_b = dict(_MINIMAL_MANIFEST, name="alpha-plugin")
        (dir_b / "plugin.json").write_text(json.dumps(manifest_b), encoding="utf-8")
        (dir_b / "plugin.py").write_text("", encoding="utf-8")

        with patch("file_organizer.plugins.registry.PluginExecutor", return_value=MagicMock()):
            registry = PluginRegistry()
            registry.load_plugin(dir_a, policy=PluginSecurityPolicy.unrestricted())
            registry.load_plugin(dir_b, policy=PluginSecurityPolicy.unrestricted())

        assert registry.list_plugins() == ["alpha-plugin", "beta-plugin"]

    def test_load_plugin_raises_when_entry_point_missing(self, tmp_path: Path) -> None:
        from file_organizer.plugins.base import PluginLoadError
        from file_organizer.plugins.registry import PluginRegistry
        from file_organizer.plugins.security import PluginSecurityPolicy

        plugin_dir = tmp_path / "no-entry"
        plugin_dir.mkdir()
        manifest = dict(_MINIMAL_MANIFEST, entry_point="missing.py")
        (plugin_dir / "plugin.json").write_text(json.dumps(manifest), encoding="utf-8")

        registry = PluginRegistry()

        with pytest.raises(PluginLoadError, match="not found"):
            registry.load_plugin(plugin_dir, policy=PluginSecurityPolicy.unrestricted())


# ---------------------------------------------------------------------------
# plugins/lifecycle.py — PluginLifecycleManager / PluginState
# ---------------------------------------------------------------------------


class TestPluginState:
    def test_state_string_values(self) -> None:
        from file_organizer.plugins.lifecycle import PluginState

        assert PluginState.UNLOADED == "unloaded"
        assert PluginState.LOADED == "loaded"
        assert PluginState.ENABLED == "enabled"
        assert PluginState.DISABLED == "disabled"
        assert PluginState.ERROR == "error"


class TestPluginLifecycleManager:
    def _make_manager_with_loaded_plugin(self, tmp_path: Path):  # type: ignore[no-untyped-def]
        """Return (manager, plugin_dir, mock_executor) with one plugin loaded."""
        from file_organizer.plugins.lifecycle import PluginLifecycleManager
        from file_organizer.plugins.registry import PluginRegistry
        from file_organizer.plugins.security import PluginSecurityPolicy

        plugin_dir = _make_plugin_dir(tmp_path)
        mock_executor = MagicMock()

        with patch("file_organizer.plugins.registry.PluginExecutor", return_value=mock_executor):
            registry = PluginRegistry()
            manager = PluginLifecycleManager(registry)
            manager.load(plugin_dir, policy=PluginSecurityPolicy.unrestricted())

        return manager, plugin_dir, mock_executor

    def test_load_sets_state_to_loaded(self, tmp_path: Path) -> None:
        from file_organizer.plugins.lifecycle import PluginState

        manager, _, _ = self._make_manager_with_loaded_plugin(tmp_path)

        assert manager.get_state("test-plugin") == PluginState.LOADED

    def test_enable_transitions_to_enabled(self, tmp_path: Path) -> None:
        from file_organizer.plugins.lifecycle import PluginState

        manager, _, mock_executor = self._make_manager_with_loaded_plugin(tmp_path)
        mock_executor.reset_mock()

        manager.enable("test-plugin")

        assert manager.get_state("test-plugin") == PluginState.ENABLED
        mock_executor.call.assert_called_once_with("on_enable")

    def test_enable_is_noop_when_already_enabled(self, tmp_path: Path) -> None:
        from file_organizer.plugins.lifecycle import PluginState

        manager, _, mock_executor = self._make_manager_with_loaded_plugin(tmp_path)
        manager.enable("test-plugin")
        mock_executor.reset_mock()

        manager.enable("test-plugin")  # second call — should be no-op

        assert manager.get_state("test-plugin") == PluginState.ENABLED
        mock_executor.call.assert_not_called()

    def test_disable_transitions_to_disabled(self, tmp_path: Path) -> None:
        from file_organizer.plugins.lifecycle import PluginState

        manager, _, mock_executor = self._make_manager_with_loaded_plugin(tmp_path)
        manager.enable("test-plugin")
        mock_executor.reset_mock()

        manager.disable("test-plugin")

        assert manager.get_state("test-plugin") == PluginState.DISABLED
        mock_executor.call.assert_called_once_with("on_disable")

    def test_unload_removes_state_entry(self, tmp_path: Path) -> None:
        from file_organizer.plugins.lifecycle import PluginState

        manager, _, mock_executor = self._make_manager_with_loaded_plugin(tmp_path)
        mock_executor.reset_mock()

        manager.unload("test-plugin")

        assert manager.get_state("test-plugin") == PluginState.UNLOADED
        assert "test-plugin" not in manager.list_states()

    def test_get_state_returns_unloaded_for_unknown_plugin(self, tmp_path: Path) -> None:
        from file_organizer.plugins.lifecycle import PluginLifecycleManager, PluginState
        from file_organizer.plugins.registry import PluginRegistry

        registry = PluginRegistry()
        manager = PluginLifecycleManager(registry)

        assert manager.get_state("no-such-plugin") == PluginState.UNLOADED

    def test_list_states_reflects_all_plugins(self, tmp_path: Path) -> None:
        manager, _, _ = self._make_manager_with_loaded_plugin(tmp_path)

        states = manager.list_states()

        assert "test-plugin" in states
        assert len(states) == 1


# ---------------------------------------------------------------------------
# plugins/config.py — PluginConfig / PluginConfigManager
# ---------------------------------------------------------------------------


class TestPluginConfig:
    def test_to_dict_round_trips_cleanly(self) -> None:
        from file_organizer.plugins.config import PluginConfig

        config = PluginConfig(
            name="my-plugin",
            enabled=True,
            settings={"threshold": 0.9},
            permissions=["read", "write"],
        )
        payload = config.to_dict()

        assert payload["name"] == "my-plugin"
        assert payload["enabled"] is True
        assert payload["settings"] == {"threshold": 0.9}
        assert payload["permissions"] == ["read", "write"]

    def test_from_dict_deserializes_correctly(self) -> None:
        from file_organizer.plugins.config import PluginConfig

        payload = {
            "name": "my-plugin",
            "enabled": True,
            "settings": {"key": "val"},
            "permissions": ["read"],
        }
        config = PluginConfig.from_dict(payload)

        assert config.name == "my-plugin"
        assert config.enabled is True
        assert config.settings == {"key": "val"}
        assert config.permissions == ["read"]

    def test_from_dict_raises_when_name_missing(self) -> None:
        from file_organizer.plugins.config import PluginConfig
        from file_organizer.plugins.errors import PluginConfigError

        with pytest.raises(PluginConfigError, match="missing a valid 'name'"):
            PluginConfig.from_dict({"enabled": True})

    def test_from_dict_raises_on_invalid_name(self) -> None:
        from file_organizer.plugins.config import PluginConfig
        from file_organizer.plugins.errors import PluginConfigError

        with pytest.raises(PluginConfigError, match="Invalid plugin name"):
            PluginConfig.from_dict({"name": "!!invalid!!"})

    def test_from_dict_raises_when_payload_not_dict(self) -> None:
        from file_organizer.plugins.config import PluginConfig
        from file_organizer.plugins.errors import PluginConfigError

        with pytest.raises(PluginConfigError, match="must be a mapping"):
            PluginConfig.from_dict(["not", "a", "dict"])  # type: ignore[arg-type]

    def test_defaults_for_missing_optional_fields(self) -> None:
        from file_organizer.plugins.config import PluginConfig

        config = PluginConfig.from_dict({"name": "minimal-plugin"})

        assert config.enabled is False
        assert config.settings == {}
        assert config.permissions == []


class TestPluginConfigManager:
    def test_save_and_load_round_trips_config(self, tmp_path: Path) -> None:
        from file_organizer.plugins.config import PluginConfig, PluginConfigManager

        manager = PluginConfigManager(tmp_path)
        config = PluginConfig(
            name="my-plugin",
            enabled=True,
            settings={"rate": 0.5},
            permissions=["read"],
        )
        manager.save_config(config)
        loaded = manager.load_config("my-plugin")

        assert loaded.name == "my-plugin"
        assert loaded.enabled is True
        assert loaded.settings == {"rate": 0.5}
        assert loaded.permissions == ["read"]

    def test_load_config_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        from file_organizer.plugins.config import PluginConfigManager

        manager = PluginConfigManager(tmp_path)
        config = manager.load_config("nonexistent-plugin")

        assert config.name == "nonexistent-plugin"
        assert config.enabled is False

    def test_save_config_writes_json_file(self, tmp_path: Path) -> None:
        from file_organizer.plugins.config import PluginConfig, PluginConfigManager

        manager = PluginConfigManager(tmp_path)
        config = PluginConfig(name="test-plugin", enabled=False)
        manager.save_config(config)

        config_path = tmp_path / "test-plugin.json"
        assert config_path.exists()
        payload = json.loads(config_path.read_text(encoding="utf-8"))
        assert payload["name"] == "test-plugin"

    def test_list_configured_plugins_returns_saved_names(self, tmp_path: Path) -> None:
        from file_organizer.plugins.config import PluginConfig, PluginConfigManager

        manager = PluginConfigManager(tmp_path)
        manager.save_config(PluginConfig(name="alpha"))
        manager.save_config(PluginConfig(name="beta"))

        names = manager.list_configured_plugins()

        assert names == ["alpha", "beta"]
        assert len(names) == 2

    def test_list_configured_plugins_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        from file_organizer.plugins.config import PluginConfigManager

        manager = PluginConfigManager(tmp_path / "nonexistent")
        names = manager.list_configured_plugins()

        assert names == []

    def test_config_path_uses_validated_name(self, tmp_path: Path) -> None:
        from file_organizer.plugins.config import PluginConfigManager

        manager = PluginConfigManager(tmp_path)
        path = manager.config_path("my-plugin")

        assert path == tmp_path / "my-plugin.json"

    def test_save_config_creates_dir_if_missing(self, tmp_path: Path) -> None:
        from file_organizer.plugins.config import PluginConfig, PluginConfigManager

        nested = tmp_path / "deep" / "config"
        manager = PluginConfigManager(nested)
        manager.save_config(PluginConfig(name="new-plugin"))

        assert (nested / "new-plugin.json").exists()
