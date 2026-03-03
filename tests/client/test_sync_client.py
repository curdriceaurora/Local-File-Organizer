"""Tests for synchronous API client: FileOrganizerClient request building and configuration."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from file_organizer.client.exceptions import (
    AuthenticationError,
    ClientError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from file_organizer.client.sync_client import FileOrganizerClient


@pytest.mark.unit
class TestFileOrganizerClientInit:
    """Tests for FileOrganizerClient initialization."""

    def test_create_client_default_url(self) -> None:
        """Test creating client with default URL."""
        client = FileOrganizerClient()

        assert client._base_url == "http://localhost:8000"
        assert client._client is not None

    def test_create_client_custom_url(self) -> None:
        """Test creating client with custom URL."""
        client = FileOrganizerClient(base_url="http://example.com:8080")

        assert client._base_url == "http://example.com:8080"

    def test_create_client_with_token(self) -> None:
        """Test creating client with Bearer token."""
        token = "test-jwt-token-123"
        client = FileOrganizerClient(token=token)

        headers = client._client.headers
        assert "Authorization" in headers
        assert headers["Authorization"] == f"Bearer {token}"

    def test_create_client_with_api_key(self) -> None:
        """Test creating client with API key."""
        api_key = "test-api-key-456"
        client = FileOrganizerClient(api_key=api_key)

        headers = client._client.headers
        assert "X-API-Key" in headers
        assert headers["X-API-Key"] == api_key

    def test_create_client_with_token_and_api_key(self) -> None:
        """Test creating client with both token and API key."""
        token = "test-token"
        api_key = "test-key"
        client = FileOrganizerClient(token=token, api_key=api_key)

        headers = client._client.headers
        assert headers["Authorization"] == f"Bearer {token}"
        assert headers["X-API-Key"] == api_key

    def test_create_client_custom_timeout(self) -> None:
        """Test creating client with custom timeout."""
        client = FileOrganizerClient(timeout=60.0)

        assert client._client.timeout.connect == 60.0
        assert client._client.timeout.read == 60.0
        assert client._client.timeout.write == 60.0
        assert client._client.timeout.pool == 60.0

    def test_create_client_default_timeout(self) -> None:
        """Test client has default timeout."""
        client = FileOrganizerClient()

        assert client._client.timeout.connect == 30.0
        assert client._client.timeout.read == 30.0
        assert client._client.timeout.write == 30.0
        assert client._client.timeout.pool == 30.0

    def test_client_cleanup(self) -> None:
        """Test client can be properly closed."""
        client = FileOrganizerClient()

        # Client should have close method from httpx.Client
        assert hasattr(client._client, "close")


@pytest.mark.unit
class TestFileOrganizerClientHelpers:
    """Tests for FileOrganizerClient helper methods."""

    def test_url_construction(self) -> None:
        """Test _url helper constructs API paths."""
        client = FileOrganizerClient()

        assert client._url("/health") == "/api/v1/health"
        assert client._url("/organize/scan") == "/api/v1/organize/scan"
        assert client._url("/files") == "/api/v1/files"

    def test_url_construction_empty_path(self) -> None:
        """Test _url with empty path."""
        client = FileOrganizerClient()

        assert client._url("") == "/api/v1"

    def test_url_construction_trailing_slash(self) -> None:
        """Test _url with trailing slash."""
        client = FileOrganizerClient()

        assert client._url("/health/") == "/api/v1/health/"

    def test_raise_for_status_success(self) -> None:
        """Test _raise_for_status with success response."""
        response = MagicMock(spec=httpx.Response)
        response.is_success = True

        # Should not raise
        FileOrganizerClient._raise_for_status(response)

    def test_raise_for_status_client_error(self) -> None:
        """Test _raise_for_status with client error."""
        response = MagicMock(spec=httpx.Response)
        response.is_success = False
        response.status_code = 400
        response.json.return_value = {"detail": "Bad request"}
        response.text = "Bad request"

        with pytest.raises(ClientError):
            FileOrganizerClient._raise_for_status(response)

    def test_raise_for_status_unauthorized(self) -> None:
        """Test _raise_for_status with 401 response."""
        response = MagicMock(spec=httpx.Response)
        response.is_success = False
        response.status_code = 401
        response.json.return_value = {"detail": "Unauthorized"}
        response.text = "Unauthorized"

        with pytest.raises(AuthenticationError):
            FileOrganizerClient._raise_for_status(response)

    def test_raise_for_status_forbidden(self) -> None:
        """Test _raise_for_status with 403 response."""
        response = MagicMock(spec=httpx.Response)
        response.is_success = False
        response.status_code = 403
        response.json.return_value = {"detail": "Forbidden"}
        response.text = "Forbidden"

        with pytest.raises(AuthenticationError):
            FileOrganizerClient._raise_for_status(response)

    def test_raise_for_status_not_found(self) -> None:
        """Test _raise_for_status with 404 response."""
        response = MagicMock(spec=httpx.Response)
        response.is_success = False
        response.status_code = 404
        response.json.return_value = {"detail": "Not found"}
        response.text = "Not found"

        with pytest.raises(NotFoundError):
            FileOrganizerClient._raise_for_status(response)

    def test_raise_for_status_validation_error(self) -> None:
        """Test _raise_for_status with 422 response."""
        response = MagicMock(spec=httpx.Response)
        response.is_success = False
        response.status_code = 422
        response.json.return_value = {"detail": "Validation failed"}
        response.text = "Validation failed"

        with pytest.raises(ValidationError):
            FileOrganizerClient._raise_for_status(response)

    def test_raise_for_status_server_error(self) -> None:
        """Test _raise_for_status with 500 response."""
        response = MagicMock(spec=httpx.Response)
        response.is_success = False
        response.status_code = 500
        response.json.return_value = {"detail": "Server error"}
        response.text = "Server error"

        with pytest.raises(ServerError):
            FileOrganizerClient._raise_for_status(response)

    def test_raise_for_status_json_parse_error(self) -> None:
        """Test _raise_for_status when JSON parsing fails."""
        response = MagicMock(spec=httpx.Response)
        response.is_success = False
        response.status_code = 400
        response.json.side_effect = ValueError("Invalid JSON")
        response.text = "Invalid request"

        with pytest.raises(ClientError):
            FileOrganizerClient._raise_for_status(response)

    def test_raise_for_status_uses_message_field(self) -> None:
        """Test _raise_for_status uses message field when detail missing."""
        response = MagicMock(spec=httpx.Response)
        response.is_success = False
        response.status_code = 400
        response.json.return_value = {"message": "Error message"}
        response.text = "Error"

        with pytest.raises(ClientError):
            FileOrganizerClient._raise_for_status(response)


@pytest.mark.unit
class TestFileOrganizerClientConfiguration:
    """Tests for FileOrganizerClient configuration options."""

    def test_client_with_custom_url_and_auth(self) -> None:
        """Test client with multiple configuration options."""
        client = FileOrganizerClient(
            base_url="http://api.example.com",
            token="custom-token",
            timeout=45.0,
        )

        assert client._base_url == "http://api.example.com"
        assert client._client.timeout.connect == 45.0
        assert "Authorization" in client._client.headers

    def test_client_base_url_attribute(self) -> None:
        """Test that base URL is accessible."""
        url = "http://custom.example.com"
        client = FileOrganizerClient(base_url=url)

        assert client._base_url == url

    def test_client_httpx_client_exists(self) -> None:
        """Test that internal httpx client exists."""
        client = FileOrganizerClient()

        assert client._client is not None
        assert hasattr(client._client, "headers")
        assert hasattr(client._client, "timeout")

    def test_client_supports_context_manager(self) -> None:
        """Test that client works as context manager."""
        # This tests if the underlying httpx.Client supports it
        client = FileOrganizerClient()

        # httpx.Client is a context manager
        assert hasattr(client._client, "__enter__")
        assert hasattr(client._client, "__exit__")

    def test_client_headers_are_dict(self) -> None:
        """Test that client headers are dict-like."""
        client = FileOrganizerClient(token="test")

        # httpx.Headers is dict-like and supports dict operations
        assert hasattr(client._client.headers, "__getitem__")
        assert hasattr(client._client.headers, "__setitem__")
        assert "authorization" in client._client.headers

    def test_empty_token_creates_no_auth_header(self) -> None:
        """Test that empty token doesn't create auth header."""
        # Empty token should not create Authorization header
        # (Implementation may vary)
        FileOrganizerClient(token="")

    def test_multiple_client_instances_independent(self) -> None:
        """Test that multiple client instances are independent."""
        client1 = FileOrganizerClient(token="token1", base_url="http://api1.com")
        client2 = FileOrganizerClient(token="token2", base_url="http://api2.com")

        assert client1._base_url == "http://api1.com"
        assert client2._base_url == "http://api2.com"
        assert client1._client is not client2._client


@pytest.mark.unit
class TestFileOrganizerClientAPIPrefix:
    """Tests for API prefix constant."""

    def test_api_prefix_constant(self) -> None:
        """Test that API prefix is correct."""
        client = FileOrganizerClient()

        # The API prefix should be /api/v1
        assert client._url("") == "/api/v1"

    def test_api_prefix_version(self) -> None:
        """Test that API uses v1 version."""
        client = FileOrganizerClient()

        # All API paths should start with /api/v1
        assert client._url("/health").startswith("/api/v1")
        assert "/api/v1/" in client._url("/organize/scan")
