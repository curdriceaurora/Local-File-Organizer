"""Tests for file_organizer.api.repositories.workspace_repo."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from file_organizer.api.db_models import Workspace
from file_organizer.api.repositories.workspace_repo import WorkspaceRepository

pytestmark = pytest.mark.unit


class TestWorkspaceRepositoryCreate:
    """Tests for WorkspaceRepository.create."""

    def test_create_minimal(self):
        session = MagicMock(spec=Session)

        WorkspaceRepository.create(session, "My Workspace", "user-1", "/home/user/docs")

        session.add.assert_called_once()
        session.flush.assert_called_once()
        added = session.add.call_args[0][0]
        assert isinstance(added, Workspace)
        assert added.name == "My Workspace"
        assert added.owner_id == "user-1"
        assert added.root_path == "/home/user/docs"
        assert added.description is None

    def test_create_with_description(self):
        session = MagicMock(spec=Session)

        WorkspaceRepository.create(
            session,
            "Work",
            "user-1",
            "/work",
            description="Work files",
        )

        added = session.add.call_args[0][0]
        assert added.description == "Work files"


class TestWorkspaceRepositoryGetById:
    """Tests for WorkspaceRepository.get_by_id."""

    def test_get_existing(self):
        session = MagicMock(spec=Session)
        ws = MagicMock(spec=Workspace)
        session.get.return_value = ws

        result = WorkspaceRepository.get_by_id(session, "ws-1")
        assert result is ws
        session.get.assert_called_once_with(Workspace, "ws-1")

    def test_get_nonexistent(self):
        session = MagicMock(spec=Session)
        session.get.return_value = None

        result = WorkspaceRepository.get_by_id(session, "missing")
        assert result is None


class TestWorkspaceRepositoryListByOwner:
    """Tests for WorkspaceRepository.list_by_owner."""

    def test_list_returns_workspaces(self):
        session = MagicMock(spec=Session)
        workspaces = [MagicMock(spec=Workspace), MagicMock(spec=Workspace)]
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = workspaces

        result = WorkspaceRepository.list_by_owner(session, "user-1")
        assert result == workspaces

    def test_list_empty(self):
        session = MagicMock(spec=Session)
        query = MagicMock()
        session.query.return_value = query
        query.filter.return_value = query
        query.order_by.return_value = query
        query.all.return_value = []

        result = WorkspaceRepository.list_by_owner(session, "user-1")
        assert result == []


class TestWorkspaceRepositoryUpdate:
    """Tests for WorkspaceRepository.update."""

    def test_update_name(self):
        session = MagicMock(spec=Session)
        ws = MagicMock(spec=Workspace)
        session.get.return_value = ws

        result = WorkspaceRepository.update(session, "ws-1", name="New Name")
        assert result is ws
        session.flush.assert_called_once()

    def test_update_ignores_unknown_keys(self):
        session = MagicMock(spec=Session)
        ws = MagicMock(spec=Workspace)
        session.get.return_value = ws

        result = WorkspaceRepository.update(session, "ws-1", name="X", unknown_field="ignored")
        assert result is ws
        session.flush.assert_called_once()

    def test_update_multiple_fields(self):
        session = MagicMock(spec=Session)
        ws = MagicMock(spec=Workspace)
        session.get.return_value = ws

        WorkspaceRepository.update(
            session,
            "ws-1",
            name="Updated",
            root_path="/new/path",
            description="Updated desc",
            is_active=False,
        )
        session.flush.assert_called_once()

    def test_update_nonexistent_returns_none(self):
        session = MagicMock(spec=Session)
        session.get.return_value = None

        result = WorkspaceRepository.update(session, "missing", name="X")
        assert result is None
        session.flush.assert_not_called()


class TestWorkspaceRepositoryDelete:
    """Tests for WorkspaceRepository.delete."""

    def test_delete_existing(self):
        session = MagicMock(spec=Session)
        ws = MagicMock(spec=Workspace)
        session.get.return_value = ws

        result = WorkspaceRepository.delete(session, "ws-1")
        assert result is True
        session.delete.assert_called_once_with(ws)
        session.flush.assert_called_once()

    def test_delete_nonexistent(self):
        session = MagicMock(spec=Session)
        session.get.return_value = None

        result = WorkspaceRepository.delete(session, "missing")
        assert result is False
        session.delete.assert_not_called()
