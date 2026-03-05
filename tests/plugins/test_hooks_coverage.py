"""Coverage tests for plugins.hooks module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from file_organizer.plugins.hooks import HookExecutionResult, HookRegistry

pytestmark = pytest.mark.unit


class TestHookExecutionResult:
    def test_succeeded_true_when_no_error(self):
        result = HookExecutionResult(callback_name="cb", value=42)
        assert result.succeeded is True

    def test_succeeded_false_when_error(self):
        result = HookExecutionResult(callback_name="cb", error=RuntimeError("x"))
        assert result.succeeded is False


class TestHookRegistry:
    def test_register_and_trigger(self):
        reg = HookRegistry()
        cb = MagicMock(return_value="ok")
        reg.register_hook("event.a", cb)

        results = reg.trigger_hook("event.a", 1, 2, key="val")
        assert len(results) == 1
        assert results[0].value == "ok"
        cb.assert_called_once_with(1, 2, key="val")

    def test_register_ignores_duplicates(self):
        reg = HookRegistry()
        cb = MagicMock()
        reg.register_hook("e", cb)
        reg.register_hook("e", cb)
        assert reg.list_hooks() == {"e": 1}

    def test_unregister_removes_callback(self):
        reg = HookRegistry()
        cb = MagicMock()
        reg.register_hook("e", cb)
        reg.unregister_hook("e", cb)
        assert reg.list_hooks() == {}

    def test_unregister_noop_for_missing_hook(self):
        reg = HookRegistry()
        cb = MagicMock()
        reg.unregister_hook("nonexistent", cb)

    def test_unregister_noop_for_missing_callback(self):
        reg = HookRegistry()
        cb1 = MagicMock()
        cb2 = MagicMock()
        reg.register_hook("e", cb1)
        reg.unregister_hook("e", cb2)
        assert reg.list_hooks() == {"e": 1}

    def test_unregister_removes_empty_hook_entry(self):
        reg = HookRegistry()
        cb = MagicMock()
        reg.register_hook("e", cb)
        reg.unregister_hook("e", cb)
        assert "e" not in reg.list_hooks()

    def test_trigger_no_callbacks(self):
        reg = HookRegistry()
        results = reg.trigger_hook("nothing")
        assert results == []

    def test_trigger_multiple_callbacks(self):
        reg = HookRegistry()
        cb1 = MagicMock(return_value=1)
        cb2 = MagicMock(return_value=2)
        reg.register_hook("e", cb1)
        reg.register_hook("e", cb2)

        results = reg.trigger_hook("e")
        assert len(results) == 2
        assert results[0].value == 1
        assert results[1].value == 2

    def test_list_hooks_counts(self):
        reg = HookRegistry()
        reg.register_hook("a", MagicMock())
        reg.register_hook("a", MagicMock())
        reg.register_hook("b", MagicMock())

        counts = reg.list_hooks()
        assert counts["a"] == 2
        assert counts["b"] == 1
