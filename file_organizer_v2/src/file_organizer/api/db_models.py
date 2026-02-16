"""SQLAlchemy ORM models for workspaces, jobs, settings, and plugins."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)

from file_organizer.api.auth_models import Base


def _utcnow() -> datetime:
    """Return current UTC datetime (used as column default)."""
    return datetime.now(timezone.utc)


def _new_id() -> str:
    """Generate a new UUID4 string (used as primary-key default)."""
    return str(uuid.uuid4())


class Workspace(Base):
    """A workspace groups files under a single root directory."""

    __tablename__ = "workspaces"

    id = Column(String, primary_key=True, default=_new_id)
    name = Column(String, nullable=False)
    owner_id = Column(String, ForeignKey("users.id"), nullable=False)
    root_path = Column(String, nullable=False)
    description = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<Workspace {self.name!r} owner={self.owner_id}>"


class OrganizationJob(Base):
    """Tracks an asynchronous file-organization job."""

    __tablename__ = "organization_jobs"

    id = Column(String, primary_key=True, default=_new_id)
    workspace_id = Column(String, ForeignKey("workspaces.id"), nullable=True)
    owner_id = Column(String, ForeignKey("users.id"), nullable=True)
    job_type = Column(String, nullable=False, default="organize")
    status = Column(String, nullable=False, default="queued")
    input_dir = Column(String, nullable=False)
    output_dir = Column(String, nullable=False)
    methodology = Column(String, default="content_based")
    dry_run = Column(Boolean, default=False)
    total_files = Column(Integer, default=0)
    processed_files = Column(Integer, default=0)
    failed_files = Column(Integer, default=0)
    skipped_files = Column(Integer, default=0)
    error = Column(String, nullable=True)
    result_json = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<OrganizationJob {self.id} status={self.status}>"


class SettingsStore(Base):
    """Key/value settings scoped per user (or global when user_id is NULL)."""

    __tablename__ = "settings_store"

    id = Column(String, primary_key=True, default=_new_id)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    key = Column(String, nullable=False, index=True)
    value = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_settings_user_key"),
    )

    def __repr__(self) -> str:
        return f"<SettingsStore key={self.key!r} user={self.user_id}>"


class PluginInstallation(Base):
    """Tracks installed plugins and their configuration."""

    __tablename__ = "plugin_installations"

    id = Column(String, primary_key=True, default=_new_id)
    plugin_name = Column(String, nullable=False, unique=True, index=True)
    version = Column(String, nullable=True)
    is_enabled = Column(Boolean, default=True)
    config_json = Column(String, nullable=True)
    installed_by = Column(String, ForeignKey("users.id"), nullable=True)
    installed_at = Column(DateTime(timezone=True), default=_utcnow)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<PluginInstallation {self.plugin_name!r} v={self.version}>"
