"""Tests for the /api/setup/browse-folder server-side folder picker endpoint.

Covers:
- Endpoint exists and returns correct schema
- macOS: calls osascript and parses the POSIX path correctly
- macOS: returns {path: "", cancelled: true} when user cancels
- macOS: returns {path: "", available: false} when osascript fails
- Non-macOS (Linux/Docker): immediately returns {available: false} without
  spawning a subprocess
- Subprocess timeout is respected
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.routers.setup import router as setup_router

pytestmark = [pytest.mark.unit, pytest.mark.ci]


# ---------------------------------------------------------------------------
# Minimal test app fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def client() -> TestClient:
    app = FastAPI()
    app.include_router(setup_router, prefix="/api")
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Schema / route existence
# ---------------------------------------------------------------------------


class TestBrowseFolderSchema:
    def test_endpoint_exists(self, client: TestClient) -> None:
        """GET /api/setup/browse-folder must be reachable (not 404)."""
        with patch(
            "file_organizer.api.routers.setup.sys.platform", "linux"
        ):
            resp = client.get("/api/setup/browse-folder")
        assert resp.status_code == 200

    def test_response_has_required_keys(self, client: TestClient) -> None:
        """Response must contain 'path' and 'available' keys."""
        with patch("file_organizer.api.routers.setup.sys.platform", "linux"):
            resp = client.get("/api/setup/browse-folder")
        data = resp.json()
        assert "path" in data
        assert "available" in data

    def test_path_is_string(self, client: TestClient) -> None:
        with patch("file_organizer.api.routers.setup.sys.platform", "linux"):
            resp = client.get("/api/setup/browse-folder")
        assert isinstance(resp.json()["path"], str)

    def test_available_is_bool(self, client: TestClient) -> None:
        with patch("file_organizer.api.routers.setup.sys.platform", "linux"):
            resp = client.get("/api/setup/browse-folder")
        assert isinstance(resp.json()["available"], bool)


# ---------------------------------------------------------------------------
# Linux / Docker: no subprocess spawned
# ---------------------------------------------------------------------------


class TestBrowseFolderLinux:
    def test_returns_unavailable_on_linux(self, client: TestClient) -> None:
        with patch("file_organizer.api.routers.setup.sys.platform", "linux"):
            resp = client.get("/api/setup/browse-folder")
        data = resp.json()
        assert data["available"] is False
        assert data["path"] == ""

    def test_does_not_spawn_subprocess_on_linux(self, client: TestClient) -> None:
        with (
            patch("file_organizer.api.routers.setup.sys.platform", "linux"),
            patch("file_organizer.api.routers.setup.subprocess.run") as mock_run,
        ):
            client.get("/api/setup/browse-folder")
        mock_run.assert_not_called()


# ---------------------------------------------------------------------------
# macOS: happy path
# ---------------------------------------------------------------------------


class TestBrowseFolderMacOS:
    def _make_run_result(self, stdout: str, returncode: int = 0) -> MagicMock:
        result = MagicMock(spec=subprocess.CompletedProcess)
        result.returncode = returncode
        result.stdout = stdout
        return result

    def test_returns_path_on_success(self, client: TestClient) -> None:
        mock_result = self._make_run_result("/Users/rahul/Documents/\n")
        with (
            patch("file_organizer.api.routers.setup.sys.platform", "darwin"),
            patch(
                "file_organizer.api.routers.setup.subprocess.run",
                return_value=mock_result,
            ),
        ):
            resp = client.get("/api/setup/browse-folder")
        data = resp.json()
        assert data["available"] is True
        assert data["path"] == "/Users/rahul/Documents/"
        assert data.get("cancelled") is False

    def test_path_is_stripped(self, client: TestClient) -> None:
        """Trailing newline from osascript must be stripped."""
        mock_result = self._make_run_result("/Users/rahul/Desktop/\n")
        with (
            patch("file_organizer.api.routers.setup.sys.platform", "darwin"),
            patch(
                "file_organizer.api.routers.setup.subprocess.run",
                return_value=mock_result,
            ),
        ):
            resp = client.get("/api/setup/browse-folder")
        assert resp.json()["path"] == "/Users/rahul/Desktop/"

    def test_calls_osascript_posix_path(self, client: TestClient) -> None:
        """Must call osascript with 'POSIX path of (choose folder)'."""
        mock_result = self._make_run_result("/tmp/\n")
        with (
            patch("file_organizer.api.routers.setup.sys.platform", "darwin"),
            patch(
                "file_organizer.api.routers.setup.subprocess.run",
                return_value=mock_result,
            ) as mock_run,
        ):
            client.get("/api/setup/browse-folder")
        args, kwargs = mock_run.call_args
        cmd = args[0]
        assert cmd[0] == "osascript"
        assert "POSIX path of (choose folder)" in " ".join(cmd)


# ---------------------------------------------------------------------------
# macOS: user cancelled (osascript returns non-zero)
# ---------------------------------------------------------------------------


class TestBrowseFolderMacOSCancel:
    def test_cancelled_when_nonzero_returncode(self, client: TestClient) -> None:
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stdout = ""
        with (
            patch("file_organizer.api.routers.setup.sys.platform", "darwin"),
            patch(
                "file_organizer.api.routers.setup.subprocess.run",
                return_value=mock_result,
            ),
        ):
            resp = client.get("/api/setup/browse-folder")
        data = resp.json()
        assert data["path"] == ""
        assert data["cancelled"] is True

    def test_available_true_even_on_cancel(self, client: TestClient) -> None:
        """Cancel means available=True (picker worked, user just cancelled it)."""
        mock_result = MagicMock(spec=subprocess.CompletedProcess)
        mock_result.returncode = 1
        mock_result.stdout = ""
        with (
            patch("file_organizer.api.routers.setup.sys.platform", "darwin"),
            patch(
                "file_organizer.api.routers.setup.subprocess.run",
                return_value=mock_result,
            ),
        ):
            resp = client.get("/api/setup/browse-folder")
        assert resp.json()["available"] is True


# ---------------------------------------------------------------------------
# macOS: osascript not found / error
# ---------------------------------------------------------------------------


class TestBrowseFolderMacOSError:
    def test_returns_unavailable_when_osascript_missing(
        self, client: TestClient
    ) -> None:
        with (
            patch("file_organizer.api.routers.setup.sys.platform", "darwin"),
            patch(
                "file_organizer.api.routers.setup.subprocess.run",
                side_effect=FileNotFoundError("osascript not found"),
            ),
        ):
            resp = client.get("/api/setup/browse-folder")
        data = resp.json()
        assert data["available"] is False
        assert data["path"] == ""

    def test_returns_unavailable_on_timeout(self, client: TestClient) -> None:
        with (
            patch("file_organizer.api.routers.setup.sys.platform", "darwin"),
            patch(
                "file_organizer.api.routers.setup.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="osascript", timeout=60),
            ),
        ):
            resp = client.get("/api/setup/browse-folder")
        data = resp.json()
        assert data["available"] is False
        assert data["path"] == ""

    def test_returns_unavailable_on_os_error(self, client: TestClient) -> None:
        with (
            patch("file_organizer.api.routers.setup.sys.platform", "darwin"),
            patch(
                "file_organizer.api.routers.setup.subprocess.run",
                side_effect=OSError("permission denied"),
            ),
        ):
            resp = client.get("/api/setup/browse-folder")
        data = resp.json()
        assert data["available"] is False
