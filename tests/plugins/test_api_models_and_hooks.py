"""Tests for plugin API models, hooks, and webhooks."""

from __future__ import annotations

from datetime import datetime, UTC
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from file_organizer.plugins.api.hooks import (
    HookEvent,
    PluginHookManager,
    WebhookDeliveryResult,
    WebhookRegistration,
)
from file_organizer.plugins.api.models import (
    PluginConfigValueResponse,
    PluginFileListResponse,
    PluginHookListResponse,
    PluginHookRegistrationRequest,
    PluginHookRegistrationResponse,
    PluginHookTriggerRequest,
    PluginHookTriggerResponse,
    PluginHookTriggerResult,
    PluginHookUnregisterRequest,
    PluginHookUnregisterResponse,
    PluginOrganizeFileRequest,
    PluginOrganizeFileResponse,
)
from file_organizer.plugins.hooks import HookExecutionResult, HookRegistry


# ============================================================================
# Hook Event Tests
# ============================================================================


class TestHookEvent:
    """Test hook event enumeration."""

    def test_hook_event_string_enum(self) -> None:
        """HookEvent is a string enum with valid values."""
        assert isinstance(HookEvent.FILE_SCANNED, str)
        assert HookEvent.FILE_SCANNED == "file.scanned"

    def test_hook_event_all_values(self) -> None:
        """All hook events are properly defined."""
        expected_events = {
            "file.scanned",
            "file.organized",
            "file.duplicated",
            "file.deleted",
            "organization.started",
            "organization.completed",
            "organization.failed",
            "deduplication.started",
            "deduplication.completed",
            "deduplication.found",
            "para.categorized",
            "johnny_decimal.assigned",
        }
        actual_events = {event.value for event in HookEvent}
        assert actual_events == expected_events

    def test_hook_event_string_representation(self) -> None:
        """HookEvent values are valid strings."""
        for event in HookEvent:
            assert isinstance(event.value, str)
            assert len(event.value) > 0


# ============================================================================
# API Model Tests - Request/Response Validation
# ============================================================================


class TestOrganizeFileModels:
    """Test file organization request/response models."""

    def test_organize_file_request_valid(self) -> None:
        """Create valid organize file request."""
        request = PluginOrganizeFileRequest(
            source_path="/source/file.txt",
            destination_path="/dest/file.txt",
            overwrite=False,
            dry_run=False,
        )
        assert request.source_path == "/source/file.txt"
        assert request.destination_path == "/dest/file.txt"
        assert request.overwrite is False
        assert request.dry_run is False

    def test_organize_file_request_defaults(self) -> None:
        """Organize file request has correct defaults."""
        request = PluginOrganizeFileRequest(
            source_path="/source/file.txt",
            destination_path="/dest/file.txt",
        )
        assert request.overwrite is False
        assert request.dry_run is False

    def test_organize_file_request_invalid_source_empty(self) -> None:
        """Reject empty source path."""
        with pytest.raises(ValidationError):
            PluginOrganizeFileRequest(
                source_path="",
                destination_path="/dest/file.txt",
            )

    def test_organize_file_request_invalid_source_null_char(self) -> None:
        """Reject path with null character."""
        with pytest.raises(ValidationError):
            PluginOrganizeFileRequest(
                source_path="/source/file\x00.txt",
                destination_path="/dest/file.txt",
            )

    def test_organize_file_response_serialization(self) -> None:
        """Organize file response serializes to JSON."""
        response = PluginOrganizeFileResponse(
            source_path="/source/file.txt",
            destination_path="/dest/file.txt",
            moved=True,
            dry_run=False,
        )
        data = response.model_dump()
        assert data["source_path"] == "/source/file.txt"
        assert data["moved"] is True


