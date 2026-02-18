"""Tests for the synchronous File Organizer API client.

Each test creates a real FastAPI app wired to an in-process ASGI transport
so requests hit the actual API code without needing a running server.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.config import ApiSettings
from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings
from file_organizer.client.exceptions import (
    AuthenticationError,
    NotFoundError,
)
from file_organizer.client.models import (
    FileListResponse,
    HealthResponse,
    TokenResponse,
    UserResponse,
)
from file_organizer.client.sync_client import FileOrganizerClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(
    tmp_path: Path,
    allowed_root: Path | None = None,
    auth_enabled: bool = False,
    bootstrap_admin: bool = False,
) -> tuple[FileOrganizerClient, ApiSettings]:
    """Create a FileOrganizerClient backed by an in-process ASGI transport."""
    allowed_paths = [str(allowed_root)] if allowed_root else [str(tmp_path)]
    overrides: dict[str, object] = {"auth_enabled": auth_enabled}
    if bootstrap_admin:
        overrides["auth_bootstrap_admin"] = True
        overrides["auth_bootstrap_admin_local_only"] = False
    settings = build_test_settings(
        tmp_path,
        allowed_paths=allowed_paths,
        auth_overrides=overrides,
    )
    app = create_app(settings)

    client = FileOrganizerClient.__new__(FileOrganizerClient)
    client._base_url = "http://test"
    client._client = TestClient(app, base_url="http://test")
    return client, settings


def _make_auth_client(
    tmp_path: Path,
    allowed_root: Path | None = None,
) -> tuple[FileOrganizerClient, str]:
    """Create a client with a registered and logged-in user."""
    client, _ = _make_client(
        tmp_path,
        allowed_root=allowed_root,
        auth_enabled=True,
        bootstrap_admin=True,
    )
    username = f"user-{uuid4().hex[:8]}"
    email = f"{username}@test.com"
    client.register(username, email, "password123", full_name="Test User")
    tokens = client.login(username, "password123")
    return client, tokens.access_token


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


def test_health(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path)
    result = client.health()
    assert isinstance(result, HealthResponse)
    assert result.status == "healthy"
    assert result.version
    client.close()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


def test_register_and_login(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path, auth_enabled=True, bootstrap_admin=True)
    username = f"user-{uuid4().hex[:8]}"
    user = client.register(username, f"{username}@test.com", "password123")
    assert isinstance(user, UserResponse)
    assert user.username == username

    tokens = client.login(username, "password123")
    assert isinstance(tokens, TokenResponse)
    assert tokens.access_token
    assert tokens.refresh_token
    client.close()


def test_login_bad_password(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path, auth_enabled=True, bootstrap_admin=True)
    username = f"user-{uuid4().hex[:8]}"
    client.register(username, f"{username}@test.com", "password123")

    with pytest.raises(AuthenticationError) as exc_info:
        client.login(username, "wrong-password")
    assert exc_info.value.status_code == 401
    client.close()


def test_me(tmp_path: Path) -> None:
    client, _ = _make_auth_client(tmp_path)
    user = client.me()
    assert isinstance(user, UserResponse)
    assert user.is_active
    client.close()


def test_refresh_token(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path, auth_enabled=True, bootstrap_admin=True)
    username = f"user-{uuid4().hex[:8]}"
    client.register(username, f"{username}@test.com", "password123")
    tokens = client.login(username, "password123")

    new_tokens = client.refresh_token(tokens.refresh_token)
    assert isinstance(new_tokens, TokenResponse)
    assert new_tokens.access_token != tokens.access_token
    client.close()


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------


def test_list_files(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "readme.txt").write_text("hello", encoding="utf-8")
    (root / "data.csv").write_text("a,b,c", encoding="utf-8")

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    result = client.list_files(str(root))
    assert isinstance(result, FileListResponse)
    assert result.total == 2
    assert len(result.items) == 2
    names = {item.name for item in result.items}
    assert "readme.txt" in names
    assert "data.csv" in names
    client.close()


def test_get_file_info(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    target = root / "doc.txt"
    target.write_text("content", encoding="utf-8")

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    info = client.get_file_info(str(target))
    assert info.name == "doc.txt"
    assert info.size > 0
    client.close()


def test_read_file_content(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    target = root / "note.txt"
    target.write_text("hello world", encoding="utf-8")

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    result = client.read_file_content(str(target))
    assert result.content == "hello world"
    assert not result.truncated
    client.close()


def test_move_file(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    src = root / "old.txt"
    src.write_text("data", encoding="utf-8")
    dst = root / "new.txt"

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    result = client.move_file(str(src), str(dst))
    assert result.moved
    assert not result.dry_run
    assert dst.exists()
    assert not src.exists()
    client.close()


def test_move_file_dry_run(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    src = root / "file.txt"
    src.write_text("data", encoding="utf-8")
    dst = root / "moved.txt"

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    result = client.move_file(str(src), str(dst), dry_run=True)
    assert not result.moved
    assert result.dry_run
    assert src.exists()
    assert not dst.exists()
    client.close()


def test_delete_file_dry_run(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    target = root / "file.txt"
    target.write_text("data", encoding="utf-8")

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    result = client.delete_file(str(target), dry_run=True)
    assert not result.deleted
    assert result.dry_run
    assert target.exists()
    client.close()


# ---------------------------------------------------------------------------
# File not found
# ---------------------------------------------------------------------------


def test_get_file_info_not_found(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    with pytest.raises(NotFoundError) as exc_info:
        client.get_file_info(str(root / "nonexistent.txt"))
    assert exc_info.value.status_code == 404
    client.close()


# ---------------------------------------------------------------------------
# Auth required
# ---------------------------------------------------------------------------


def test_unauthenticated_files_rejected(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path, auth_enabled=True, bootstrap_admin=True)
    # No login - should get 401
    with pytest.raises(AuthenticationError):
        client.list_files(str(tmp_path))
    client.close()


# ---------------------------------------------------------------------------
# Context manager
# ---------------------------------------------------------------------------


def test_context_manager(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path)
    with client:
        result = client.health()
        assert result.status == "healthy"
    # After context exit, client is closed (no assertion needed, just no crash)


# ---------------------------------------------------------------------------
# set_token
# ---------------------------------------------------------------------------


def test_set_token(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path)
    client.set_token("my-token")
    assert client._client.headers["Authorization"] == "Bearer my-token"
    client.close()


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------


def test_scan_directory(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "readme.txt").write_text("hello", encoding="utf-8")
    (root / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    result = client.scan(str(root))
    assert result.total_files == 2
    assert result.input_dir == str(root)
    client.close()


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------


def test_system_status(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    result = client.system_status(str(root))
    assert result.disk_total > 0
    assert result.disk_free > 0
    client.close()


def test_system_stats(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "a.txt").write_text("hello", encoding="utf-8")

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    stats = client.system_stats(path=str(root), use_cache=False)
    assert stats.file_count >= 1
    assert stats.total_size >= 0
    client.close()


def test_update_config_as_admin(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()

    client, _ = _make_auth_client(tmp_path, allowed_root=root)
    updated = client.update_config(
        {
            "profile": "default",
            "default_methodology": "content_based",
            "updates": {"check_on_startup": True},
        }
    )
    assert updated.profile == "default"
    assert "default_methodology" in updated.config
    client.close()


def test_logout_revokes_tokens(tmp_path: Path) -> None:
    client, _ = _make_client(tmp_path, auth_enabled=True, bootstrap_admin=True)
    username = f"user-{uuid4().hex[:8]}"
    client.register(username, f"{username}@test.com", "password123")
    tokens = client.login(username, "password123")
    client.logout(tokens.refresh_token)
    with pytest.raises(AuthenticationError):
        client.me()
    client.close()
