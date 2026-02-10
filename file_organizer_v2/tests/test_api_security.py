"""API tests for security middleware and rate limiting."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from file_organizer.api.api_keys import hash_api_key
from file_organizer.api.main import create_app
from file_organizer.api.test_utils import build_test_settings, create_auth_client

pytestmark = pytest.mark.ci


def test_security_headers_present(tmp_path: Path) -> None:
    settings = build_test_settings(tmp_path, auth_overrides={"security_headers_enabled": True})
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert response.headers["Referrer-Policy"] == settings.security_referrer_policy
    assert "Content-Security-Policy" in response.headers
    assert "Permissions-Policy" in response.headers


def test_rate_limit_blocks_after_threshold(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client, headers, _ = create_auth_client(
        tmp_path,
        [str(data_dir)],
        auth_overrides={
            "rate_limit_enabled": True,
            "rate_limit_default_requests": 1000,
            "rate_limit_default_window_seconds": 60,
            "rate_limit_exempt_paths": [],
            "rate_limit_rules": {"/api/v1/system/status": {"requests": 2, "window_seconds": 60}},
        },
    )

    response = client.get("/api/v1/system/status", params={"path": str(data_dir)}, headers=headers)
    assert response.status_code == 200
    response = client.get("/api/v1/system/status", params={"path": str(data_dir)}, headers=headers)
    assert response.status_code == 200

    blocked = client.get("/api/v1/system/status", params={"path": str(data_dir)}, headers=headers)
    assert blocked.status_code == 429
    assert blocked.headers.get("X-RateLimit-Remaining") == "0"
    assert "Retry-After" in blocked.headers
    assert blocked.headers.get("X-Frame-Options") == "DENY"


def test_rate_limit_exempts_docs_subpaths(tmp_path: Path) -> None:
    settings = build_test_settings(
        tmp_path,
        auth_overrides={
            "enable_docs": True,
            "rate_limit_enabled": True,
            "rate_limit_exempt_paths": ["/docs"],
        },
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.get("/docs")
    assert response.status_code != 429
    response = client.get("/docs/oauth2-redirect")
    assert response.status_code != 429


def test_rate_limit_ignores_proxy_headers(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings = build_test_settings(
        tmp_path,
        allowed_paths=[str(data_dir)],
        auth_overrides={
            "auth_enabled": False,
            "rate_limit_enabled": True,
            "rate_limit_trust_proxy_headers": False,
            "rate_limit_exempt_paths": [],
            "rate_limit_rules": {"/api/v1/system/status": {"requests": 1, "window_seconds": 60}},
        },
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.get(
        "/api/v1/system/status",
        params={"path": str(data_dir)},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert response.status_code == 200

    blocked = client.get(
        "/api/v1/system/status",
        params={"path": str(data_dir)},
        headers={"X-Forwarded-For": "203.0.113.11"},
    )
    assert blocked.status_code == 429


def test_rate_limit_trusts_proxy_headers(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings = build_test_settings(
        tmp_path,
        allowed_paths=[str(data_dir)],
        auth_overrides={
            "auth_enabled": False,
            "rate_limit_enabled": True,
            "rate_limit_trust_proxy_headers": True,
            "rate_limit_exempt_paths": [],
            "rate_limit_rules": {"/api/v1/system/status": {"requests": 1, "window_seconds": 60}},
        },
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.get(
        "/api/v1/system/status",
        params={"path": str(data_dir)},
        headers={"X-Forwarded-For": "203.0.113.10"},
    )
    assert response.status_code == 200

    response = client.get(
        "/api/v1/system/status",
        params={"path": str(data_dir)},
        headers={"X-Forwarded-For": "203.0.113.11"},
    )
    assert response.status_code == 200


def test_api_key_allows_access(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    api_key = "test-api-key"
    settings = build_test_settings(
        tmp_path,
        allowed_paths=[str(data_dir)],
        auth_overrides={
            "api_key_enabled": True,
            "api_key_hashes": [hash_api_key(api_key)],
            "rate_limit_enabled": False,
        },
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.get(
        "/api/v1/system/status",
        params={"path": str(data_dir)},
        headers={settings.api_key_header: api_key},
    )
    assert response.status_code == 200


def test_api_key_admin_required_for_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setenv("FO_CONFIG_DIR", str(config_dir))

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    api_key = "test-api-key"
    settings = build_test_settings(
        tmp_path,
        allowed_paths=[str(data_dir)],
        auth_overrides={
            "api_key_enabled": True,
            "api_key_admin": False,
            "api_key_hashes": [hash_api_key(api_key)],
            "rate_limit_enabled": False,
        },
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.patch(
        "/api/v1/system/config",
        json={"profile": "default", "default_methodology": "para"},
        headers={settings.api_key_header: api_key},
    )
    assert response.status_code == 403


def test_api_key_admin_can_update_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    monkeypatch.setenv("FO_CONFIG_DIR", str(config_dir))

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    api_key = "admin-api-key"
    settings = build_test_settings(
        tmp_path,
        allowed_paths=[str(data_dir)],
        auth_overrides={
            "api_key_enabled": True,
            "api_key_admin": True,
            "api_key_hashes": [hash_api_key(api_key)],
            "rate_limit_enabled": False,
        },
    )
    app = create_app(settings)
    client = TestClient(app)

    response = client.patch(
        "/api/v1/system/config",
        json={"profile": "default", "default_methodology": "para"},
        headers={settings.api_key_header: api_key},
    )
    assert response.status_code == 200


def test_rejects_null_byte_paths(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    client, headers, _ = create_auth_client(tmp_path, [str(data_dir)])

    response = client.post(
        "/api/v1/files/move",
        json={
            "source": f"{data_dir}/bad\u0000name.txt",
            "destination": f"{data_dir}/dest.txt",
            "overwrite": False,
        },
        headers=headers,
    )
    assert response.status_code == 422
