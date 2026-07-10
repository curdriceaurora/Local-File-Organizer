"""Tests for the persisted configuration API router."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from file_organizer.api.auth_models import User
from file_organizer.api.config import ApiSettings
from file_organizer.api.dependencies import (
    get_config_manager,
    get_current_active_user,
    get_settings,
)
from file_organizer.api.exceptions import setup_exception_handlers
from file_organizer.api.routers.config import _apply_update, router
from file_organizer.config.manager import ConfigManager
from file_organizer.config.schema import AppConfig

pytestmark = [pytest.mark.ci, pytest.mark.integration]


def _build_app(
    config_dir: Path,
    admin_user: User | None = None,
    auth_enabled: bool = False,
) -> tuple[ConfigManager, TestClient]:
    """Create a FastAPI app with config router and dependency overrides."""
    settings = ApiSettings(
        environment="test",
        auth_enabled=auth_enabled,
        auth_db_path=str(config_dir / "auth.db"),
    )
    manager = ConfigManager(config_dir=config_dir)
    app = FastAPI()
    setup_exception_handlers(app)
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_config_manager] = lambda: manager
    app.dependency_overrides[get_current_active_user] = lambda: admin_user
    app.include_router(router, prefix="/api/v1")
    client = TestClient(app, raise_server_exceptions=False)
    return manager, client


def _admin_user() -> MagicMock:
    """Return a mock active admin user."""
    admin = MagicMock(spec=User)
    admin.is_admin = True
    admin.is_active = True
    return admin


@pytest.mark.unit
class TestGetConfig:
    """Tests for GET /api/v1/config."""

    def test_get_config_default(self, tmp_path: Path) -> None:
        """GET returns the real AppConfig shape."""
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/config")

        assert resp.status_code == 200
        body = resp.json()
        assert body["profile"] == "default"
        assert body["profiles"] == []
        config = body["config"]
        assert config["default_methodology"] == "none"
        assert config["setup_completed"] is False
        assert config["setup_deferred"] is False
        assert config["models"]["text_model"] == "qwen2.5:3b-instruct-q4_K_M"
        assert config["updates"]["repo"] == "curdriceaurora/Local-File-Organizer"

    def test_get_config_named_profile(self, tmp_path: Path) -> None:
        """GET can load a named profile."""
        _, client = _build_app(tmp_path)

        resp = client.get("/api/v1/config", params={"profile": "work"})

        assert resp.status_code == 200
        assert resp.json()["profile"] == "work"


@pytest.mark.unit
class TestUpdateConfig:
    """Tests for PUT /api/v1/config."""

    def test_update_config_requires_admin(self, tmp_path: Path) -> None:
        """Only admin users can update config when auth is enabled."""
        non_admin = MagicMock(spec=User)
        non_admin.is_admin = False
        non_admin.is_active = True
        _, client = _build_app(tmp_path, admin_user=non_admin, auth_enabled=True)

        resp = client.put(
            "/api/v1/config",
            json={"models": {"text_model": "qwen2.5:7b"}},
        )

        assert resp.status_code in {401, 403}

    def test_update_config_persists_models(self, tmp_path: Path) -> None:
        """Model updates are saved through ConfigManager, not process memory."""
        manager, client = _build_app(tmp_path, admin_user=_admin_user())

        resp = client.put(
            "/api/v1/config",
            json={
                "models": {
                    "text_model": "custom-model",
                    "temperature": 0.8,
                    "max_tokens": 4000,
                }
            },
        )

        assert resp.status_code == 200
        config = resp.json()["config"]
        assert config["models"]["text_model"] == "custom-model"
        assert config["models"]["temperature"] == 0.8
        assert config["models"]["max_tokens"] == 4000

        reloaded = ConfigManager(config_dir=manager.config_dir).load()
        assert reloaded.models.text_model == "custom-model"
        assert reloaded.models.temperature == pytest.approx(0.8)
        assert reloaded.models.max_tokens == 4000

    def test_update_config_load_and_save_use_profile_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The full load/mutate/save sequence runs under the profile lock."""
        manager, client = _build_app(tmp_path, admin_user=_admin_user())
        original_load = manager.load
        original_save = manager.save
        lock_depth = 0

        def guarded_load(profile: str = "default"):
            assert lock_depth == 1
            return original_load(profile)

        def guarded_save(*args, **kwargs):
            assert lock_depth == 1
            return original_save(*args, **kwargs)

        class TrackingLock:
            def __enter__(self):
                nonlocal lock_depth
                lock_depth += 1

            def __exit__(self, exc_type, exc, tb):
                nonlocal lock_depth
                lock_depth -= 1

        monkeypatch.setattr(manager, "load", guarded_load)
        monkeypatch.setattr(manager, "save", guarded_save)
        monkeypatch.setattr(
            "file_organizer.api.routers.config._profile_update_lock",
            lambda _manager, _profile: TrackingLock(),
        )

        resp = client.put("/api/v1/config", json={"default_methodology": "para"})

        assert resp.status_code == 200
        assert lock_depth == 0

    def test_update_config_partial_update_preserves_other_fields(self, tmp_path: Path) -> None:
        """Partial updates keep fields that were not mentioned."""
        _, client = _build_app(tmp_path, admin_user=_admin_user())

        resp = client.put(
            "/api/v1/config",
            json={"default_methodology": "para"},
        )

        assert resp.status_code == 200
        config = resp.json()["config"]
        assert config["default_methodology"] == "para"
        assert config["models"]["temperature"] == 0.5
        assert config["updates"]["check_on_startup"] is True

    def test_update_config_normalizes_legacy_methodology_value(self, tmp_path: Path) -> None:
        """A pre-unification/legacy methodology value is normalized on write.

        Regression test: this endpoint previously wrote request.default_methodology
        straight onto AppConfig with no validation at all, so an unrecognized or
        legacy-web value (e.g. "content_based") would corrupt the persisted config
        with a value the TUI/core vocabulary doesn't recognize.
        """
        _, client = _build_app(tmp_path, admin_user=_admin_user())

        resp = client.put(
            "/api/v1/config",
            json={"default_methodology": "content_based"},
        )

        assert resp.status_code == 200
        assert resp.json()["config"]["default_methodology"] == "none"

    def test_update_config_multiple_sections(self, tmp_path: Path) -> None:
        """PUT can update top-level, model, update, and module override fields."""
        _, client = _build_app(tmp_path, admin_user=_admin_user())

        resp = client.put(
            "/api/v1/config",
            json={
                "profile": "team",
                "default_methodology": "jd",
                "models": {"text_model": "new-model", "framework": "mlx"},
                "updates": {"include_prereleases": True},
                "watcher": {"enabled": True},
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["profile"] == "team"
        config = body["config"]
        assert config["default_methodology"] == "jd"
        assert config["models"]["framework"] == "mlx"
        assert config["updates"]["include_prereleases"] is True
        assert config["watcher"] == {"enabled": True}

    def test_apply_update_ignores_unknown_request_fields(self) -> None:
        """Defensive helper path ignores fields that are not AppConfig attributes."""
        config = AppConfig()
        request = SimpleNamespace(
            default_methodology=None,
            models=None,
            updates=None,
            model_dump=lambda exclude_none=True: {"unknown_section": {"enabled": True}},
        )

        _apply_update(config, request)

        assert not hasattr(config, "unknown_section")

    def test_update_config_unsupported_version_returns_409(self, tmp_path: Path) -> None:
        """PUT refuses to overwrite unsupported on-disk profiles."""
        (tmp_path / "config.yaml").write_text(
            "profiles:\n  default:\n    version: '999.0'\n    default_methodology: para\n",
            encoding="utf-8",
        )
        _, client = _build_app(tmp_path, admin_user=_admin_user())

        resp = client.put("/api/v1/config", json={"default_methodology": "jd"})

        assert resp.status_code == 409
        assert resp.json()["error"] == "unsupported_config_version"


@pytest.mark.unit
class TestResetConfig:
    """Tests for POST /api/v1/config/reset."""

    def test_reset_config_requires_admin(self, tmp_path: Path) -> None:
        """Only admin users can reset config when auth is enabled."""
        non_admin = MagicMock(spec=User)
        non_admin.is_admin = False
        non_admin.is_active = True
        _, client = _build_app(tmp_path, admin_user=non_admin, auth_enabled=True)

        resp = client.post("/api/v1/config/reset")

        assert resp.status_code in {401, 403}

    def test_reset_config_to_defaults(self, tmp_path: Path) -> None:
        """Reset writes default config through ConfigManager."""
        manager, client = _build_app(tmp_path, admin_user=_admin_user())
        client.put(
            "/api/v1/config",
            json={"models": {"text_model": "custom"}, "default_methodology": "para"},
        )

        resp = client.post("/api/v1/config/reset")

        assert resp.status_code == 200
        config = resp.json()["config"]
        assert config["default_methodology"] == "none"
        assert config["models"]["text_model"] == "qwen2.5:3b-instruct-q4_K_M"
        assert ConfigManager(config_dir=manager.config_dir).load().default_methodology == "none"

    def test_reset_named_profile(self, tmp_path: Path) -> None:
        """Reset supports named profiles."""
        _, client = _build_app(tmp_path, admin_user=_admin_user())

        resp = client.post("/api/v1/config/reset", params={"profile": "work"})

        assert resp.status_code == 200
        assert resp.json()["profile"] == "work"