class TestHookRegistrationModels:
    """Test webhook registration request/response models."""

    def test_hook_registration_request_valid(self) -> None:
        """Create valid hook registration request."""
        request = PluginHookRegistrationRequest(
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
        )
        assert request.event == HookEvent.FILE_ORGANIZED
        assert request.callback_url == "https://example.com/webhook"
        assert request.secret is None

    def test_hook_registration_request_with_secret(self) -> None:
        """Hook registration with secret."""
        request = PluginHookRegistrationRequest(
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
            secret="my-secret-key",
        )
        assert request.secret == "my-secret-key"

    def test_hook_registration_request_invalid_url_empty(self) -> None:
        """Reject empty callback URL."""
        with pytest.raises(ValidationError):
            PluginHookRegistrationRequest(
                event=HookEvent.FILE_ORGANIZED,
                callback_url="",
            )

    def test_hook_registration_request_invalid_url_whitespace(self) -> None:
        """Reject whitespace-only callback URL."""
        with pytest.raises(ValidationError):
            PluginHookRegistrationRequest(
                event=HookEvent.FILE_ORGANIZED,
                callback_url="   ",
            )

    def test_hook_registration_response_serialization(self) -> None:
        """Hook registration response serializes correctly."""
        now = datetime.now(UTC)
        response = PluginHookRegistrationResponse(
            plugin_id="my-plugin",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
            created_at=now,
            registered=True,
        )
        data = response.model_dump()
        assert data["plugin_id"] == "my-plugin"
        assert data["registered"] is True


class TestHookTriggerModels:
    """Test hook trigger request/response models."""

    def test_hook_trigger_request_with_payload(self) -> None:
        """Create trigger request with payload."""
        request = PluginHookTriggerRequest(
            event=HookEvent.FILE_ORGANIZED,
            payload={"file_path": "/path/to/file.txt", "size": 1024},
        )
        assert request.event == HookEvent.FILE_ORGANIZED
        assert request.payload["file_path"] == "/path/to/file.txt"

    def test_hook_trigger_request_empty_payload(self) -> None:
        """Trigger request with no payload."""
        request = PluginHookTriggerRequest(
            event=HookEvent.FILE_ORGANIZED,
        )
        assert request.payload == {}

    def test_hook_trigger_response_serialization(self) -> None:
        """Hook trigger response with results."""
        result = PluginHookTriggerResult(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
            status_code=200,
            delivered=True,
        )
        response = PluginHookTriggerResponse(
            event=HookEvent.FILE_ORGANIZED,
            delivered=1,
            failed=0,
            results=[result],
        )
        assert response.delivered == 1
        assert response.failed == 0
        assert len(response.results) == 1


class TestConfigValueResponse:
    """Test configuration value response model."""

    def test_config_value_response_string(self) -> None:
        """Config response with string value."""
        response = PluginConfigValueResponse(
            key="setting_name",
            value="setting_value",
        )
        assert response.key == "setting_name"
        assert response.value == "setting_value"

    def test_config_value_response_various_types(self) -> None:
        """Config response accepts various value types."""
        test_cases = [
            ("string", "value"),
            ("number", 42),
            ("float", 3.14),
            ("bool", True),
            ("list", [1, 2, 3]),
            ("dict", {"key": "value"}),
            ("none", None),
        ]
        for key, value in test_cases:
            response = PluginConfigValueResponse(key=key, value=value)
            assert response.value == value


# ============================================================================
# Hook Registry Tests
# ============================================================================


class TestHookRegistry:
    """Test plugin hook registry."""

    def test_hook_registry_register_callback(self) -> None:
        """Register callback for hook."""
        registry = HookRegistry()
        callback = Mock()
        registry.register_hook("test.hook", callback)

        hooks = registry.list_hooks()
        assert "test.hook" in hooks
        assert hooks["test.hook"] == 1

    def test_hook_registry_register_multiple_callbacks(self) -> None:
        """Register multiple callbacks for same hook."""
        registry = HookRegistry()
        callback1 = Mock()
        callback2 = Mock()
        registry.register_hook("test.hook", callback1)
        registry.register_hook("test.hook", callback2)

        hooks = registry.list_hooks()
        assert hooks["test.hook"] == 2

    def test_hook_registry_prevent_duplicates(self) -> None:
        """Duplicate callbacks are not registered."""
        registry = HookRegistry()
        callback = Mock()
        registry.register_hook("test.hook", callback)
        registry.register_hook("test.hook", callback)

        hooks = registry.list_hooks()
        assert hooks["test.hook"] == 1

    def test_hook_registry_unregister_callback(self) -> None:
        """Unregister callback from hook."""
        registry = HookRegistry()
        callback = Mock()
        registry.register_hook("test.hook", callback)
        registry.unregister_hook("test.hook", callback)

        hooks = registry.list_hooks()
        assert "test.hook" not in hooks

    def test_hook_registry_trigger_hook(self) -> None:
        """Trigger hook executes callbacks."""
        registry = HookRegistry()
        callback = Mock(return_value="result")
        registry.register_hook("test.hook", callback)

        results = registry.trigger_hook("test.hook", arg1="value1")

        assert len(results) == 1
        assert results[0].succeeded is True
        assert results[0].value == "result"
        callback.assert_called_once()

    def test_hook_registry_trigger_multiple_callbacks(self) -> None:
        """Trigger hook with multiple callbacks."""
        registry = HookRegistry()
        callback1 = Mock(return_value="result1")
        callback2 = Mock(return_value="result2")
        registry.register_hook("test.hook", callback1)
        registry.register_hook("test.hook", callback2)

        results = registry.trigger_hook("test.hook")

        assert len(results) == 2
        assert all(r.succeeded for r in results)

    def test_hook_registry_trigger_nonexistent_hook(self) -> None:
        """Trigger nonexistent hook returns empty list."""
        registry = HookRegistry()
        results = registry.trigger_hook("nonexistent.hook")
        assert results == []

    def test_hook_execution_result_succeeded_property(self) -> None:
        """HookExecutionResult succeeded property."""
        result_success = HookExecutionResult(callback_name="cb", value="val")
        assert result_success.succeeded is True

        result_error = HookExecutionResult(callback_name="cb", error=RuntimeError())
        assert result_error.succeeded is False


