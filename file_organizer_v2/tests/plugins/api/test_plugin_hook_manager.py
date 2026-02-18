"""Unit tests for plugin hook manager."""

from __future__ import annotations

from typing import Any

import pytest

from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager


class _FakeResponse:
    def __init__(self, status_code: int, text: str = "") -> None:
        self.status_code = status_code
        self.text = text

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300


class _FakeHttpClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __enter__(self) -> _FakeHttpClient:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def post(
        self,
        url: str,
        *,
        json: dict[str, Any],
        headers: dict[str, str],
        timeout: float,
    ) -> _FakeResponse:
        self.calls.append(
            (
                url,
                {
                    "json": json,
                    "headers": headers,
                    "timeout": timeout,
                },
            )
        )
        if self._responses:
            return self._responses.pop(0)
        return _FakeResponse(200)


def test_local_hooks_trigger() -> None:
    manager = PluginHookManager()

    def callback(payload: dict[str, Any]) -> dict[str, Any]:
        return {"received": payload["file"]}

    manager.register_local_hook(HookEvent.FILE_SCANNED, callback)
    results = manager.trigger_local_hooks(HookEvent.FILE_SCANNED, {"file": "example.txt"})
    assert len(results) == 1
    assert results[0].succeeded
    assert results[0].value == {"received": "example.txt"}


def test_webhook_register_dedupe_and_trigger() -> None:
    fake_client = _FakeHttpClient([_FakeResponse(202), _FakeResponse(500, "failed")])
    manager = PluginHookManager(http_client_factory=lambda: fake_client)

    registration, created = manager.register_webhook(
        plugin_id="plugin-a",
        event=HookEvent.FILE_ORGANIZED,
        callback_url="http://localhost:9000/hook",
    )
    assert created is True
    assert registration.plugin_id == "plugin-a"

    _, duplicate_created = manager.register_webhook(
        plugin_id="plugin-a",
        event=HookEvent.FILE_ORGANIZED,
        callback_url="http://localhost:9000/hook",
    )
    assert duplicate_created is False

    manager.register_webhook(
        plugin_id="plugin-b",
        event=HookEvent.FILE_ORGANIZED,
        callback_url="http://localhost:9001/hook",
    )

    results = manager.trigger_event(HookEvent.FILE_ORGANIZED, {"file": "sample.txt"})
    assert len(results) == 2
    assert sum(result.delivered for result in results) == 1
    assert sum(not result.delivered for result in results) == 1
    assert len(fake_client.calls) == 2


def test_webhook_url_validation() -> None:
    manager = PluginHookManager()
    with pytest.raises(ValueError):
        manager.register_webhook(
            plugin_id="plugin-a",
            event=HookEvent.FILE_SCANNED,
            callback_url="not-a-url",
        )
