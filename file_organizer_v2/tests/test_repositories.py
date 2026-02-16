"""Tests for the repository layer (WorkspaceRepository, JobRepository, SettingsRepository)."""
from __future__ import annotations

import json
import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Side-effect import to register all tables on Base.metadata
import file_organizer.api.db_models  # noqa: F401
from file_organizer.api.auth_models import Base, User
from file_organizer.api.repositories.job_repo import JobRepository
from file_organizer.api.repositories.settings_repo import SettingsRepository
from file_organizer.api.repositories.workspace_repo import WorkspaceRepository

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def db_session():
    """Provide a clean in-memory database session for each test."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(bind=engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def user(db_session: Session) -> User:
    """Create and return a test user."""
    u = User(
        id=str(uuid.uuid4()),
        username="repouser",
        email="repo@example.com",
        hashed_password="fakehash",
    )
    db_session.add(u)
    db_session.flush()
    return u


@pytest.fixture()
def second_user(db_session: Session) -> User:
    """Create a second test user for multi-user scenarios."""
    u = User(
        id=str(uuid.uuid4()),
        username="repouser2",
        email="repo2@example.com",
        hashed_password="fakehash",
    )
    db_session.add(u)
    db_session.flush()
    return u


# ------------------------------------------------------------------
# WorkspaceRepository
# ------------------------------------------------------------------


class TestWorkspaceRepository:
    """Tests for WorkspaceRepository CRUD operations."""

    def test_create(self, db_session: Session, user: User) -> None:
        ws = WorkspaceRepository.create(
            db_session,
            name="Test WS",
            owner_id=user.id,
            root_path="/tmp/test",
            description="desc",
        )
        assert ws.id is not None
        assert ws.name == "Test WS"
        assert ws.owner_id == user.id
        assert ws.root_path == "/tmp/test"
        assert ws.description == "desc"
        assert ws.is_active is True

    def test_create_without_description(self, db_session: Session, user: User) -> None:
        ws = WorkspaceRepository.create(
            db_session,
            name="NoDesc",
            owner_id=user.id,
            root_path="/tmp/nd",
        )
        assert ws.description is None

    def test_get_by_id(self, db_session: Session, user: User) -> None:
        ws = WorkspaceRepository.create(
            db_session, name="Find Me", owner_id=user.id, root_path="/tmp/find"
        )
        found = WorkspaceRepository.get_by_id(db_session, ws.id)
        assert found is not None
        assert found.name == "Find Me"

    def test_get_by_id_missing(self, db_session: Session) -> None:
        result = WorkspaceRepository.get_by_id(db_session, "nonexistent")
        assert result is None

    def test_list_by_owner(self, db_session: Session, user: User, second_user: User) -> None:
        WorkspaceRepository.create(db_session, name="A", owner_id=user.id, root_path="/a")
        WorkspaceRepository.create(db_session, name="B", owner_id=user.id, root_path="/b")
        WorkspaceRepository.create(db_session, name="C", owner_id=second_user.id, root_path="/c")

        result = WorkspaceRepository.list_by_owner(db_session, user.id)
        assert len(result) == 2
        assert [ws.name for ws in result] == ["A", "B"]

    def test_list_by_owner_empty(self, db_session: Session) -> None:
        result = WorkspaceRepository.list_by_owner(db_session, "nobody")
        assert result == []

    def test_update(self, db_session: Session, user: User) -> None:
        ws = WorkspaceRepository.create(
            db_session, name="Old", owner_id=user.id, root_path="/old"
        )
        updated = WorkspaceRepository.update(
            db_session, ws.id, name="New", description="Updated"
        )
        assert updated is not None
        assert updated.name == "New"
        assert updated.description == "Updated"

    def test_update_ignores_unknown_keys(self, db_session: Session, user: User) -> None:
        ws = WorkspaceRepository.create(
            db_session, name="Stable", owner_id=user.id, root_path="/s"
        )
        updated = WorkspaceRepository.update(
            db_session, ws.id, name="Changed", unknown_field="ignored"
        )
        assert updated is not None
        assert updated.name == "Changed"

    def test_update_missing(self, db_session: Session) -> None:
        result = WorkspaceRepository.update(db_session, "missing", name="x")
        assert result is None

    def test_update_is_active(self, db_session: Session, user: User) -> None:
        ws = WorkspaceRepository.create(
            db_session, name="Active", owner_id=user.id, root_path="/a"
        )
        updated = WorkspaceRepository.update(db_session, ws.id, is_active=False)
        assert updated is not None
        assert updated.is_active is False

    def test_delete(self, db_session: Session, user: User) -> None:
        ws = WorkspaceRepository.create(
            db_session, name="Del", owner_id=user.id, root_path="/del"
        )
        ws_id = ws.id
        assert WorkspaceRepository.delete(db_session, ws_id) is True
        assert WorkspaceRepository.get_by_id(db_session, ws_id) is None

    def test_delete_missing(self, db_session: Session) -> None:
        assert WorkspaceRepository.delete(db_session, "missing") is False


# ------------------------------------------------------------------
# JobRepository
# ------------------------------------------------------------------


class TestJobRepository:
    """Tests for JobRepository CRUD operations."""

    def test_create_defaults(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, input_dir="/in", output_dir="/out")
        assert job.id is not None
        assert job.status == "queued"
        assert job.job_type == "organize"
        assert job.methodology == "content_based"
        assert job.dry_run is False

    def test_create_with_options(self, db_session: Session, user: User) -> None:
        job = JobRepository.create(
            db_session,
            input_dir="/in",
            output_dir="/out",
            owner_id=user.id,
            job_type="dedupe",
            methodology="para",
            dry_run=True,
        )
        assert job.owner_id == user.id
        assert job.job_type == "dedupe"
        assert job.methodology == "para"
        assert job.dry_run is True

    def test_get_by_id(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, input_dir="/in", output_dir="/out")
        found = JobRepository.get_by_id(db_session, job.id)
        assert found is not None
        assert found.input_dir == "/in"

    def test_get_by_id_missing(self, db_session: Session) -> None:
        assert JobRepository.get_by_id(db_session, "nope") is None

    def test_list_jobs_no_filter(self, db_session: Session) -> None:
        JobRepository.create(db_session, input_dir="/a", output_dir="/b")
        JobRepository.create(db_session, input_dir="/c", output_dir="/d")
        jobs = JobRepository.list_jobs(db_session)
        assert len(jobs) == 2

    def test_list_jobs_by_owner(self, db_session: Session, user: User, second_user: User) -> None:
        JobRepository.create(db_session, input_dir="/a", output_dir="/b", owner_id=user.id)
        JobRepository.create(db_session, input_dir="/c", output_dir="/d", owner_id=second_user.id)

        jobs = JobRepository.list_jobs(db_session, owner_id=user.id)
        assert len(jobs) == 1
        assert jobs[0].owner_id == user.id

    def test_list_jobs_by_status(self, db_session: Session) -> None:
        j1 = JobRepository.create(db_session, input_dir="/a", output_dir="/b")
        JobRepository.update_status(db_session, j1.id, "completed")
        JobRepository.create(db_session, input_dir="/c", output_dir="/d")

        queued = JobRepository.list_jobs(db_session, status="queued")
        assert len(queued) == 1
        completed = JobRepository.list_jobs(db_session, status="completed")
        assert len(completed) == 1

    def test_list_jobs_limit(self, db_session: Session) -> None:
        for i in range(5):
            JobRepository.create(db_session, input_dir=f"/in{i}", output_dir=f"/out{i}")
        jobs = JobRepository.list_jobs(db_session, limit=3)
        assert len(jobs) == 3

    def test_list_jobs_order(self, db_session: Session) -> None:
        j1 = JobRepository.create(db_session, input_dir="/first", output_dir="/o")
        j2 = JobRepository.create(db_session, input_dir="/second", output_dir="/o")
        jobs = JobRepository.list_jobs(db_session)
        # Newest first
        assert jobs[0].id == j2.id
        assert jobs[1].id == j1.id

    def test_update_status(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, input_dir="/in", output_dir="/out")
        updated = JobRepository.update_status(db_session, job.id, "running")
        assert updated is not None
        assert updated.status == "running"
        assert updated.error is None

    def test_update_status_with_error(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, input_dir="/in", output_dir="/out")
        updated = JobRepository.update_status(db_session, job.id, "failed", error="disk full")
        assert updated is not None
        assert updated.status == "failed"
        assert updated.error == "disk full"

    def test_update_status_missing(self, db_session: Session) -> None:
        assert JobRepository.update_status(db_session, "missing", "running") is None

    def test_update_result(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, input_dir="/in", output_dir="/out")
        result_blob = json.dumps({"organized": True})
        updated = JobRepository.update_result(
            db_session,
            job.id,
            total_files=10,
            processed_files=8,
            failed_files=1,
            skipped_files=1,
            result_json=result_blob,
        )
        assert updated is not None
        assert updated.total_files == 10
        assert updated.processed_files == 8
        assert updated.failed_files == 1
        assert updated.skipped_files == 1
        assert updated.result_json == result_blob

    def test_update_result_partial(self, db_session: Session) -> None:
        job = JobRepository.create(db_session, input_dir="/in", output_dir="/out")
        updated = JobRepository.update_result(db_session, job.id, processed_files=5)
        assert updated is not None
        assert updated.processed_files == 5
        assert updated.total_files == 0  # Unchanged default

    def test_update_result_missing(self, db_session: Session) -> None:
        assert JobRepository.update_result(db_session, "nope", total_files=1) is None


# ------------------------------------------------------------------
# SettingsRepository
# ------------------------------------------------------------------


class TestSettingsRepository:
    """Tests for SettingsRepository CRUD operations."""

    def test_set_and_get_global(self, db_session: Session) -> None:
        SettingsRepository.set(db_session, "theme", "dark")
        assert SettingsRepository.get(db_session, "theme") == "dark"

    def test_set_and_get_user_scoped(self, db_session: Session, user: User) -> None:
        SettingsRepository.set(db_session, "theme", "light", user_id=user.id)
        assert SettingsRepository.get(db_session, "theme", user_id=user.id) == "light"
        # Global should be unset
        assert SettingsRepository.get(db_session, "theme") is None

    def test_get_missing(self, db_session: Session) -> None:
        assert SettingsRepository.get(db_session, "nonexistent") is None

    def test_set_upsert(self, db_session: Session) -> None:
        SettingsRepository.set(db_session, "color", "red")
        SettingsRepository.set(db_session, "color", "blue")
        assert SettingsRepository.get(db_session, "color") == "blue"

    def test_set_returns_row(self, db_session: Session) -> None:
        row = SettingsRepository.set(db_session, "k", "v")
        assert row.key == "k"
        assert row.value == "v"

    def test_delete(self, db_session: Session) -> None:
        SettingsRepository.set(db_session, "del_key", "val")
        assert SettingsRepository.delete(db_session, "del_key") is True
        assert SettingsRepository.get(db_session, "del_key") is None

    def test_delete_missing(self, db_session: Session) -> None:
        assert SettingsRepository.delete(db_session, "nope") is False

    def test_delete_user_scoped(self, db_session: Session, user: User) -> None:
        SettingsRepository.set(db_session, "scoped", "val", user_id=user.id)
        # Deleting global scope should not remove user-scoped entry
        assert SettingsRepository.delete(db_session, "scoped") is False
        assert SettingsRepository.get(db_session, "scoped", user_id=user.id) == "val"
        # Deleting correct scope works
        assert SettingsRepository.delete(db_session, "scoped", user_id=user.id) is True
        assert SettingsRepository.get(db_session, "scoped", user_id=user.id) is None

    def test_list_all_global(self, db_session: Session) -> None:
        SettingsRepository.set(db_session, "a", "1")
        SettingsRepository.set(db_session, "b", "2")
        result = SettingsRepository.list_all(db_session)
        assert result == {"a": "1", "b": "2"}

    def test_list_all_user_scoped(self, db_session: Session, user: User) -> None:
        SettingsRepository.set(db_session, "x", "10", user_id=user.id)
        SettingsRepository.set(db_session, "y", "20", user_id=user.id)
        # Also add a global setting that should NOT appear
        SettingsRepository.set(db_session, "z", "30")

        result = SettingsRepository.list_all(db_session, user_id=user.id)
        assert result == {"x": "10", "y": "20"}

    def test_list_all_empty(self, db_session: Session) -> None:
        result = SettingsRepository.list_all(db_session)
        assert result == {}

    def test_set_none_value(self, db_session: Session) -> None:
        row = SettingsRepository.set(db_session, "nullable", None)
        assert row.value is None
        assert SettingsRepository.get(db_session, "nullable") is None

    def test_isolation_between_users(
        self, db_session: Session, user: User, second_user: User
    ) -> None:
        SettingsRepository.set(db_session, "pref", "A", user_id=user.id)
        SettingsRepository.set(db_session, "pref", "B", user_id=second_user.id)

        assert SettingsRepository.get(db_session, "pref", user_id=user.id) == "A"
        assert SettingsRepository.get(db_session, "pref", user_id=second_user.id) == "B"


# ------------------------------------------------------------------
# init_db integration
# ------------------------------------------------------------------


class TestInitDb:
    """Test the init_db convenience function."""

    def test_init_db_creates_all_tables(self) -> None:
        from sqlalchemy import inspect as sa_inspect

        from file_organizer.api.db import init_db

        init_db(":memory:")

        from file_organizer.api.db import get_engine

        engine = get_engine(":memory:")
        inspector = sa_inspect(engine)
        tables = set(inspector.get_table_names())
        assert "workspaces" in tables
        assert "organization_jobs" in tables
        assert "settings_store" in tables
        assert "plugin_installations" in tables
        assert "users" in tables