# ============================================================================
# Plugin Hook Manager Tests
# ============================================================================


class TestPluginHookManager:
    """Test plugin hook manager."""

    def test_hook_manager_register_webhook(self) -> None:
        """Register webhook for event."""
        manager = PluginHookManager()
        registration, created = manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
        )

        assert created is True
        assert registration.plugin_id == "plugin-1"
        assert registration.callback_url == "https://example.com/webhook"

    def test_hook_manager_prevent_duplicate_webhooks(self) -> None:
        """Duplicate webhooks are not created."""
        manager = PluginHookManager()
        registration1, created1 = manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
        )
        registration2, created2 = manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
        )

        assert created1 is True
        assert created2 is False
        assert registration1.callback_url == registration2.callback_url

    def test_hook_manager_unregister_webhook(self) -> None:
        """Unregister webhook."""
        manager = PluginHookManager()
        manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
        )

        removed = manager.unregister_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
        )

        assert removed is True
        webhooks = manager.list_webhooks(event=HookEvent.FILE_ORGANIZED)
        assert len(webhooks) == 0

    def test_hook_manager_list_webhooks_by_event(self) -> None:
        """List webhooks filtered by event."""
        manager = PluginHookManager()
        manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook1",
        )
        manager.register_webhook(
            plugin_id="plugin-2",
            event=HookEvent.FILE_DUPLICATED,
            callback_url="https://example.com/webhook2",
        )

        webhooks = manager.list_webhooks(event=HookEvent.FILE_ORGANIZED)
        assert len(webhooks) == 1
        assert webhooks[0].plugin_id == "plugin-1"

    def test_hook_manager_list_webhooks_by_plugin(self) -> None:
        """List webhooks filtered by plugin."""
        manager = PluginHookManager()
        manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook1",
        )
        manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_DUPLICATED,
            callback_url="https://example.com/webhook2",
        )
        manager.register_webhook(
            plugin_id="plugin-2",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook3",
        )

        webhooks = manager.list_webhooks(plugin_id="plugin-1")
        assert len(webhooks) == 2
        assert all(w.plugin_id == "plugin-1" for w in webhooks)

    def test_hook_manager_register_local_hook(self) -> None:
        """Register local hook callback."""
        manager = PluginHookManager()
        callback = Mock(return_value="result")

        manager.register_local_hook(HookEvent.FILE_ORGANIZED, callback)
        results = manager.trigger_local_hooks(
            HookEvent.FILE_ORGANIZED,
            {"file": "test.txt"},
        )

        assert len(results) == 1
        assert results[0].succeeded is True

    def test_hook_manager_unregister_local_hook(self) -> None:
        """Unregister local hook callback."""
        manager = PluginHookManager()
        callback = Mock(return_value="result")

        manager.register_local_hook(HookEvent.FILE_ORGANIZED, callback)
        manager.unregister_local_hook(HookEvent.FILE_ORGANIZED, callback)

        results = manager.trigger_local_hooks(
            HookEvent.FILE_ORGANIZED,
            {"file": "test.txt"},
        )

        assert len(results) == 0

    def test_hook_manager_clear_all_hooks_and_webhooks(self) -> None:
        """Clear all hooks and webhooks."""
        manager = PluginHookManager()
        manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
        )
        manager.register_local_hook(HookEvent.FILE_ORGANIZED, Mock())

        manager.clear()

        webhooks = manager.list_webhooks()
        assert len(webhooks) == 0

    def test_hook_manager_webhook_registration_with_secret(self) -> None:
        """Webhook registration includes secret."""
        manager = PluginHookManager()
        registration, created = manager.register_webhook(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
            secret="my-secret",
        )

        assert registration.secret == "my-secret"


