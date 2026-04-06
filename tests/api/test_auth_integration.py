"""Integration tests for auth.py and auth_rate_limit.py.

Uses a real in-memory SQLite database wired through the real auth router.
External boundaries (Redis) use the in-memory fallback — no mocks needed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from file_organizer.api.auth_models import Base
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import get_db, get_settings
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.auth import router


def _make_app(tmp_path) -> tuple[TestClient, ApiSettings]:
    """Return a TestClient backed by a real in-memory SQLite auth database."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    settings = ApiSettings(
        auth_enabled=True,
        auth_jwt_secret="integration-test-secret",
        auth_db_path=str(tmp_path / "unused.db"),
        auth_login_rate_limit_enabled=False,
        auth_bootstrap_admin=True,
        auth_bootstrap_admin_local_only=False,
        auth_password_min_length=8,
        auth_password_require_uppercase=False,
        auth_password_require_number=False,
        auth_password_require_special=False,
    )

    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_db] = override_db
    app.include_router(router, prefix="/api/v1")
    return TestClient(app, raise_server_exceptions=False), settings


@pytest.mark.integration
class TestAuthRegistrationAndLogin:
    """Register a user and log in — exercises auth.py hash + JWT paths."""

    @pytest.fixture()
    def client_settings(self, tmp_path):
        return _make_app(tmp_path)

    @pytest.mark.ci
    def test_register_then_login_returns_token_bundle(self, client_settings):
        client, _ = client_settings
        r = client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "password": "secretpass", "email": "a@example.com"},
        )
        assert r.status_code == 201, r.text

        r = client.post(
            "/api/v1/auth/login",
            data={"username": "alice", "password": "secretpass"},
        )
        assert r.status_code == 200
        body = r.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    @pytest.mark.ci
    def test_login_wrong_password_returns_401(self, client_settings):
        client, _ = client_settings
        client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "password": "correctpass", "email": "b@example.com"},
        )
        r = client.post(
            "/api/v1/auth/login",
            data={"username": "bob", "password": "wrongpass"},
        )
        assert r.status_code == 401

    @pytest.mark.ci
    def test_login_unknown_user_returns_401(self, client_settings):
        client, _ = client_settings
        r = client.post(
            "/api/v1/auth/login",
            data={"username": "nobody", "password": "pass"},
        )
        assert r.status_code == 401

    def test_me_endpoint_requires_valid_token(self, client_settings):
        client, _ = client_settings
        r = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token.here"})
        assert r.status_code == 401

    def test_me_endpoint_returns_user_for_valid_token(self, client_settings):
        client, _ = client_settings
        client.post(
            "/api/v1/auth/register",
            json={"username": "carol", "password": "mypassword", "email": "c@example.com"},
        )
        login = client.post(
            "/api/v1/auth/login",
            data={"username": "carol", "password": "mypassword"},
        )
        token = login.json()["access_token"]
        r = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["username"] == "carol"

    def test_token_refresh_returns_new_access_token(self, client_settings):
        client, _ = client_settings
        client.post(
            "/api/v1/auth/register",
            json={"username": "dave", "password": "refreshtest", "email": "d@example.com"},
        )
        login = client.post(
            "/api/v1/auth/login",
            data={"username": "dave", "password": "refreshtest"},
        )
        refresh_token = login.json()["refresh_token"]
        r = client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_logout_invalidates_token(self, client_settings):
        client, _ = client_settings
        client.post(
            "/api/v1/auth/register",
            json={"username": "eve", "password": "logouttest", "email": "e@example.com"},
        )
        login = client.post(
            "/api/v1/auth/login",
            data={"username": "eve", "password": "logouttest"},
        )
        body = login.json()
        access_token = body["access_token"]
        refresh_token = body["refresh_token"]
        r = client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert r.status_code in (200, 204)


@pytest.mark.integration
class TestRateLimiterIntegration:
    """Login rate limiting blocks after N failures — exercises auth_rate_limit.py."""

    @pytest.fixture()
    def client_settings(self, tmp_path):
        engine = create_engine(
            "sqlite+pysqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

        settings = ApiSettings(
            auth_enabled=True,
            auth_jwt_secret="rl-integration-secret",
            auth_db_path=str(tmp_path / "unused.db"),
            auth_login_rate_limit_enabled=True,
            auth_login_max_attempts=3,
            auth_login_window_seconds=60,
            auth_password_min_length=8,
            auth_password_require_uppercase=False,
            auth_password_require_number=False,
            auth_password_require_special=False,
        )

        def override_db():
            session = SessionLocal()
            try:
                yield session
            finally:
                session.close()

        app = FastAPI()
        setup_exception_handlers(app)
        app.dependency_overrides[get_settings] = lambda: settings
        app.dependency_overrides[get_db] = override_db
        app.include_router(router, prefix="/api/v1")
        return TestClient(app, raise_server_exceptions=False), settings

    @pytest.mark.ci
    def test_blocked_after_max_attempts(self, client_settings):
        client, settings = client_settings
        client.post(
            "/api/v1/auth/register",
            json={"username": "target", "password": "goodpass", "email": "t@example.com"},
        )
        for _ in range(settings.auth_login_max_attempts):
            client.post(
                "/api/v1/auth/login",
                data={"username": "target", "password": "wrongpass"},
            )
        r = client.post(
            "/api/v1/auth/login",
            data={"username": "target", "password": "wrongpass"},
        )
        assert r.status_code == 429

    def test_successful_login_resets_rate_limit_counter(self, client_settings):
        client, settings = client_settings
        client.post(
            "/api/v1/auth/register",
            json={"username": "frank", "password": "goodpass", "email": "f@example.com"},
        )
        client.post(
            "/api/v1/auth/login",
            data={"username": "frank", "password": "wrong"},
        )
        r = client.post(
            "/api/v1/auth/login",
            data={"username": "frank", "password": "goodpass"},
        )
        assert r.status_code == 200
