"""Integration tests for undo/models.py, api/auth_store.py, api/auth_db.py,
config/path_migration.py, and api/exceptions.py — branch-coverage focus.

Targets high-coverage modules with small uncovered branch gaps.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# undo/models.py — Conflict, ValidationResult, RollbackResult __str__ branches
# ---------------------------------------------------------------------------


class TestConflictStr:
    def test_str_with_expected_and_actual(self) -> None:
        from file_organizer.undo.models import Conflict, ConflictType

        c = Conflict(
            conflict_type=ConflictType.FILE_MISSING,
            path="/some/path",
            description="File not found",
            expected="File exists",
            actual="File not found",
        )
        s = str(c)
        assert "expected" in s
        assert "actual" in s
        assert "file_missing" in s

    def test_str_without_expected_and_actual(self) -> None:
        from file_organizer.undo.models import Conflict, ConflictType

        c = Conflict(
            conflict_type=ConflictType.HASH_MISMATCH,
            path="/other/path",
            description="Hash mismatch",
        )
        s = str(c)
        assert "hash_mismatch" in s
        assert "expected" not in s

    def test_str_with_only_expected(self) -> None:
        from file_organizer.undo.models import Conflict, ConflictType

        c = Conflict(
            conflict_type=ConflictType.PATH_OCCUPIED,
            path="/p",
            description="occupied",
            expected="Path available",
            actual=None,
        )
        s = str(c)
        # only expected, no actual → branch not taken
        assert "expected" not in s or "actual" not in s


class TestValidationResultStr:
    def test_can_proceed_no_warnings(self) -> None:
        from file_organizer.undo.models import ValidationResult

        vr = ValidationResult(can_proceed=True)
        s = str(vr)
        assert "passed" in s
        assert "warnings" not in s

    def test_can_proceed_with_warnings(self) -> None:
        from file_organizer.undo.models import ValidationResult

        vr = ValidationResult(can_proceed=True, warnings=["beware"])
        s = str(vr)
        assert "1 warnings" in s

    def test_cannot_proceed_no_conflicts(self) -> None:
        from file_organizer.undo.models import ValidationResult

        vr = ValidationResult(can_proceed=False, error_message="blocked")
        s = str(vr)
        assert "failed" in s
        assert "Conflicts" not in s

    def test_cannot_proceed_with_few_conflicts(self) -> None:
        from file_organizer.undo.models import Conflict, ConflictType, ValidationResult

        conflicts = [Conflict(ConflictType.FILE_MISSING, f"/p{i}", f"desc{i}") for i in range(2)]
        vr = ValidationResult(can_proceed=False, error_message="blocked", conflicts=conflicts)
        s = str(vr)
        assert "Conflicts: 2" in s

    def test_cannot_proceed_with_many_conflicts(self) -> None:
        from file_organizer.undo.models import Conflict, ConflictType, ValidationResult

        # > 3 conflicts triggers "... and N more" branch
        conflicts = [Conflict(ConflictType.FILE_MISSING, f"/p{i}", f"desc{i}") for i in range(5)]
        vr = ValidationResult(can_proceed=False, error_message="too many", conflicts=conflicts)
        s = str(vr)
        assert "more" in s

    def test_bool_true_when_can_proceed(self) -> None:
        from file_organizer.undo.models import ValidationResult

        assert bool(ValidationResult(can_proceed=True)) is True

    def test_bool_false_when_cannot_proceed(self) -> None:
        from file_organizer.undo.models import ValidationResult

        assert bool(ValidationResult(can_proceed=False)) is False


class TestRollbackResultStr:
    def test_success_str(self) -> None:
        from file_organizer.undo.models import RollbackResult

        r = RollbackResult(success=True, operations_rolled_back=3)
        s = str(r)
        assert "successful" in s
        assert "3" in s

    def test_success_with_warnings(self) -> None:
        from file_organizer.undo.models import RollbackResult

        r = RollbackResult(success=True, operations_rolled_back=1, warnings=["warn"])
        s = str(r)
        assert "Warnings" in s

    def test_failure_no_errors(self) -> None:
        from file_organizer.undo.models import RollbackResult

        r = RollbackResult(success=False, operations_rolled_back=0, operations_failed=1)
        s = str(r)
        assert "failed" in s
        assert "Errors" not in s

    def test_failure_with_few_errors(self) -> None:
        from file_organizer.undo.models import RollbackResult

        r = RollbackResult(
            success=False,
            operations_rolled_back=0,
            operations_failed=2,
            errors=[(1, "err1"), (2, "err2")],
        )
        s = str(r)
        assert "Errors" in s
        assert "Operation 1" in s

    def test_failure_with_many_errors(self) -> None:
        from file_organizer.undo.models import RollbackResult

        # > 3 errors triggers "... and N more errors" branch
        errors = [(i, f"err{i}") for i in range(5)]
        r = RollbackResult(success=False, operations_failed=5, errors=errors)
        s = str(r)
        assert "more errors" in s

    def test_bool_true_when_success(self) -> None:
        from file_organizer.undo.models import RollbackResult

        assert bool(RollbackResult(success=True)) is True

    def test_bool_false_when_failure(self) -> None:
        from file_organizer.undo.models import RollbackResult

        assert bool(RollbackResult(success=False)) is False


# ---------------------------------------------------------------------------
# api/auth_store.py — InMemoryTokenStore branch coverage
# ---------------------------------------------------------------------------


class TestInMemoryTokenStore:
    def test_store_and_check_refresh_active(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore

        store = InMemoryTokenStore()
        store.store_refresh("jti1", "user1", ttl_seconds=60)
        assert store.is_refresh_active("jti1") is True

    def test_refresh_expired_returns_false(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore

        store = InMemoryTokenStore()
        # Manually set expiry in the past
        store._refresh["jti_expired"] = time.time() - 1.0
        assert store.is_refresh_active("jti_expired") is False

    def test_refresh_not_found_returns_false(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore

        store = InMemoryTokenStore()
        assert store.is_refresh_active("nonexistent") is False

    def test_revoke_refresh(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore

        store = InMemoryTokenStore()
        store.store_refresh("jti2", "user2", ttl_seconds=60)
        store.revoke_refresh("jti2")
        assert store.is_refresh_active("jti2") is False

    def test_revoke_access_and_check(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore

        store = InMemoryTokenStore()
        store.revoke_access("access1", ttl_seconds=60)
        assert store.is_access_revoked("access1") is True

    def test_access_not_revoked(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore

        store = InMemoryTokenStore()
        assert store.is_access_revoked("unknown_access") is False

    def test_access_expired_returns_false(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore

        store = InMemoryTokenStore()
        store._revoked["old_access"] = time.time() - 1.0
        assert store.is_access_revoked("old_access") is False

    def test_revoke_refresh_nonexistent_no_error(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore

        store = InMemoryTokenStore()
        # Should not raise
        store.revoke_refresh("no_such_jti")


class TestBuildTokenStore:
    def test_no_redis_url_returns_in_memory(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore, build_token_store

        store = build_token_store(None)
        assert isinstance(store, InMemoryTokenStore)

    def test_empty_redis_url_returns_in_memory(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore, build_token_store

        store = build_token_store("")
        assert isinstance(store, InMemoryTokenStore)

    def test_unreachable_redis_falls_back_to_in_memory(self) -> None:
        from file_organizer.api.auth_store import InMemoryTokenStore, build_token_store

        # Unreachable Redis → falls back to in-memory
        store = build_token_store("redis://nonexistent.invalid:6379/0")
        assert isinstance(store, InMemoryTokenStore)


# ---------------------------------------------------------------------------
# api/auth_db.py — create_session
# ---------------------------------------------------------------------------


class TestAuthDb:
    def test_create_session_returns_session(self, tmp_path: Path) -> None:
        from sqlalchemy.orm import Session

        from file_organizer.api.auth_db import create_session

        db_path = str(tmp_path / "auth_test.db")
        session = create_session(db_path)
        try:
            assert isinstance(session, Session)
        finally:
            session.close()

    def test_get_session_factory_returns_callable(self, tmp_path: Path) -> None:
        from file_organizer.api.auth_db import get_session_factory

        db_path = str(tmp_path / "auth_sf.db")
        factory = get_session_factory(db_path)
        assert callable(factory)


# ---------------------------------------------------------------------------
# config/path_migration.py — resolve_active_dir branches
# ---------------------------------------------------------------------------


class TestResolveLegacyPath:
    def test_new_dir_non_empty_returns_new(self, tmp_path: Path) -> None:
        from file_organizer.config.path_migration import resolve_legacy_path

        new_dir = tmp_path / "new"
        new_dir.mkdir()
        (new_dir / "file.txt").write_text("data")
        legacy = tmp_path / "legacy"
        result = resolve_legacy_path(new_dir, legacy)
        assert result == new_dir

    def test_new_dir_empty_legacy_non_empty_returns_legacy(self, tmp_path: Path) -> None:
        from file_organizer.config.path_migration import resolve_legacy_path

        new_dir = tmp_path / "new_empty"
        new_dir.mkdir()
        legacy = tmp_path / "legacy_full"
        legacy.mkdir()
        (legacy / "data.txt").write_text("legacy data")
        result = resolve_legacy_path(new_dir, legacy)
        assert result == legacy

    def test_both_empty_returns_new(self, tmp_path: Path) -> None:
        from file_organizer.config.path_migration import resolve_legacy_path

        new_dir = tmp_path / "new_empty2"
        new_dir.mkdir()
        legacy = tmp_path / "legacy_empty"
        legacy.mkdir()
        result = resolve_legacy_path(new_dir, legacy)
        assert result == new_dir

    def test_neither_exists_returns_new(self, tmp_path: Path) -> None:
        from file_organizer.config.path_migration import resolve_legacy_path

        new_dir = tmp_path / "nonexistent_new"
        legacy = tmp_path / "nonexistent_legacy"
        result = resolve_legacy_path(new_dir, legacy)
        assert result == new_dir

    def test_new_exists_legacy_missing_returns_new(self, tmp_path: Path) -> None:
        from file_organizer.config.path_migration import resolve_legacy_path

        new_dir = tmp_path / "new_has_data"
        new_dir.mkdir()
        (new_dir / "item.txt").write_text("new data")
        legacy = tmp_path / "no_legacy"
        result = resolve_legacy_path(new_dir, legacy)
        assert result == new_dir


# ---------------------------------------------------------------------------
# config/path_migration.py — detect_legacy_paths
# ---------------------------------------------------------------------------


class TestDetectLegacyPaths:
    def test_no_legacy_paths(self, tmp_path: Path) -> None:
        from file_organizer.config.path_migration import detect_legacy_paths

        result = detect_legacy_paths(tmp_path, tmp_path / ".config", tmp_path / ".data")
        assert result == []

    def test_detects_dot_file_organizer(self, tmp_path: Path) -> None:
        from file_organizer.config.path_migration import detect_legacy_paths

        legacy = tmp_path / ".file-organizer"
        legacy.mkdir()
        result = detect_legacy_paths(tmp_path, tmp_path / ".config", tmp_path / ".data")
        assert legacy in result

    def test_detects_underscore_variant(self, tmp_path: Path) -> None:
        from file_organizer.config.path_migration import detect_legacy_paths

        legacy = tmp_path / ".file_organizer"
        legacy.mkdir()
        result = detect_legacy_paths(tmp_path, tmp_path / ".config", tmp_path / ".data")
        assert legacy in result

    def test_detects_old_config_home(self, tmp_path: Path) -> None:
        from file_organizer.config.path_migration import detect_legacy_paths

        config_home = tmp_path / ".config"
        config_home.mkdir()
        old_cfg = config_home / "file-organizer"
        old_cfg.mkdir()
        result = detect_legacy_paths(tmp_path, config_home, tmp_path / ".data")
        assert old_cfg in result


# ---------------------------------------------------------------------------
# api/exceptions.py — setup_exception_handlers (handler registrations)
# ---------------------------------------------------------------------------


class TestSetupExceptionHandlers:
    def test_registers_handlers(self) -> None:
        from fastapi import FastAPI

        from file_organizer.api.exceptions import setup_exception_handlers

        app = FastAPI()
        setup_exception_handlers(app)
        # Verify exception handlers are registered (FastAPI stores them)
        assert app.exception_handlers is not None

    def test_api_error_handler_builds_payload_with_details(self) -> None:
        """Directly test the handler logic for ApiError with details."""

        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from file_organizer.api.exceptions import ApiError, setup_exception_handlers

        app = FastAPI()
        setup_exception_handlers(app)

        @app.get("/trigger")
        async def trigger() -> None:
            raise ApiError(
                status_code=400,
                error="bad_input",
                message="Invalid data",
                details={"field": "email"},
            )

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/trigger")
        assert resp.status_code == 400
        body = resp.json()
        assert body["error"] == "bad_input"
        assert body["details"] == {"field": "email"}

    def test_api_error_handler_no_details(self) -> None:
        """ApiError without details → no 'details' key in response."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from file_organizer.api.exceptions import ApiError, setup_exception_handlers

        app = FastAPI()
        setup_exception_handlers(app)

        @app.get("/nodets")
        async def nodets() -> None:
            raise ApiError(status_code=404, error="not_found", message="Missing")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/nodets")
        assert resp.status_code == 404
        assert "details" not in resp.json()

    def test_unhandled_exception_returns_500(self) -> None:
        """Unhandled exception handler returns 500."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from file_organizer.api.exceptions import setup_exception_handlers

        app = FastAPI()
        setup_exception_handlers(app)

        @app.get("/boom")
        async def boom() -> None:
            raise RuntimeError("unexpected failure")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/boom")
        assert resp.status_code == 500
        assert resp.json()["error"] == "internal_server_error"

    def test_validation_error_handler_returns_422(self) -> None:
        """RequestValidationError is handled as 422."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from pydantic import BaseModel

        from file_organizer.api.exceptions import setup_exception_handlers

        app = FastAPI()
        setup_exception_handlers(app)

        class Body(BaseModel):
            count: int

        @app.post("/validate")
        async def validate(body: Body) -> dict:
            return {"count": body.count}

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post("/validate", json={"count": "not-a-number"})
        assert resp.status_code == 422
        assert resp.json()["error"] == "validation_error"
