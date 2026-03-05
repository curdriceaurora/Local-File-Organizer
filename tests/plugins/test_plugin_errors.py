"""Tests for plugin exception hierarchy, message formatting, and inheritance."""

from __future__ import annotations

import pytest

from file_organizer.plugins.errors import (
    HookExecutionError,
    PluginConfigError,
    PluginDependencyError,
    PluginDiscoveryError,
    PluginError,
    PluginLifecycleError,
    PluginLoadError,
    PluginNotFoundError,
    PluginNotLoadedError,
    PluginPermissionError,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Inheritance hierarchy
# ---------------------------------------------------------------------------


class TestErrorHierarchy:
    """Verify the exception class hierarchy matches the design."""

    def test_plugin_error_is_exception(self) -> None:
        assert issubclass(PluginError, Exception)

    @pytest.mark.parametrize(
        "exc_cls",
        [
            PluginDiscoveryError,
            PluginLoadError,
            PluginNotLoadedError,
            PluginConfigError,
            PluginPermissionError,
            PluginLifecycleError,
            HookExecutionError,
        ],
    )
    def test_direct_subclass_of_plugin_error(self, exc_cls: type) -> None:
        assert issubclass(exc_cls, PluginError)

    def test_plugin_dependency_error_inherits_load_error(self) -> None:
        assert issubclass(PluginDependencyError, PluginLoadError)
        assert issubclass(PluginDependencyError, PluginError)

    def test_plugin_not_found_error_inherits_load_error(self) -> None:
        assert issubclass(PluginNotFoundError, PluginLoadError)
        assert issubclass(PluginNotFoundError, PluginError)


# ---------------------------------------------------------------------------
# Instantiation and message formatting
# ---------------------------------------------------------------------------


class TestErrorMessages:
    """Verify that exceptions store and format messages correctly."""

    def test_plugin_error_message(self) -> None:
        exc = PluginError("general failure")
        assert str(exc) == "general failure"

    def test_plugin_load_error_message(self) -> None:
        exc = PluginLoadError("cannot load plugin 'foo'")
        assert "cannot load plugin 'foo'" in str(exc)

    def test_plugin_discovery_error_message(self) -> None:
        exc = PluginDiscoveryError("discovery failed")
        assert str(exc) == "discovery failed"

    def test_plugin_dependency_error_message(self) -> None:
        exc = PluginDependencyError("missing dep 'bar'")
        assert "missing dep 'bar'" in str(exc)

    def test_plugin_not_found_error_message(self) -> None:
        exc = PluginNotFoundError("plugin 'baz' not found")
        assert "plugin 'baz' not found" in str(exc)

    def test_plugin_not_loaded_error_message(self) -> None:
        exc = PluginNotLoadedError("not loaded")
        assert str(exc) == "not loaded"

    def test_plugin_config_error_message(self) -> None:
        exc = PluginConfigError("bad config key")
        assert str(exc) == "bad config key"

    def test_plugin_permission_error_message(self) -> None:
        exc = PluginPermissionError("access denied to /secret")
        assert "access denied" in str(exc)

    def test_plugin_lifecycle_error_message(self) -> None:
        exc = PluginLifecycleError("enable failed")
        assert str(exc) == "enable failed"

    def test_hook_execution_error_message(self) -> None:
        exc = HookExecutionError("hook 'on_file' raised ValueError")
        assert "hook 'on_file'" in str(exc)


# ---------------------------------------------------------------------------
# Catching behaviour
# ---------------------------------------------------------------------------


class TestErrorCatching:
    """Verify that parent-class except blocks catch child exceptions."""

    def test_catch_dependency_as_load_error(self) -> None:
        with pytest.raises(PluginLoadError):
            raise PluginDependencyError("dep missing")

    def test_catch_not_found_as_load_error(self) -> None:
        with pytest.raises(PluginLoadError):
            raise PluginNotFoundError("not found")

    def test_catch_load_error_as_plugin_error(self) -> None:
        with pytest.raises(PluginError):
            raise PluginLoadError("load fail")

    def test_catch_lifecycle_as_plugin_error(self) -> None:
        with pytest.raises(PluginError):
            raise PluginLifecycleError("lifecycle fail")

    def test_catch_hook_execution_as_plugin_error(self) -> None:
        with pytest.raises(PluginError):
            raise HookExecutionError("hook fail")

    def test_catch_permission_as_plugin_error(self) -> None:
        with pytest.raises(PluginError):
            raise PluginPermissionError("perm fail")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestErrorEdgeCases:
    """Edge cases: empty messages, no-arg construction."""

    def test_empty_message(self) -> None:
        exc = PluginError("")
        assert str(exc) == ""

    def test_no_args(self) -> None:
        exc = PluginError()
        assert str(exc) == ""

    def test_multiple_args(self) -> None:
        exc = PluginError("a", "b", "c")
        assert exc.args == ("a", "b", "c")
