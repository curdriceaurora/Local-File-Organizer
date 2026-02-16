"""Repository for :class:`~file_organizer.api.db_models.Workspace` CRUD."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from file_organizer.api.db_models import Workspace


class WorkspaceRepository:
    """Data-access layer for workspaces."""

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    def create(
        session: Session,
        name: str,
        owner_id: str,
        root_path: str,
        description: Optional[str] = None,
    ) -> Workspace:
        """Create and persist a new workspace.

        Args:
            session: Active SQLAlchemy session.
            name: Human-readable workspace name.
            owner_id: Foreign key to ``users.id``.
            root_path: Filesystem root of the workspace.
            description: Optional description text.

        Returns:
            The newly created :class:`Workspace` instance.
        """
        workspace = Workspace(
            name=name,
            owner_id=owner_id,
            root_path=root_path,
            description=description,
        )
        session.add(workspace)
        session.flush()
        return workspace

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    def get_by_id(session: Session, workspace_id: str) -> Optional[Workspace]:
        """Return a single workspace by primary key, or ``None``."""
        return session.get(Workspace, workspace_id)

    @staticmethod
    def list_by_owner(session: Session, owner_id: str) -> list[Workspace]:
        """Return all workspaces belonging to *owner_id*, ordered by name."""
        return (
            session.query(Workspace)
            .filter(Workspace.owner_id == owner_id)
            .order_by(Workspace.name)
            .all()
        )

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    @staticmethod
    def update(
        session: Session,
        workspace_id: str,
        **kwargs: object,
    ) -> Optional[Workspace]:
        """Update mutable fields of a workspace.

        Accepted keyword arguments: ``name``, ``root_path``, ``description``,
        ``is_active``.  Unknown keys are silently ignored.

        Returns:
            The updated :class:`Workspace`, or ``None`` if not found.
        """
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            return None

        allowed = {"name", "root_path", "description", "is_active"}
        for key, value in kwargs.items():
            if key in allowed:
                setattr(workspace, key, value)

        workspace.updated_at = datetime.now(timezone.utc)
        session.flush()
        return workspace

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    @staticmethod
    def delete(session: Session, workspace_id: str) -> bool:
        """Delete a workspace by primary key.

        Returns:
            ``True`` if a row was deleted, ``False`` otherwise.
        """
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            return False
        session.delete(workspace)
        session.flush()
        return True
