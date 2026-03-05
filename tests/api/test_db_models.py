"""Tests for file_organizer.api.db_models ORM model definitions."""

from __future__ import annotations

import uuid

import pytest

from file_organizer.api.db_models import (
    FileMetadata,
    OrganizationJob,
    PluginInstallation,
    SettingsStore,
    UserSession,
    Workspace,
    _new_id,
    _utcnow,
)

pytestmark = pytest.mark.unit


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_utcnow_returns_datetime(self):
        result = _utcnow()
        assert result.tzinfo is not None

    def test_new_id_returns_valid_uuid(self):
        result = _new_id()
        assert isinstance(result, str)
        # Should be parseable as UUID4
        parsed = uuid.UUID(result)
        assert parsed.version == 4


class TestWorkspaceModel:
    """Tests for the Workspace ORM model."""

    def test_tablename(self):
        assert Workspace.__tablename__ == "workspaces"

    def test_instantiation(self):
        ws = Workspace(
            id="ws-1",
            name="Test",
            owner_id="user-1",
            root_path="/tmp/test",
        )
        assert ws.name == "Test"
        assert ws.owner_id == "user-1"
        assert ws.root_path == "/tmp/test"
        assert ws.description is None

    def test_repr(self):
        ws = Workspace(name="MyWS", owner_id="u1")
        assert "MyWS" in repr(ws)
        assert "u1" in repr(ws)

    def test_default_is_active(self):
        # Column default is True
        col = Workspace.__table__.columns["is_active"]
        assert col.default.arg is True


class TestOrganizationJobModel:
    """Tests for the OrganizationJob ORM model."""

    def test_tablename(self):
        assert OrganizationJob.__tablename__ == "organization_jobs"

    def test_instantiation(self):
        job = OrganizationJob(
            id="job-1",
            input_dir="/in",
            output_dir="/out",
        )
        assert job.input_dir == "/in"
        assert job.output_dir == "/out"

    def test_default_status(self):
        col = OrganizationJob.__table__.columns["status"]
        assert col.default.arg == "queued"

    def test_default_job_type(self):
        col = OrganizationJob.__table__.columns["job_type"]
        assert col.default.arg == "organize"

    def test_default_dry_run(self):
        col = OrganizationJob.__table__.columns["dry_run"]
        assert col.default.arg is False

    def test_default_counters(self):
        for col_name in ("total_files", "processed_files", "failed_files", "skipped_files"):
            col = OrganizationJob.__table__.columns[col_name]
            assert col.default.arg == 0

    def test_repr(self):
        job = OrganizationJob(id="j1", status="running")
        r = repr(job)
        assert "j1" in r
        assert "running" in r


class TestUserSessionModel:
    """Tests for the UserSession ORM model."""

    def test_tablename(self):
        assert UserSession.__tablename__ == "user_sessions"

    def test_instantiation(self):
        us = UserSession(
            id="sess-1",
            user_id="user-1",
            token_hash="hash",
        )
        assert us.user_id == "user-1"
        assert us.token_hash == "hash"
        assert us.revoked_at is None

    def test_token_hash_is_unique(self):
        col = UserSession.__table__.columns["token_hash"]
        assert col.unique is True

    def test_repr(self):
        us = UserSession(id="s1", user_id="u1")
        r = repr(us)
        assert "s1" in r
        assert "u1" in r


class TestSettingsStoreModel:
    """Tests for the SettingsStore ORM model."""

    def test_tablename(self):
        assert SettingsStore.__tablename__ == "settings_store"

    def test_instantiation(self):
        ss = SettingsStore(key="theme", value="dark")
        assert ss.key == "theme"
        assert ss.value == "dark"
        assert ss.user_id is None

    def test_unique_constraint_name(self):
        constraints = {c.name for c in SettingsStore.__table__.constraints}
        assert "uq_settings_user_key" in constraints

    def test_repr(self):
        ss = SettingsStore(key="theme", user_id="u1")
        r = repr(ss)
        assert "theme" in r
        assert "u1" in r


class TestPluginInstallationModel:
    """Tests for the PluginInstallation ORM model."""

    def test_tablename(self):
        assert PluginInstallation.__tablename__ == "plugin_installations"

    def test_instantiation(self):
        pi = PluginInstallation(
            plugin_name="my-plugin",
            version="1.0.0",
        )
        assert pi.plugin_name == "my-plugin"
        assert pi.version == "1.0.0"

    def test_default_is_enabled(self):
        col = PluginInstallation.__table__.columns["is_enabled"]
        assert col.default.arg is True

    def test_plugin_name_is_unique(self):
        col = PluginInstallation.__table__.columns["plugin_name"]
        assert col.unique is True

    def test_repr(self):
        pi = PluginInstallation(plugin_name="test-plugin", version="2.0")
        r = repr(pi)
        assert "test-plugin" in r
        assert "2.0" in r


class TestFileMetadataModel:
    """Tests for the FileMetadata ORM model."""

    def test_tablename(self):
        assert FileMetadata.__tablename__ == "file_metadata"

    def test_instantiation(self):
        fm = FileMetadata(
            workspace_id="ws-1",
            path="/abs/file.txt",
            relative_path="file.txt",
            name="file.txt",
        )
        assert fm.workspace_id == "ws-1"
        assert fm.relative_path == "file.txt"

    def test_default_size_bytes(self):
        col = FileMetadata.__table__.columns["size_bytes"]
        assert col.default.arg == 0

    def test_unique_constraint_name(self):
        constraints = {c.name for c in FileMetadata.__table__.constraints}
        assert "uq_file_metadata_workspace_path" in constraints

    def test_repr(self):
        fm = FileMetadata(relative_path="docs/r.md", workspace_id="ws-1")
        r = repr(fm)
        assert "docs/r.md" in r
        assert "ws-1" in r
