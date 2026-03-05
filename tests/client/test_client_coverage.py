"""Coverage tests for client.sync_client and client.async_client modules."""

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

pytestmark = pytest.mark.unit


def _mock_response(status_code: int = 200, json_data: dict | None = None, text: str = ""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.text = text
    if json_data is not None:
        resp.json.return_value = json_data
    else:
        resp.json.side_effect = ValueError("no json")
    return resp


class TestRaiseForStatus:
    def test_success_returns_none(self):
        resp = _mock_response(200, {"ok": True})
        FileOrganizerClient._raise_for_status(resp)

    def test_401_raises_auth_error(self):
        resp = _mock_response(401, {"detail": "unauthorized"})
        with pytest.raises(AuthenticationError, match="401"):
            FileOrganizerClient._raise_for_status(resp)

    def test_403_raises_auth_error(self):
        resp = _mock_response(403, {"detail": "forbidden"})
        with pytest.raises(AuthenticationError, match="403"):
            FileOrganizerClient._raise_for_status(resp)

    def test_404_raises_not_found(self):
        resp = _mock_response(404, {"detail": "not found"})
        with pytest.raises(NotFoundError, match="404"):
            FileOrganizerClient._raise_for_status(resp)

    def test_422_raises_validation_error(self):
        resp = _mock_response(422, {"detail": "bad input"})
        with pytest.raises(ValidationError, match="422"):
            FileOrganizerClient._raise_for_status(resp)

    def test_500_raises_server_error(self):
        resp = _mock_response(500, {"detail": "internal"})
        with pytest.raises(ServerError, match="500"):
            FileOrganizerClient._raise_for_status(resp)

    def test_400_raises_client_error(self):
        resp = _mock_response(400, {"message": "bad request"})
        with pytest.raises(ClientError, match="400"):
            FileOrganizerClient._raise_for_status(resp)

    def test_error_uses_text_when_no_json(self):
        resp = _mock_response(500, text="plain error")
        resp.json.side_effect = Exception("no json")
        with pytest.raises(ServerError, match="plain error"):
            FileOrganizerClient._raise_for_status(resp)


class TestSyncClientInit:
    def test_default_init(self):
        client = FileOrganizerClient()
        assert client._base_url == "http://localhost:8000"
        client.close()

    def test_with_token(self):
        client = FileOrganizerClient(token="mytoken")
        assert "Authorization" in client._client.headers
        client.close()

    def test_with_api_key(self):
        client = FileOrganizerClient(api_key="key123")
        assert "X-API-Key" in client._client.headers
        client.close()

    def test_set_token(self):
        client = FileOrganizerClient()
        client.set_token("new-token")
        assert client._client.headers["Authorization"] == "Bearer new-token"
        client.close()


class TestSyncClientContextManager:
    def test_context_manager(self):
        with FileOrganizerClient() as client:
            assert client is not None


class TestSyncClientUrl:
    def test_url_prefix(self):
        client = FileOrganizerClient()
        assert client._url("/health") == "/api/v1/health"
        client.close()


class TestSyncClientAuth:
    def test_login(self):
        client = FileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "access_token": "at",
                "refresh_token": "rt",
                "token_type": "bearer",
            },
        )
        client._client.post = MagicMock(return_value=resp)

        result = client.login("user", "pass")
        assert result.access_token == "at"
        client.close()

    def test_register_with_full_name(self):
        client = FileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "id": "1",
                "username": "user",
                "email": "u@e.com",
                "full_name": "User Name",
                "is_active": True,
                "is_admin": False,
                "created_at": "2026-01-01T00:00:00Z",
            },
        )
        client._client.post = MagicMock(return_value=resp)

        result = client.register("user", "u@e.com", "pass", full_name="User Name")
        assert result.username == "user"
        client.close()

    def test_register_without_full_name(self):
        client = FileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "id": "1",
                "username": "user",
                "email": "u@e.com",
                "is_active": True,
                "is_admin": False,
                "created_at": "2026-01-01T00:00:00Z",
            },
        )
        client._client.post = MagicMock(return_value=resp)

        result = client.register("user", "u@e.com", "pass")
        assert result.username == "user"
        client.close()

    def test_refresh_token(self):
        client = FileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "access_token": "new-at",
                "refresh_token": "new-rt",
                "token_type": "bearer",
            },
        )
        client._client.post = MagicMock(return_value=resp)

        result = client.refresh_token("old-rt")
        assert result.access_token == "new-at"
        client.close()

    def test_me(self):
        client = FileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "id": "1",
                "username": "user",
                "email": "u@e.com",
                "is_active": True,
                "is_admin": False,
                "created_at": "2026-01-01T00:00:00Z",
            },
        )
        client._client.get = MagicMock(return_value=resp)

        result = client.me()
        assert result.username == "user"
        client.close()

    def test_logout(self):
        client = FileOrganizerClient()
        resp = _mock_response(200, {})
        client._client.post = MagicMock(return_value=resp)

        client.logout("rt")
        client.close()


class TestSyncClientFiles:
    def test_list_files_with_type(self):
        client = FileOrganizerClient()
        resp = _mock_response(200, {"items": [], "total": 0, "skip": 0, "limit": 100})
        client._client.get = MagicMock(return_value=resp)

        result = client.list_files("/tmp", file_type="pdf")
        assert hasattr(result, "items")
        client.close()

    def test_delete_file(self):
        client = FileOrganizerClient()
        resp = _mock_response(
            200, {"path": "/x", "deleted": True, "permanent": False, "dry_run": False}
        )
        client._client.request = MagicMock(return_value=resp)

        result = client.delete_file("/x", permanent=True)
        assert result.deleted is True
        client.close()


class TestSyncClientOrganize:
    def test_scan(self):
        client = FileOrganizerClient()
        resp = _mock_response(200, {"input_dir": "/input", "total_files": 10, "counts": {"txt": 5}})
        client._client.post = MagicMock(return_value=resp)

        result = client.scan("/input")
        assert result.total_files == 10
        client.close()


class TestSyncClientSystem:
    def test_system_stats_with_max_depth(self):
        client = FileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "total_size": 1000,
                "organized_size": 500,
                "saved_size": 200,
                "file_count": 5,
                "directory_count": 2,
                "size_by_type": {},
                "largest_files": [],
            },
        )
        client._client.get = MagicMock(return_value=resp)

        result = client.system_stats(path=".", max_depth=3)
        assert result.file_count == 5
        client.close()


class TestSyncClientDedupe:
    def test_dedupe_scan_with_max_size(self):
        client = FileOrganizerClient()
        resp = _mock_response(
            200,
            {
                "path": "/path",
                "duplicates": [],
                "stats": {"total_scanned": 10},
            },
        )
        client._client.post = MagicMock(return_value=resp)

        result = client.dedupe_scan("/path", max_file_size=1000)
        assert result.path == "/path"
        client.close()
