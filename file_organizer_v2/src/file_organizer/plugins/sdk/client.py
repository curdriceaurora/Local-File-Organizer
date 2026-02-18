"""HTTP client used by external plugins."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from file_organizer.plugins.api.hooks import HookEvent


class PluginClientError(RuntimeError):
    """Raised when plugin API requests fail."""


class PluginClientAuthError(PluginClientError):
    """Raised when plugin API authentication fails."""


class PluginClient:
    """Typed client for plugin-facing API endpoints."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        cleaned_url = base_url.rstrip("/")
        if not cleaned_url.startswith(("http://", "https://")):
            raise ValueError("base_url must use http:// or https://")
        cleaned_token = token.strip()
        if not cleaned_token:
            raise ValueError("token must not be empty")
        self._client = httpx.Client(
            base_url=cleaned_url,
            headers={"Authorization": f"Bearer {cleaned_token}"},
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> PluginClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
    ) -> Any:
        try:
            response = self._client.request(method, path, params=params, json=body)
        except httpx.HTTPError as exc:
            raise PluginClientError(f"Failed to call plugin API endpoint: {path}") from exc

        if response.status_code in {401, 403}:
            raise PluginClientAuthError(f"Plugin API authentication failed: {response.status_code}")

        if response.is_error:
            try:
                payload = response.json()
                message = str(payload.get("message", payload))
            except ValueError:
                message = response.text or "Unknown API error"
            raise PluginClientError(
                f"Plugin API request failed ({response.status_code}) for {path}: {message}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise PluginClientError(f"Plugin API returned non-JSON response for {path}") from exc

    def list_files(
        self,
        *,
        path: str,
        recursive: bool = False,
        include_hidden: bool = False,
        max_items: int = 200,
    ) -> list[dict[str, Any]]:
        payload = self._request(
            "GET",
            "/api/v1/plugins/files/list",
            params={
                "path": path,
                "recursive": recursive,
                "include_hidden": include_hidden,
                "max_items": max_items,
            },
        )
        if not isinstance(payload, dict):
            raise PluginClientError("Unexpected response shape from list_files")
        items = payload.get("items")
        if not isinstance(items, list):
            raise PluginClientError("Invalid items payload from list_files")
        return [item for item in items if isinstance(item, dict)]

    def get_metadata(self, *, path: str) -> dict[str, Any]:
        payload = self._request(
            "GET",
            "/api/v1/plugins/files/metadata",
            params={"path": path},
        )
        if not isinstance(payload, dict):
            raise PluginClientError("Unexpected response shape from get_metadata")
        return payload

    def organize_file(
        self,
        *,
        source_path: str,
        destination_path: str,
        overwrite: bool = False,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        payload = self._request(
            "POST",
            "/api/v1/plugins/files/organize",
            body={
                "source_path": source_path,
                "destination_path": destination_path,
                "overwrite": overwrite,
                "dry_run": dry_run,
            },
        )
        if not isinstance(payload, dict):
            raise PluginClientError("Unexpected response shape from organize_file")
        return payload

    def get_config(self, *, key: str, profile: str = "default") -> Any:
        payload = self._request(
            "GET",
            "/api/v1/plugins/config/get",
            params={"key": key, "profile": profile},
        )
        if not isinstance(payload, dict) or "value" not in payload:
            raise PluginClientError("Unexpected response shape from get_config")
        return payload["value"]

    def register_hook(
        self,
        *,
        event: HookEvent | str,
        callback_url: str,
        secret: str | None = None,
    ) -> dict[str, Any]:
        event_name = event.value if isinstance(event, HookEvent) else str(event)
        payload = self._request(
            "POST",
            "/api/v1/plugins/hooks/register",
            body={
                "event": event_name,
                "callback_url": callback_url,
                "secret": secret,
            },
        )
        if not isinstance(payload, dict):
            raise PluginClientError("Unexpected response shape from register_hook")
        return payload

    def unregister_hook(self, *, event: HookEvent | str, callback_url: str) -> bool:
        event_name = event.value if isinstance(event, HookEvent) else str(event)
        payload = self._request(
            "POST",
            "/api/v1/plugins/hooks/unregister",
            body={"event": event_name, "callback_url": callback_url},
        )
        if not isinstance(payload, dict):
            raise PluginClientError("Unexpected response shape from unregister_hook")
        return bool(payload.get("removed"))

    def list_hooks(self, *, event: HookEvent | str | None = None) -> list[dict[str, Any]]:
        event_name: str | None
        if isinstance(event, HookEvent):
            event_name = event.value
        else:
            event_name = event
        params = {"event": event_name} if event_name else None
        payload = self._request("GET", "/api/v1/plugins/hooks", params=params)
        if not isinstance(payload, dict):
            raise PluginClientError("Unexpected response shape from list_hooks")
        items = payload.get("items")
        if not isinstance(items, list):
            raise PluginClientError("Invalid items payload from list_hooks")
        return [item for item in items if isinstance(item, dict)]

    def trigger_event(
        self, *, event: HookEvent | str, payload: Mapping[str, Any]
    ) -> dict[str, Any]:
        event_name = event.value if isinstance(event, HookEvent) else str(event)
        response_payload = self._request(
            "POST",
            "/api/v1/plugins/hooks/trigger",
            body={"event": event_name, "payload": dict(payload)},
        )
        if not isinstance(response_payload, dict):
            raise PluginClientError("Unexpected response shape from trigger_event")
        return response_payload
