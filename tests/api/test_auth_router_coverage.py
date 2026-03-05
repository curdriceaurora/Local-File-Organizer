"""Coverage tests for file_organizer.api.routers.auth — uncovered branches."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


class TestRateLimitKey:
    """Covers _rate_limit_key helper."""

    def test_with_client(self) -> None:
        from file_organizer.api.routers.auth import _rate_limit_key

        request = MagicMock()
        request.client.host = "192.168.1.1"
        key = _rate_limit_key(request, "admin")
        assert "192.168.1.1" in key
        assert "admin" in key

    def test_without_client(self) -> None:
        from file_organizer.api.routers.auth import _rate_limit_key

        request = MagicMock()
        request.client = None
        key = _rate_limit_key(request, "user")
        assert "unknown" in key

    def test_empty_username(self) -> None:
        from file_organizer.api.routers.auth import _rate_limit_key

        request = MagicMock()
        request.client.host = "127.0.0.1"
        key = _rate_limit_key(request, "")
        assert "unknown" in key


class TestIsLocalRequest:
    """Covers _is_local_request helper."""

    def test_localhost(self) -> None:
        from file_organizer.api.routers.auth import _is_local_request

        request = MagicMock()
        request.client.host = "127.0.0.1"
        assert _is_local_request(request) is True

    def test_ipv6_localhost(self) -> None:
        from file_organizer.api.routers.auth import _is_local_request

        request = MagicMock()
        request.client.host = "::1"
        assert _is_local_request(request) is True

    def test_named_localhost(self) -> None:
        from file_organizer.api.routers.auth import _is_local_request

        request = MagicMock()
        request.client.host = "localhost"
        assert _is_local_request(request) is True

    def test_remote_host(self) -> None:
        from file_organizer.api.routers.auth import _is_local_request

        request = MagicMock()
        request.client.host = "10.0.0.5"
        assert _is_local_request(request) is False

    def test_no_client(self) -> None:
        from file_organizer.api.routers.auth import _is_local_request

        request = MagicMock()
        request.client = None
        assert _is_local_request(request) is False


class TestAccessTtlSeconds:
    """Covers _access_ttl_seconds helper."""

    def test_with_valid_exp(self) -> None:
        from file_organizer.api.routers.auth import _access_ttl_seconds

        settings = MagicMock()
        settings.auth_access_token_minutes = 15
        future = datetime.now(UTC).timestamp() + 600
        ttl = _access_ttl_seconds(settings, {"exp": future})
        assert ttl > 0

    def test_with_expired(self) -> None:
        from file_organizer.api.routers.auth import _access_ttl_seconds

        settings = MagicMock()
        settings.auth_access_token_minutes = 15
        past = datetime.now(UTC).timestamp() - 600
        ttl = _access_ttl_seconds(settings, {"exp": past})
        assert ttl == 0

    def test_without_exp(self) -> None:
        from file_organizer.api.routers.auth import _access_ttl_seconds

        settings = MagicMock()
        settings.auth_access_token_minutes = 15
        ttl = _access_ttl_seconds(settings, {})
        assert ttl == 15 * 60

    def test_non_numeric_exp(self) -> None:
        from file_organizer.api.routers.auth import _access_ttl_seconds

        settings = MagicMock()
        settings.auth_access_token_minutes = 15
        ttl = _access_ttl_seconds(settings, {"exp": "not-a-number"})
        assert ttl == 15 * 60