# ============================================================================
# Webhook URL Validation Tests
# ============================================================================


class TestWebhookUrlValidation:
    """Test webhook URL validation."""

    def test_valid_https_url(self) -> None:
        """Accept valid HTTPS URL."""
        request = PluginHookRegistrationRequest(
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
        )
        assert request.callback_url == "https://example.com/webhook"

    def test_valid_http_url(self) -> None:
        """Accept valid HTTP URL."""
        request = PluginHookRegistrationRequest(
            event=HookEvent.FILE_ORGANIZED,
            callback_url="http://example.com/webhook",
        )
        assert request.callback_url == "http://example.com/webhook"

    def test_invalid_url_exceeds_length(self) -> None:
        """Reject URL exceeding maximum length."""
        long_url = "https://example.com/" + "a" * 2048
        with pytest.raises(ValidationError):
            PluginHookRegistrationRequest(
                event=HookEvent.FILE_ORGANIZED,
                callback_url=long_url,
            )

    def test_invalid_url_contains_null(self) -> None:
        """Reject URL with null character."""
        with pytest.raises(ValidationError):
            PluginHookRegistrationRequest(
                event=HookEvent.FILE_ORGANIZED,
                callback_url="https://example.com/webhook\x00",
            )


# ============================================================================
# Serialization Tests
# ============================================================================


class TestModelSerialization:
    """Test Pydantic model serialization/deserialization."""

    def test_organize_file_request_json_roundtrip(self) -> None:
        """Request serializes and deserializes to JSON."""
        original = PluginOrganizeFileRequest(
            source_path="/source/file.txt",
            destination_path="/dest/file.txt",
            overwrite=True,
        )
        data = original.model_dump()
        restored = PluginOrganizeFileRequest(**data)

        assert restored.source_path == original.source_path
        assert restored.overwrite == original.overwrite

    def test_hook_trigger_response_json_roundtrip(self) -> None:
        """Hook trigger response serializes and deserializes correctly."""
        result = PluginHookTriggerResult(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
            status_code=200,
            delivered=True,
        )
        response = PluginHookTriggerResponse(
            event=HookEvent.FILE_ORGANIZED,
            delivered=1,
            failed=0,
            results=[result],
        )
        data = response.model_dump()
        restored = PluginHookTriggerResponse(**data)

        assert restored.delivered == response.delivered
        assert len(restored.results) == 1

    def test_hook_registration_response_json_roundtrip(self) -> None:
        """Hook registration response serialization."""
        now = datetime.now(UTC)
        original = PluginHookRegistrationResponse(
            plugin_id="plugin-1",
            event=HookEvent.FILE_ORGANIZED,
            callback_url="https://example.com/webhook",
            created_at=now,
            registered=True,
        )
        data = original.model_dump()
        restored = PluginHookRegistrationResponse(**data)

        assert restored.plugin_id == original.plugin_id
        assert restored.registered == original.registered


# ============================================================================
# Thread Safety Tests
# ============================================================================


class TestThreadSafety:
    """Test thread-safe operations."""

    def test_hook_registry_thread_safe_trigger(self) -> None:
        """Hook registry safely triggers in multi-threaded context."""
        import threading

        registry = HookRegistry()
        callback = Mock(return_value="result")
        registry.register_hook("test.hook", callback)

        results = []

        def trigger_hook():
            result = registry.trigger_hook("test.hook")
            results.append(result)

        threads = [threading.Thread(target=trigger_hook) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 3

    def test_hook_manager_webhook_thread_safe(self) -> None:
        """Hook manager safely manages webhooks in multi-threaded context."""
        import threading

        manager = PluginHookManager()

        def register_webhooks():
            for i in range(5):
                manager.register_webhook(
                    plugin_id=f"plugin-{i}",
                    event=HookEvent.FILE_ORGANIZED,
                    callback_url=f"https://example.com/webhook{i}",
                )

        threads = [threading.Thread(target=register_webhooks) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        webhooks = manager.list_webhooks(event=HookEvent.FILE_ORGANIZED)
        # All registrations should succeed
        assert len(webhooks) >= 5
