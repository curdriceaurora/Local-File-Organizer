"""Plugin API hook and webhook orchestration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from threading import RLock
from typing import Any
from urllib.parse import urlparse

import httpx

from file_organizer.plugins.hooks import HookExecutionResult, HookRegistry


class HookEvent(StrEnum):
    """Canonical plugin hook events exposed via API + SDK."""

    FILE_SCANNED = "file.scanned"
    FILE_ORGANIZED = "file.organized"
    FILE_DUPLICATED = "file.duplicated"
    FILE_DELETED = "file.deleted"
    ORGANIZATION_STARTED = "organization.started"
    ORGANIZATION_COMPLETED = "organization.completed"
    ORGANIZATION_FAILED = "organization.failed"
    DEDUPLICATION_STARTED = "deduplication.started"
    DEDUPLICATION_COMPLETED = "deduplication.completed"
    DEDUPLICATION_FOUND = "deduplication.found"
    PARA_CATEGORIZED = "para.categorized"
    JOHNNY_DECIMAL_ASSIGNED = "johnny_decimal.assigned"


@dataclass(frozen=True)
class WebhookRegistration:
    """Webhook registration persisted in memory for plugin event delivery."""

    plugin_id: str
    event: HookEvent
    callback_url: str
    secret: str | None
    created_at: datetime


@dataclass(frozen=True)
class WebhookDeliveryResult:
    """Delivery status for one webhook callback."""

    plugin_id: str
    event: HookEvent
    callback_url: str
    status_code: int | None
    delivered: bool
    error: str | None = None


def _default_http_client_factory() -> httpx.Client:
    return httpx.Client(follow_redirects=False)


def _validate_callback_url(callback_url: str) -> str:
    candidate = callback_url.strip()
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Callback URL must use http or https.")
    if not parsed.netloc:
        raise ValueError("Callback URL must include a host.")
    return candidate


class PluginHookManager:
    """Manage local hooks and plugin webhooks for event-driven extensions."""

    def __init__(
        self,
        *,
        http_client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        """Set up the plugin hook manager."""
        self._lock = RLock()
        self._hook_registry = HookRegistry()
        self._webhooks: dict[HookEvent, list[WebhookRegistration]] = {}
        self._http_client_factory = http_client_factory or _default_http_client_factory

    def register_local_hook(self, event: HookEvent, callback: Callable[..., Any]) -> None:
        """Register an in-process callback for an event."""
        self._hook_registry.register_hook(event.value, callback)

    def unregister_local_hook(self, event: HookEvent, callback: Callable[..., Any]) -> None:
        """Unregister an in-process callback for an event."""
        self._hook_registry.unregister_hook(event.value, callback)

    def trigger_local_hooks(
        self,
        event: HookEvent,
        payload: Mapping[str, Any],
        *,
        stop_on_error: bool = False,
    ) -> list[HookExecutionResult]:
        """Trigger in-process callbacks with the given payload."""
        return self._hook_registry.trigger_hook(
            event.value,
            dict(payload),
            stop_on_error=stop_on_error,
        )

    def register_webhook(
        self,
        *,
        plugin_id: str,
        event: HookEvent,
        callback_url: str,
        secret: str | None = None,
    ) -> tuple[WebhookRegistration, bool]:
        """Register an outbound webhook callback.

        Returns ``(registration, created)`` where ``created`` is False for duplicate
        registrations (same plugin + event + callback URL).
        """
        normalized_url = _validate_callback_url(callback_url)
        normalized_secret = secret.strip() if secret else None
        with self._lock:
            registrations = self._webhooks.setdefault(event, [])
            for existing in registrations:
                if existing.plugin_id == plugin_id and existing.callback_url == normalized_url:
                    return existing, False
            registration = WebhookRegistration(
                plugin_id=plugin_id,
                event=event,
                callback_url=normalized_url,
                secret=normalized_secret,
                created_at=datetime.now(UTC),
            )
            registrations.append(registration)
            return registration, True

    def unregister_webhook(self, *, plugin_id: str, event: HookEvent, callback_url: str) -> bool:
        """Remove a webhook registration."""
        normalized_url = _validate_callback_url(callback_url)
        with self._lock:
            registrations = self._webhooks.get(event)
            if not registrations:
                return False
            new_list = [
                existing
                for existing in registrations
                if not (existing.plugin_id == plugin_id and existing.callback_url == normalized_url)
            ]
            if len(new_list) == len(registrations):
                return False
            if new_list:
                self._webhooks[event] = new_list
            else:
                self._webhooks.pop(event, None)
            return True

    def list_webhooks(
        self,
        *,
        plugin_id: str | None = None,
        event: HookEvent | None = None,
    ) -> list[WebhookRegistration]:
        """List webhooks, optionally filtered by plugin or event."""
        with self._lock:
            if event is None:
                candidates = [
                    registration
                    for registrations in self._webhooks.values()
                    for registration in registrations
                ]
            else:
                candidates = list(self._webhooks.get(event, []))
        if plugin_id is not None:
            candidates = [
                registration for registration in candidates if registration.plugin_id == plugin_id
            ]
        return sorted(
            candidates,
            key=lambda registration: (
                registration.event.value,
                registration.created_at,
                registration.callback_url,
            ),
        )

    def trigger_event(
        self,
        event: HookEvent,
        payload: Mapping[str, Any],
        *,
        timeout_seconds: float = 2.0,
    ) -> list[WebhookDeliveryResult]:
        """Deliver one event payload to all registered webhooks."""
        webhooks = self.list_webhooks(event=event)
        if not webhooks:
            return []

        body = {
            "event": event.value,
            "payload": dict(payload),
            "timestamp": datetime.now(UTC).isoformat(),
        }
        results: list[WebhookDeliveryResult] = []

        with self._http_client_factory() as client:
            for webhook in webhooks:
                headers = {
                    "X-File-Organizer-Event": webhook.event.value,
                    "X-Plugin-Id": webhook.plugin_id,
                }
                if webhook.secret:
                    headers["X-Plugin-Secret"] = webhook.secret
                try:
                    response = client.post(
                        webhook.callback_url,
                        json=body,
                        headers=headers,
                        timeout=timeout_seconds,
                    )
                except httpx.HTTPError as exc:
                    results.append(
                        WebhookDeliveryResult(
                            plugin_id=webhook.plugin_id,
                            event=webhook.event,
                            callback_url=webhook.callback_url,
                            status_code=None,
                            delivered=False,
                            error=str(exc),
                        )
                    )
                    continue

                results.append(
                    WebhookDeliveryResult(
                        plugin_id=webhook.plugin_id,
                        event=webhook.event,
                        callback_url=webhook.callback_url,
                        status_code=response.status_code,
                        delivered=response.is_success,
                        error=None if response.is_success else response.text,
                    )
                )

        return results

    def clear(self) -> None:
        """Clear all registered hooks and webhooks (used by tests)."""
        with self._lock:
            self._webhooks.clear()
            self._hook_registry = HookRegistry()
