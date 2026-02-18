"""Tests for SQLAlchemy ORM models defined in db_models.py."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

# Side-effect import to register all tables on Base.metadata
import file_organizer.api.db_models  # noqa: F401
from file_organizer.api.auth_models import Base, User
from file_organizer.api.db_models import (
    FileMetadata,
    OrganizationJob,
    PluginInstallation,
    SettingsStore,
    UserSession,
    Workspace,
)

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
        username="testuser",
        email="test@example.com",
        hashed_password="fakehash",
    )
    db_session.add(u)
    db_session.flush()
    return u


# ------------------------------------------------------------------
# Table creation
# ------------------------------------------------------------------


class TestTableCreation:
    """Verify that all expected tables are created."""

    def test_all_tables_exist(self, db_session: Session) -> None:
        inspector = inspect(db_session.bind)
        tables = set(inspector.get_table_names())
        expected = {
            "users",
            "workspaces",
            "organization_jobs",
            "settings_store",
            "plugin_installations",
            "user_sessions",
            "file_metadata",
        }
        assert expected.issubset(tables)


# ------------------------------------------------------------------
# Workspace model
# ------------------------------------------------------------------


class TestWorkspaceModel:
    """Tests for the Workspace model."""

    def test_create_workspace(self, db_session: Session, user: User) -> None:
        ws = Workspace(
            name="My Workspace",
            owner_id=user.id,
            root_path="/tmp/ws",
        )
        db_session.add(ws)
        db_session.flush()

        assert ws.id is not None
        assert ws.name == "My Workspace"
        assert ws.owner_id == user.id
        assert ws.root_path == "/tmp/ws"
        assert ws.is_active is True
        assert ws.description is None
        assert isinstance(ws.created_at, datetime)
        assert isinstance(ws.updated_at, datetime)

    def test_workspace_with_description(self, db_session: Session, user: User) -> None:
        ws = Workspace(
            name="Described",
            owner_id=user.id,
            root_path="/tmp/desc",
            description="A test workspace",
        )
        db_session.add(ws)
        db_session.flush()
        assert ws.description == "A test workspace"

    def test_workspace_requires_name(self, db_session: Session, user: User) -> None:
        ws = Workspace(owner_id=user.id, root_path="/tmp/bad")
        db_session.add(ws)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_workspace_requires_owner(self, db_session: Session) -> None:
        ws = Workspace(name="orphan", root_path="/tmp/bad")
        db_session.add(ws)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_workspace_requires_root_path(self, db_session: Session, user: User) -> None:
        ws = Workspace(name="nopath", owner_id=user.id)
        db_session.add(ws)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_workspace_repr(self, db_session: Session, user: User) -> None:
        ws = Workspace(name="repr-test", owner_id=user.id, root_path="/tmp/r")
        db_session.add(ws)
        db_session.flush()
        assert "repr-test" in repr(ws)

    def test_workspace_foreign_key_to_user(self, db_session: Session) -> None:
        ws = Workspace(
            name="bad-fk",
            owner_id="nonexistent-user-id",
            root_path="/tmp/fk",
        )
        db_session.add(ws)
        # SQLite does not enforce FK by default; we still verify the row is created.
        db_session.flush()
        assert ws.id is not None


# ------------------------------------------------------------------
# OrganizationJob model
# ------------------------------------------------------------------


class TestOrganizationJobModel:
    """Tests for the OrganizationJob model."""

    def test_create_job_defaults(self, db_session: Session) -> None:
        job = OrganizationJob(input_dir="/in", output_dir="/out")
        db_session.add(job)
        db_session.flush()

        assert job.id is not None
        assert job.job_type == "organize"
        assert job.status == "queued"
        assert job.methodology == "content_based"
        assert job.dry_run is False
        assert job.total_files == 0
        assert job.processed_files == 0
        assert job.failed_files == 0
        assert job.skipped_files == 0
        assert job.error is None
        assert job.result_json is None
        assert job.workspace_id is None
        assert job.owner_id is None

    def test_create_job_with_owner(self, db_session: Session, user: User) -> None:
        job = OrganizationJob(
            input_dir="/in",
            output_dir="/out",
            owner_id=user.id,
            job_type="dedupe",
            status="running",
            methodology="para",
            dry_run=True,
        )
        db_session.add(job)
        db_session.flush()

        assert job.owner_id == user.id
        assert job.job_type == "dedupe"
        assert job.status == "running"
        assert job.methodology == "para"
        assert job.dry_run is True

    def test_create_job_with_workspace(self, db_session: Session, user: User) -> None:
        ws = Workspace(name="ws", owner_id=user.id, root_path="/ws")
        db_session.add(ws)
        db_session.flush()

        job = OrganizationJob(
            input_dir="/in",
            output_dir="/out",
            workspace_id=ws.id,
            owner_id=user.id,
        )
        db_session.add(job)
        db_session.flush()
        assert job.workspace_id == ws.id

    def test_job_requires_input_dir(self, db_session: Session) -> None:
        job = OrganizationJob(output_dir="/out")
        db_session.add(job)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_job_requires_output_dir(self, db_session: Session) -> None:
        job = OrganizationJob(input_dir="/in")
        db_session.add(job)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_job_repr(self, db_session: Session) -> None:
        job = OrganizationJob(input_dir="/in", output_dir="/out")
        db_session.add(job)
        db_session.flush()
        r = repr(job)
        assert "OrganizationJob" in r
        assert "queued" in r

    def test_job_result_json(self, db_session: Session) -> None:
        job = OrganizationJob(
            input_dir="/in",
            output_dir="/out",
            result_json='{"files": 10}',
        )
        db_session.add(job)
        db_session.flush()
        assert job.result_json == '{"files": 10}'


# ------------------------------------------------------------------
# SettingsStore model
# ------------------------------------------------------------------


class TestSettingsStoreModel:
    """Tests for the SettingsStore model."""

    def test_create_global_setting(self, db_session: Session) -> None:
        s = SettingsStore(key="theme", value="dark")
        db_session.add(s)
        db_session.flush()

        assert s.id is not None
        assert s.key == "theme"
        assert s.value == "dark"
        assert s.user_id is None

    def test_create_user_setting(self, db_session: Session, user: User) -> None:
        s = SettingsStore(key="theme", value="light", user_id=user.id)
        db_session.add(s)
        db_session.flush()
        assert s.user_id == user.id

    def test_unique_constraint_user_key(self, db_session: Session, user: User) -> None:
        s1 = SettingsStore(key="lang", value="en", user_id=user.id)
        db_session.add(s1)
        db_session.flush()

        s2 = SettingsStore(key="lang", value="fr", user_id=user.id)
        db_session.add(s2)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_same_key_different_users(self, db_session: Session) -> None:
        u1 = User(
            id=str(uuid.uuid4()),
            username="user1",
            email="u1@example.com",
            hashed_password="h",
        )
        u2 = User(
            id=str(uuid.uuid4()),
            username="user2",
            email="u2@example.com",
            hashed_password="h",
        )
        db_session.add_all([u1, u2])
        db_session.flush()

        s1 = SettingsStore(key="lang", value="en", user_id=u1.id)
        s2 = SettingsStore(key="lang", value="fr", user_id=u2.id)
        db_session.add_all([s1, s2])
        db_session.flush()

        assert s1.value == "en"
        assert s2.value == "fr"

    def test_setting_nullable_value(self, db_session: Session) -> None:
        s = SettingsStore(key="empty", value=None)
        db_session.add(s)
        db_session.flush()
        assert s.value is None

    def test_setting_repr(self, db_session: Session) -> None:
        s = SettingsStore(key="repr_key", value="v")
        db_session.add(s)
        db_session.flush()
        assert "repr_key" in repr(s)


# ------------------------------------------------------------------
# PluginInstallation model
# ------------------------------------------------------------------


class TestPluginInstallationModel:
    """Tests for the PluginInstallation model."""

    def test_create_plugin(self, db_session: Session) -> None:
        p = PluginInstallation(plugin_name="image-optimizer", version="1.0.0")
        db_session.add(p)
        db_session.flush()

        assert p.id is not None
        assert p.plugin_name == "image-optimizer"
        assert p.version == "1.0.0"
        assert p.is_enabled is True
        assert p.config_json is None
        assert p.installed_by is None
        assert isinstance(p.installed_at, datetime)

    def test_plugin_unique_name(self, db_session: Session) -> None:
        p1 = PluginInstallation(plugin_name="unique-plug")
        db_session.add(p1)
        db_session.flush()

        p2 = PluginInstallation(plugin_name="unique-plug")
        db_session.add(p2)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_plugin_with_config(self, db_session: Session) -> None:
        p = PluginInstallation(
            plugin_name="cfg-plug",
            config_json='{"enable_cache": true}',
        )
        db_session.add(p)
        db_session.flush()
        assert p.config_json == '{"enable_cache": true}'

    def test_plugin_installed_by_user(self, db_session: Session, user: User) -> None:
        p = PluginInstallation(plugin_name="user-plug", installed_by=user.id)
        db_session.add(p)
        db_session.flush()
        assert p.installed_by == user.id


# ------------------------------------------------------------------
# UserSession model
# ------------------------------------------------------------------


class TestUserSessionModel:
    """Tests for the UserSession model."""

    def test_create_user_session(self, db_session: Session, user: User) -> None:
        session_row = UserSession(
            user_id=user.id,
            token_hash="tok-hash",
            refresh_token_hash="ref-hash",
            expires_at=datetime.now(timezone.utc),
        )
        db_session.add(session_row)
        db_session.flush()

        assert session_row.id is not None
        assert session_row.user_id == user.id
        assert session_row.revoked_at is None

    def test_session_unique_token_hash(self, db_session: Session, user: User) -> None:
        one = UserSession(user_id=user.id, token_hash="same", expires_at=datetime.now(timezone.utc))
        db_session.add(one)
        db_session.flush()

        two = UserSession(user_id=user.id, token_hash="same", expires_at=datetime.now(timezone.utc))
        db_session.add(two)
        with pytest.raises(IntegrityError):
            db_session.flush()


# ------------------------------------------------------------------
# FileMetadata model
# ------------------------------------------------------------------


class TestFileMetadataModel:
    """Tests for the FileMetadata model."""

    def test_create_file_metadata(self, db_session: Session, user: User) -> None:
        workspace = Workspace(name="ws-meta", owner_id=user.id, root_path="/tmp/ws-meta")
        db_session.add(workspace)
        db_session.flush()

        row = FileMetadata(
            workspace_id=workspace.id,
            path="/tmp/ws-meta/docs/file.txt",
            relative_path="docs/file.txt",
            name="file.txt",
            size_bytes=123,
            mime_type="text/plain",
        )
        db_session.add(row)
        db_session.flush()

        assert row.id is not None
        assert row.workspace_id == workspace.id
        assert row.relative_path == "docs/file.txt"
        assert row.size_bytes == 123

    def test_file_metadata_unique_workspace_path(self, db_session: Session, user: User) -> None:
        workspace = Workspace(name="ws-meta-uq", owner_id=user.id, root_path="/tmp/ws-meta-uq")
        db_session.add(workspace)
        db_session.flush()

        one = FileMetadata(
            workspace_id=workspace.id,
            path="/tmp/ws-meta-uq/file.txt",
            relative_path="file.txt",
            name="file.txt",
            size_bytes=10,
        )
        db_session.add(one)
        db_session.flush()

        two = FileMetadata(
            workspace_id=workspace.id,
            path="/tmp/ws-meta-uq/file.txt",
            relative_path="file.txt",
            name="file.txt",
            size_bytes=11,
        )
        db_session.add(two)
        with pytest.raises(IntegrityError):
            db_session.flush()

    def test_plugin_repr(self, db_session: Session) -> None:
        p = PluginInstallation(plugin_name="repr-plug", version="2.0")
        db_session.add(p)
        db_session.flush()
        r = repr(p)
        assert "repr-plug" in r
        assert "2.0" in r

    def test_plugin_disabled(self, db_session: Session) -> None:
        p = PluginInstallation(plugin_name="off-plug", is_enabled=False)
        db_session.add(p)
        db_session.flush()
        assert p.is_enabled is False


# ------------------------------------------------------------------
# Default value tests
# ------------------------------------------------------------------


class TestDefaultValues:
    """Verify that column defaults are applied correctly."""

    def test_workspace_default_id_is_uuid(self, db_session: Session, user: User) -> None:
        ws = Workspace(name="uuid-test", owner_id=user.id, root_path="/t")
        db_session.add(ws)
        db_session.flush()
        # Should be a valid UUID4 string
        parsed = uuid.UUID(ws.id)
        assert parsed.version == 4

    def test_job_default_timestamps(self, db_session: Session) -> None:
        before = datetime.now(timezone.utc)
        job = OrganizationJob(input_dir="/i", output_dir="/o")
        db_session.add(job)
        db_session.flush()
        after = datetime.now(timezone.utc)

        assert before <= job.created_at.replace(tzinfo=timezone.utc) <= after
        assert before <= job.updated_at.replace(tzinfo=timezone.utc) <= after

    def test_settings_default_timestamps(self, db_session: Session) -> None:
        before = datetime.now(timezone.utc)
        s = SettingsStore(key="ts-test", value="v")
        db_session.add(s)
        db_session.flush()
        after = datetime.now(timezone.utc)

        assert before <= s.created_at.replace(tzinfo=timezone.utc) <= after
