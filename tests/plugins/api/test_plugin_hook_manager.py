"""Unit tests for plugin hook manager."""

from __future__ import annotations

import socket
from typing import Any

import pytest

from file_organizer.plugins.api.hooks import HookEvent, PluginHookManager, _validate_callback_url

pytestmark = pytest.mark.ci


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
        extensions: dict[str, Any] | None = None,
    ) -> _FakeResponse:
        self.calls.append(
            (
                url,
                {
                    "json": json,
                    "headers": headers,
                    "timeout": timeout,
                    "extensions": extensions,
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
        callback_url="http://8.8.8.8/hook",
    )
    assert created is True
    assert registration.plugin_id == "plugin-a"

    _, duplicate_created = manager.register_webhook(
        plugin_id="plugin-a",
        event=HookEvent.FILE_ORGANIZED,
        callback_url="http://8.8.8.8/hook",
    )
    assert duplicate_created is False

    manager.register_webhook(
        plugin_id="plugin-b",
        event=HookEvent.FILE_ORGANIZED,
        callback_url="http://1.1.1.1/hook",
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

    # Test SSRF block on localhost
    with pytest.raises(ValueError, match=r"not allowed|Loopback"):
        manager.register_webhook(
            plugin_id="plugin-a",
            event=HookEvent.FILE_SCANNED,
            callback_url="http://localhost/hook",
        )

    # Test SSRF block on private range
    with pytest.raises(ValueError, match=r"not allowed|Private"):
        manager.register_webhook(
            plugin_id="plugin-a",
            event=HookEvent.FILE_SCANNED,
            callback_url="http://192.168.1.1/hook",
        )

    # Test SSRF block on metadata IP
    with pytest.raises(ValueError, match=r"not allowed|Metadata"):
        manager.register_webhook(
            plugin_id="plugin-a",
            event=HookEvent.FILE_SCANNED,
            callback_url="http://169.254.169.254/hook",
        )


def test_validate_callback_url_rejects_empty_authority_host() -> None:
    """A netloc with no host portion (e.g. ':8080') must be rejected."""
    with pytest.raises(ValueError, match="valid host"):
        _validate_callback_url("http://:8080/path")


def test_validate_callback_url_allows_unresolvable_host() -> None:
    """A host that fails DNS resolution is allowed at registration time."""
    result = _validate_callback_url("http://this-host-does-not-resolve.example.invalid/hook")
    assert result == "http://this-host-does-not-resolve.example.invalid/hook"


def test_validate_callback_url_skips_malformed_resolved_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-IP string returned by getaddrinfo is skipped rather than raising."""

    def fake_getaddrinfo(host: str, port: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("not-an-ip", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    result = _validate_callback_url("http://example.com/hook")
    assert result == "http://example.com/hook"


def test_validate_callback_url_rejects_loopback_address() -> None:
    """A literal loopback IP must be rejected."""
    with pytest.raises(ValueError, match="Loopback"):
        _validate_callback_url("http://127.0.0.1/hook")


def test_validate_callback_url_rejects_multicast_address() -> None:
    """A literal multicast IP must be rejected."""
    with pytest.raises(ValueError, match="Multicast"):
        _validate_callback_url("http://224.0.0.1/hook")


def test_validate_callback_url_rejects_reserved_address() -> None:
    """A literal reserved (non-private) IPv6 address must be rejected."""
    with pytest.raises(ValueError, match="Reserved"):
        _validate_callback_url("http://[64:ff9b::1]/hook")


def test_validate_callback_url_rejects_link_local_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An address classified as link-local (but not private) must be rejected."""
    import ipaddress

    class _FakeIp:
        is_loopback = False
        is_unspecified = False
        is_private = False
        is_link_local = True
        is_reserved = False
        is_multicast = False

    def fake_getaddrinfo(host: str, port: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("203.0.113.5", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(ipaddress, "ip_address", lambda _addr: _FakeIp())

    with pytest.raises(ValueError, match="Link-local"):
        _validate_callback_url("http://example.com/hook")


def test_validate_callback_url_rejects_metadata_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The well-known cloud metadata IP must be rejected even if no other category matches."""
    import ipaddress

    class _FakeIp:
        is_loopback = False
        is_unspecified = False
        is_private = False
        is_link_local = False
        is_reserved = False
        is_multicast = False

    def fake_getaddrinfo(host: str, port: object) -> list[tuple[object, ...]]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(ipaddress, "ip_address", lambda _addr: _FakeIp())

    with pytest.raises(ValueError, match="Metadata"):
        _validate_callback_url("http://example.com/hook")


def test_trigger_event_blocks_dns_rebinding_at_dispatch_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A webhook valid at registration but rebound to a private IP is blocked at dispatch."""
    fake_client = _FakeHttpClient([])
    manager = PluginHookManager(http_client_factory=lambda: fake_client)

    responses: list[list[tuple[Any, ...]]] = [
        socket.getaddrinfo("8.8.8.8", None),
        socket.getaddrinfo("10.0.0.5", None),
    ]
    response_iter = iter(responses)

    def fake_getaddrinfo(host: str, port: object) -> list[tuple[Any, ...]]:
        return next(response_iter)

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    manager.register_webhook(
        plugin_id="plugin-a",
        event=HookEvent.FILE_DELETED,
        callback_url="http://rebinding.example.com/hook",
    )

    results = manager.trigger_event(HookEvent.FILE_DELETED, {"file": "sample.txt"})
    assert len(results) == 1
    assert results[0].delivered is False
    assert results[0].error is not None
    assert "SSRF Prevention" in results[0].error
    assert len(fake_client.calls) == 0


def test_trigger_event_pins_ip_to_prevent_dns_rebinding_at_send_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Triggering a webhook resolves the domain, validates it, and pins the IP in the request."""
    fake_client = _FakeHttpClient([])
    manager = PluginHookManager(http_client_factory=lambda: fake_client)

    # Mock getaddrinfo to return a safe public IP
    def fake_getaddrinfo(host: str, port: object) -> list[tuple[Any, ...]]:
        if host == "safe.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        raise socket.gaierror("unknown host")

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)

    manager.register_webhook(
        plugin_id="plugin-a",
        event=HookEvent.FILE_DELETED,
        callback_url="https://safe.example.com/hook",
    )

    results = manager.trigger_event(HookEvent.FILE_DELETED, {"file": "sample.txt"})
    assert len(results) == 1
    assert results[0].delivered is True
    assert results[0].error is None

    # Verify that the HTTP call was pinned to the resolved IP address,
    # and the original hostname was sent in Host header and sni_hostname
    assert len(fake_client.calls) == 1
    url, kwargs = fake_client.calls[0]
    assert url == "https://93.184.216.34/hook"
    assert kwargs["headers"]["Host"] == "safe.example.com"
    assert kwargs["extensions"] == {"sni_hostname": "safe.example.com"}
